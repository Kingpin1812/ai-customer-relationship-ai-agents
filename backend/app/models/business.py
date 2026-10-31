from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UuidPk, utcnow

Money = Numeric(14, 2)


class Customer(UuidPk, CreatedAt, Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "provider_customer_id"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    provider_customer_id: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    sync_status: Mapped[str] = mapped_column(String(30), default="synced")


class InvoiceSequence(Base):
    __tablename__ = "invoice_sequences"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class Invoice(UuidPk, CreatedAt, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_number"),
        UniqueConstraint("organization_id", "workflow_id"),
        CheckConstraint("status IN ('draft','issued','void')", name="status"),
        CheckConstraint("total = subtotal + tax", name="total_adds_up"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"))
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal] = mapped_column(Money)
    tax: Mapped[Decimal] = mapped_column(Money)
    total: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvoiceItem(UuidPk, Base):
    __tablename__ = "invoice_items"

    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    line_total: Mapped[Decimal] = mapped_column(Money)


class Artifact(UuidPk, CreatedAt, Base):
    __tablename__ = "artifacts"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))


class Report(UuidPk, Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("organization_id", "workflow_id", "report_type"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"))
    report_type: Mapped[str] = mapped_column(String(60))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    pdf_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    csv_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SalesRecord(UuidPk, Base):
    __tablename__ = "sales_records"
    __table_args__ = (Index("ix_sales_org_sold_on", "organization_id", "sold_on"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    customer_name: Mapped[str] = mapped_column(String(200))
    sold_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))


class EmailDraft(UuidPk, CreatedAt, Base):
    __tablename__ = "email_drafts"
    __table_args__ = (UniqueConstraint("organization_id", "workflow_id"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"))
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    artifact_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MockCrmRecord(UuidPk, Base):
    """Stands in for an external CRM. Only the mock adapter touches this table."""

    __tablename__ = "mock_crm_records"
    __table_args__ = (UniqueConstraint("organization_id", "provider_customer_id"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider_customer_id: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    notes: Mapped[list] = mapped_column(JSON, default=list)
    applied_keys: Mapped[list] = mapped_column(JSON, default=list)


class MockEmail(UuidPk, Base):
    """Stands in for an external mail provider's sent log. No real mail ever leaves."""

    __tablename__ = "mock_emails"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    provider_message_id: Mapped[str] = mapped_column(String(200))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
