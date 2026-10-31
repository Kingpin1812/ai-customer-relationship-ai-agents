"""Read-only invoices, reports and artifact access, all tenant scoped."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import func, select

from app.auth.dependencies import Actor, CurrentActor, Db
from app.auth.permissions import Permission
from app.core.errors import NotFound
from app.models import Customer, Invoice, InvoiceItem, Report, Workflow
from app.schemas.common import Limit, Offset, Page, Schema
from app.schemas.workflows import ArtifactOut
from app.services.artifacts import get_artifact_for_actor, read_artifact

invoices = APIRouter(prefix="/invoices", tags=["invoices"])
reports = APIRouter(prefix="/reports", tags=["reports"])
artifacts = APIRouter(prefix="/artifacts", tags=["artifacts"])


class InvoiceSummary(Schema):
    id: UUID
    workflow_id: UUID
    invoice_number: str
    customer_name: str
    currency: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    status: str
    issue_date: date
    due_date: date
    artifact_id: UUID | None


class InvoiceLine(Schema):
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal


class InvoiceDetail(InvoiceSummary):
    items: list[InvoiceLine]


class ReportOut(Schema):
    id: UUID
    workflow_id: UUID
    report_type: str
    period_start: date
    period_end: date
    filters: dict
    source: dict
    summary: dict
    generated_at: datetime
    pdf_artifact_id: UUID | None
    csv_artifact_id: UUID | None


def _own_filter(statement, actor: Actor, model):
    if actor.can(Permission.BUSINESS_VIEW_ALL):
        return statement
    return statement.join(Workflow, Workflow.id == model.workflow_id).where(
        Workflow.created_by == actor.user_id
    )


def _invoice_query(actor: Actor):
    statement = (
        select(Invoice, Customer.name)
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(Invoice.organization_id == actor.organization_id)
    )
    return _own_filter(statement, actor, Invoice)


def _invoice_fields(invoice: Invoice, customer_name: str) -> dict:
    return {
        "id": invoice.id,
        "workflow_id": invoice.workflow_id,
        "invoice_number": invoice.invoice_number,
        "customer_name": customer_name,
        "currency": invoice.currency,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
        "status": invoice.status,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "artifact_id": invoice.artifact_id,
    }


@invoices.get("", response_model=Page[InvoiceSummary])
def list_invoices(
    actor: CurrentActor, db: Db, limit: Limit = 25, offset: Offset = 0
) -> Page[InvoiceSummary]:
    statement = _invoice_query(actor)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.execute(
        statement.order_by(Invoice.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return Page(
        items=[InvoiceSummary(**_invoice_fields(i, n)) for i, n in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@invoices.get("/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: UUID, actor: CurrentActor, db: Db) -> InvoiceDetail:
    row = db.execute(_invoice_query(actor).where(Invoice.id == invoice_id)).first()
    if row is None:
        raise NotFound("Invoice")
    items = db.scalars(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice_id)).all()
    return InvoiceDetail(
        **_invoice_fields(row[0], row[1]), items=[InvoiceLine.model_validate(i) for i in items]
    )


@reports.get("", response_model=Page[ReportOut])
def list_reports(
    actor: CurrentActor, db: Db, limit: Limit = 25, offset: Offset = 0
) -> Page[ReportOut]:
    statement = _own_filter(
        select(Report).where(Report.organization_id == actor.organization_id), actor, Report
    )
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(
        statement.order_by(Report.generated_at.desc()).limit(limit).offset(offset)
    ).all()
    return Page(
        items=[ReportOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@artifacts.get("/{artifact_id}", response_model=ArtifactOut)
def artifact_metadata(artifact_id: UUID, actor: CurrentActor, db: Db) -> ArtifactOut:
    return ArtifactOut.model_validate(get_artifact_for_actor(db, actor, artifact_id))


@artifacts.get("/{artifact_id}/download")
def artifact_download(artifact_id: UUID, actor: CurrentActor, db: Db) -> Response:
    artifact = get_artifact_for_actor(db, actor, artifact_id)
    data = read_artifact(db, actor.organization_id, artifact.id)
    return Response(
        content=data,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
