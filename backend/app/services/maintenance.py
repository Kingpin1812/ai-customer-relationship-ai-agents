from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ApprovalRequest, Workflow
from app.services.audit.service import record_audit
from app.services.reliability.outbox import dispatch_outbox
from app.services.workflows.service import fail_workflow

STUCK_AFTER = timedelta(minutes=2)


def expire_overdue_approvals() -> int:
    with SessionLocal() as db:
        overdue = db.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.status == "pending", ApprovalRequest.expires_at <= datetime.now(UTC)
            )
            .with_for_update(skip_locked=True)
        ).all()
        for approval in overdue:
            approval.status = "expired"
            approval.invalidation_reason = "approval window passed"
            record_audit(
                db,
                approval.organization_id,
                "approval.expired",
                str(approval.id),
                "expired",
                None,
                approval.workflow_id,
            )
            workflow = db.get(Workflow, approval.workflow_id)
            if workflow.status == "waiting_for_approval":
                fail_workflow(
                    db,
                    workflow,
                    "validation_error",
                    "The approval window passed. Submit the request again.",
                )
        db.commit()
        return len(overdue)


def find_stuck_workflows() -> list[UUID]:
    """Work a crashed process left behind. Re-running is safe: the runner is idempotent and locked."""
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Workflow.id).where(
                    Workflow.status.in_(("queued", "running")),
                    Workflow.updated_at <= datetime.now(UTC) - STUCK_AFTER,
                )
            )
        )


def run_maintenance(submit: Callable[[UUID], None]) -> None:
    expire_overdue_approvals()
    for workflow_id in find_stuck_workflows():
        submit(workflow_id)
    with SessionLocal() as db:
        dispatch_outbox(db)
