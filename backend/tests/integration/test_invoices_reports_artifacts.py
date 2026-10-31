import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal as D
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import func, select

from app.core.errors import ValidationFailed
from app.db.session import SessionLocal
from app.integrations.storage import LocalStorage, S3Storage, StorageError
from app.models import Customer, Invoice, Membership, Organization, Report, User, Workflow
from app.services.artifacts import store_artifact
from app.services.invoices.calculator import LineInput
from app.services.invoices.service import create_draft_invoice, next_invoice_number
from app.services.reports.service import generate_report


def _org(db, name="Demo Trading Co"):
    return db.scalar(select(Organization).where(Organization.name == name))


def _workflow(db, org_id):
    user_id = db.scalar(select(User.id).where(User.organization_id == org_id).limit(1))
    workflow = Workflow(
        organization_id=org_id,
        created_by=user_id,
        request_text="t",
        status="running",
        graph_thread_id=uuid4().hex,
        idempotency_key=uuid4().hex,
    )
    db.add(workflow)
    db.flush()
    return workflow


def _customer(db, org_id):
    customer = Customer(
        organization_id=org_id,
        provider="mock_crm",
        provider_customer_id=uuid4().hex,
        name="Acme Ltd",
        email="billing@acme-ltd.example",
    )
    db.add(customer)
    db.flush()
    return customer


def test_invoice_numbers_are_unique_under_concurrency(db):
    org_id = _org(db).id
    db.commit()

    def take(_):
        with SessionLocal() as session:
            number = next_invoice_number(session, org_id, 2026)
            session.commit()
            return number

    with ThreadPoolExecutor(max_workers=10) as pool:
        numbers = list(pool.map(take, range(20)))
    assert len(set(numbers)) == 20
    assert all(n.startswith("INV-2026-") for n in numbers)


def test_draft_invoice_is_created_once_per_workflow(db):
    org = _org(db)
    workflow = _workflow(db, org.id)
    customer = _customer(db, org.id)
    lines = [LineInput("Consulting", D("10"), D("2500"))]
    first = create_draft_invoice(db, org.id, workflow.id, customer, lines, "INR")
    second = create_draft_invoice(db, org.id, workflow.id, customer, lines, "INR")
    assert first.id == second.id
    assert first.subtotal == D("25000.00")
    assert first.total == D("29500.00")
    assert first.status == "draft"
    assert first.artifact_id is not None
    assert db.scalar(select(func.count()).select_from(Invoice)) == 1


def test_invoice_rejects_unknown_currency(db):
    org = _org(db)
    with pytest.raises(ValidationFailed):
        create_draft_invoice(
            db,
            org.id,
            _workflow(db, org.id).id,
            _customer(db, org.id),
            [LineInput("x", D("1"), D("1"))],
            "XXX",
        )


def test_report_contains_only_own_tenant_and_metadata(db):
    org = _org(db)
    workflow = _workflow(db, org.id)
    report = generate_report(
        db, org.id, workflow.id, "monthly_sales_summary", {"period": "this_month"}
    )
    today = date.today()
    assert report.period_start == today.replace(day=1)
    assert report.source["query"] == "monthly_sales_summary.v1"
    assert report.generated_at is not None
    names = {row["customer_name"] for row in report.summary["rows"]}
    assert names == {"Acme Ltd", "Globex Corporation", "Initech"}
    assert "Secret Other Customer" not in str(report.summary)
    # 3 customers across the 2 days in this month: (12000+13500)+(12700+14200)+(13400+14900)
    assert D(report.summary["total"]) == D("80700.00")


def test_report_artifacts_carry_period_and_generation_metadata(db):
    from app.services.artifacts import read_artifact

    org = _org(db)
    report = generate_report(
        db, org.id, _workflow(db, org.id).id, "monthly_sales_summary", {"period": "last_month"}
    )
    content = read_artifact(db, org.id, report.csv_artifact_id).decode()
    rows = list(csv.reader(io.StringIO(content)))
    flat = " ".join(" ".join(r) for r in rows)
    assert str(report.period_start) in flat
    assert "generated_at" in flat
    assert read_artifact(db, org.id, report.pdf_artifact_id).startswith(b"%PDF")


def test_report_is_created_once_per_workflow(db):
    org = _org(db)
    workflow = _workflow(db, org.id)
    params = {"period": "this_month"}
    a = generate_report(db, org.id, workflow.id, "monthly_sales_summary", params)
    b = generate_report(db, org.id, workflow.id, "monthly_sales_summary", params)
    assert a.id == b.id
    assert db.scalar(select(func.count()).select_from(Report)) == 1


@pytest.mark.parametrize(
    ("report_type", "params"),
    [
        ("drop_table_users", {"period": "this_month"}),
        ("monthly_sales_summary", {"period": "1=1; DROP TABLE users"}),
        ("monthly_sales_summary", {"period": "this_month", "sql": "select 1"}),
    ],
)
def test_invalid_reports_are_rejected(db, report_type, params):
    org = _org(db)
    with pytest.raises(ValidationFailed):
        generate_report(db, org.id, _workflow(db, org.id).id, report_type, params)


@pytest.mark.parametrize(
    "key", ["../../etc/passwd", "..\\..\\windows\\system32", "/abs/path", "a/../../b", "C:/x"]
)
def test_local_storage_refuses_path_traversal(tmp_path, key):
    storage = LocalStorage(str(tmp_path))
    with pytest.raises(StorageError):
        storage.put(key, b"x", "text/plain")
    with pytest.raises(StorageError):
        storage.get(key)


def test_local_storage_round_trip(tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.put("org/wf/a.pdf", b"hello", "application/pdf")
    assert storage.get("org/wf/a.pdf") == b"hello"
    storage.check()


def test_s3_storage_round_trip():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        storage = S3Storage(
            bucket="test-bucket",
            endpoint_url=None,
            access_key="a",
            secret_key="s",
            region="us-east-1",
        )
        storage.put("org/wf/a.pdf", b"hello", "application/pdf")
        assert storage.get("org/wf/a.pdf") == b"hello"
        storage.check()


def test_artifact_download_is_tenant_and_owner_scoped(db, manager, operator, other_admin, viewer):
    org = _org(db)
    manager_id = db.scalar(
        select(Membership.user_id).where(
            Membership.organization_id == org.id, Membership.role == "manager"
        )
    )
    workflow = _workflow(db, org.id)
    workflow.created_by = manager_id
    artifact = store_artifact(db, org.id, workflow.id, "report", "a.csv", "text/csv", b"data")
    db.commit()
    url = f"/artifacts/{artifact.id}"
    assert manager.get(url).json()["checksum"] == artifact.checksum
    assert manager.get(f"{url}/download").content == b"data"
    assert viewer.get(f"{url}/download").status_code == 200
    assert other_admin.get(url).status_code == 404
    assert other_admin.get(f"{url}/download").status_code == 404
    assert operator.get(url).status_code == 404  # not this operator's workflow


def test_artifact_download_detects_tampering(db, manager):
    from app.integrations.storage import get_storage

    org = _org(db)
    artifact = store_artifact(
        db, org.id, _workflow(db, org.id).id, "report", "a.csv", "text/csv", b"data"
    )
    db.commit()
    get_storage().put(artifact.storage_key, b"tampered", "text/csv")
    assert manager.get(f"/artifacts/{artifact.id}/download").status_code == 409
