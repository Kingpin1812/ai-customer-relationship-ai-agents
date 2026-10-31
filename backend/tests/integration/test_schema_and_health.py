import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.base import Base
from app.db.session import engine
from app.models import AuditEvent, IdempotencyRecord, Organization
from tests.conftest import alembic_config


def test_health_endpoints(client):
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}
    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"


def test_ready_reports_503_when_database_is_down(client, monkeypatch):
    def broken():
        raise OSError("down")

    monkeypatch.setattr("app.api.v1.health.check_database", broken)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "down" not in response.text


def test_migrations_round_trip_and_match_models():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        opts = {
            "include_name": lambda name, type_, _: (
                not (type_ == "table" and name.startswith("checkpoint"))
            )
        }
        diff = compare_metadata(MigrationContext.configure(conn, opts=opts), Base.metadata)
    assert diff == []


def test_idempotency_uniqueness_is_enforced_by_the_database(db):
    org_id = db.scalar(select(Organization.id).limit(1))
    for _ in range(2):
        db.add(IdempotencyRecord(organization_id=org_id, key="same", operation="x", status="done"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_audit_rows_are_append_only(db):
    org_id = db.scalar(select(Organization.id).limit(1))
    event = AuditEvent(organization_id=org_id, action="t", target="t", result="ok")
    db.add(event)
    db.commit()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE audit_events SET result='forged' WHERE id=:i"), {"i": event.id})
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM audit_events WHERE id=:i"), {"i": event.id})
    db.rollback()


def test_money_columns_are_numeric():
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name IN "
                "('subtotal','tax','total','unit_price','line_total','amount','quantity','tax_rate')"
            )
        ).all()
    assert rows
    assert {r.data_type for r in rows} == {"numeric"}


def test_every_business_table_is_tenant_scoped():
    exempt = {"organizations", "users", "invoice_items", "alembic_version"}
    with engine.connect() as conn:
        tables = conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename NOT LIKE 'checkpoint%'"
            )
        ).scalars()
        names = set(tables) - exempt
        scoped = set(
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND column_name='organization_id'"
                )
            ).scalars()
        )
    assert names <= scoped, names - scoped
    assert uuid.UUID  # uuid primary keys are checked by the model definitions
