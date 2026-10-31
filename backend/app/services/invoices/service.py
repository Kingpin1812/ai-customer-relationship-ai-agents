from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.models import Customer, Invoice, InvoiceItem, InvoiceSequence, Organization
from app.services.artifacts import store_artifact
from app.services.invoices.calculator import LineInput, calculate
from app.services.invoices.pdf import render_invoice_pdf


def next_invoice_number(db: Session, organization_id: UUID, year: int) -> str:
    """Atomic counter: the upsert row lock serializes concurrent callers until they commit."""
    statement = (
        insert(InvoiceSequence)
        .values(organization_id=organization_id, year=year, last_value=1)
        .on_conflict_do_update(
            index_elements=["organization_id", "year"],
            set_={"last_value": InvoiceSequence.last_value + 1},
        )
        .returning(InvoiceSequence.last_value)
    )
    value = db.execute(statement).scalar_one()
    return f"INV-{year}-{value:06d}"


def create_draft_invoice(
    db: Session,
    organization_id: UUID,
    workflow_id: UUID,
    customer: Customer,
    items: list[LineInput],
    currency: str,
    today: date | None = None,
) -> Invoice:
    """Create the workflow's draft invoice and PDF. Returns the existing one on a repeat call."""
    existing = db.scalar(
        select(Invoice).where(
            Invoice.organization_id == organization_id, Invoice.workflow_id == workflow_id
        )
    )
    if existing:
        return existing

    settings = get_settings()
    currency = currency.upper()
    if currency not in settings.currencies:
        raise ValidationFailed(f"Currency {currency} is not supported.")
    totals = calculate(items, settings.default_tax_rate)

    issue_date = today or datetime.now(UTC).date()
    invoice = Invoice(
        organization_id=organization_id,
        workflow_id=workflow_id,
        customer_id=customer.id,
        invoice_number=next_invoice_number(db, organization_id, issue_date.year),
        currency=currency,
        subtotal=totals.subtotal,
        tax=totals.tax,
        total=totals.total,
        status="draft",
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=settings.default_payment_terms_days),
    )
    db.add(invoice)
    db.flush()
    rows = [
        InvoiceItem(
            invoice_id=invoice.id,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax_rate=totals.tax_rate,
            line_total=line.line_total,
        )
        for line in totals.lines
    ]
    db.add_all(rows)
    db.flush()

    organization = db.get(Organization, organization_id)
    artifact = store_artifact(
        db,
        organization_id,
        workflow_id,
        "invoice",
        f"{invoice.invoice_number}.pdf",
        "application/pdf",
        render_invoice_pdf(invoice, customer, rows, organization.name),
    )
    invoice.artifact_id = artifact.id
    db.flush()
    return invoice


def issue_invoice(db: Session, invoice: Invoice) -> Invoice:
    """Finalize a draft. Only called while executing an approved payload."""
    if invoice.status == "draft":
        invoice.status = "issued"
        invoice.issued_at = datetime.now(UTC)
        db.flush()
    return invoice
