from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UuidPk, utcnow


class Workflow(UuidPk, CreatedAt, Base):
    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','waiting_for_approval','succeeded','failed',"
            "'rejected','cancelled')",
            name="status",
        ),
        UniqueConstraint("organization_id", "idempotency_key"),
        Index("ix_workflows_org_status_created", "organization_id", "status", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    request_text: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    plan: Mapped[dict | None] = mapped_column(JSON)
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"))
    planner_source: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    graph_thread_id: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    error_category: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    needs_clarification: Mapped[bool] = mapped_column(default=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(32))
    trace_context: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WorkflowStep(UuidPk, Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("workflow_id", "step_key"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"), index=True)
    step_key: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="running")
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    runs: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalRequest(UuidPk, CreatedAt, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','changes_requested','expired')",
            name="status",
        ),
        Index(
            "uq_approval_one_pending_per_workflow",
            "workflow_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_approvals_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(60))
    summary: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(20), default="high")
    # Immutable snapshot of exactly what will run. Execution reads this, nothing else.
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IdempotencyRecord(CreatedAt, Base):
    __tablename__ = "idempotency_records"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    operation: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    result_reference: Mapped[str | None] = mapped_column(String(64))


class AuditEvent(UuidPk, CreatedAt, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_org_created", "organization_id", "created_at"),
        Index("ix_audit_org_workflow", "organization_id", "workflow_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    workflow_id: Mapped[UUID | None] = mapped_column(ForeignKey("workflows.id"))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(200))
    result: Mapped[str] = mapped_column(String(30))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class IntegrationOperation(UuidPk, CreatedAt, Base):
    __tablename__ = "integration_operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','succeeded','retry_scheduled','failed',"
            "'unknown_outcome','manual_review_required')",
            name="status",
        ),
        UniqueConstraint("organization_id", "op_key"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    operation: Mapped[str] = mapped_column(String(60))
    op_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_category: Mapped[str | None] = mapped_column(String(40))
    last_error: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    result: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OutboxEvent(UuidPk, CreatedAt, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_unpublished", "created_at", postgresql_where=text("published_at IS NULL")),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
