import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.dependencies import Actor
from app.auth.permissions import Permission
from app.core.context import get_correlation_id
from app.core.errors import Conflict, Forbidden, NotFound
from app.models import ApprovalRequest, IdempotencyRecord, User, Workflow
from app.observability import metrics
from app.schemas.workflows import WorkflowCreate
from app.services.audit.service import record_audit
from app.services.reliability.outbox import enqueue_event
from app.services.workflows.state_machine import RETRYABLE_ERROR_CATEGORIES, ensure_transition

_OPERATION = "workflow.create"


def _request_hash(body: WorkflowCreate) -> str:
    canonical = json.dumps(
        {"request": body.request, "context": body.context.model_dump(mode="json")},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _trace_fields() -> tuple[str | None, dict]:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None, {}
    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier)
    return format(span_context.trace_id, "032x"), carrier


def create_workflow(db: Session, actor: Actor, body: WorkflowCreate) -> tuple[Workflow, bool]:
    """Return (workflow, created). The unique key decides the race; losers read the winner's row."""
    request_hash = _request_hash(body)
    claimed = db.execute(
        insert(IdempotencyRecord)
        .values(
            organization_id=actor.organization_id,
            key=body.idempotency_key,
            operation=_OPERATION,
            status="in_progress",
            request_hash=request_hash,
            created_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "key"])
        .returning(IdempotencyRecord.key)
    ).scalar_one_or_none()

    if claimed is None:
        db.rollback()
        record = db.get(IdempotencyRecord, (actor.organization_id, body.idempotency_key))
        if record.request_hash != request_hash or record.operation != _OPERATION:
            raise Conflict("That idempotency key was already used for a different request.")
        workflow = db.get(Workflow, UUID(record.result_reference))
        return workflow, False

    workflow_id = uuid4()
    trace_id, carrier = _trace_fields()
    workflow = Workflow(
        id=workflow_id,
        organization_id=actor.organization_id,
        created_by=actor.user_id,
        request_text=body.request,
        context=body.context.model_dump(mode="json", exclude_none=True),
        status="queued",
        graph_thread_id=str(workflow_id),
        idempotency_key=body.idempotency_key,
        correlation_id=get_correlation_id(),
        trace_id=trace_id,
        trace_context=carrier,
    )
    db.add(workflow)
    db.flush()
    record = db.get(IdempotencyRecord, (actor.organization_id, body.idempotency_key))
    record.status = "completed"
    record.result_reference = str(workflow_id)
    record_audit(
        db,
        actor.organization_id,
        "workflow.created",
        str(workflow_id),
        "queued",
        actor.user_id,
        workflow_id,
    )
    enqueue_event(db, actor.organization_id, "workflow.created", {"workflow_id": str(workflow_id)})
    db.commit()
    metrics.WORKFLOWS_CREATED.inc()
    return workflow, True


def visible_workflows(actor: Actor):
    """The one definition of which workflows this person may see."""
    statement = select(Workflow).where(Workflow.organization_id == actor.organization_id)
    if not actor.can(Permission.WORKFLOW_VIEW_ALL):
        statement = statement.where(Workflow.created_by == actor.user_id)
    return statement


def get_visible_workflow(db: Session, actor: Actor, workflow_id: UUID) -> Workflow:
    workflow = db.scalar(visible_workflows(actor).where(Workflow.id == workflow_id))
    if workflow is None:
        raise NotFound("Workflow")
    return workflow


def list_workflows(
    db: Session,
    actor: Actor,
    status: str | None,
    q: str | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[Workflow, str]], int]:
    statement = visible_workflows(actor)
    if status:
        statement = statement.where(Workflow.status == status)
    if q:
        statement = statement.where(Workflow.request_text.icontains(q, autoescape=True))
    if date_from:
        statement = statement.where(
            Workflow.created_at >= datetime.combine(date_from, time.min, tzinfo=UTC)
        )
    if date_to:
        statement = statement.where(
            Workflow.created_at
            < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.execute(
        statement.join(User, User.id == Workflow.created_by)
        .add_columns(User.email)
        .order_by(Workflow.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [(r[0], r[1]) for r in rows], total


def can_retry(workflow: Workflow) -> bool:
    return (
        workflow.status == "failed"
        and not workflow.needs_clarification
        and workflow.error_category in RETRYABLE_ERROR_CATEGORIES
    )


def _require_control(actor: Actor, workflow: Workflow) -> None:
    allowed = actor.can(Permission.RETRY_ANY) or (
        actor.can(Permission.RETRY_OWN) and workflow.created_by == actor.user_id
    )
    if not allowed:
        raise Forbidden()


def retry_workflow(db: Session, actor: Actor, workflow_id: UUID) -> Workflow:
    workflow = get_visible_workflow(db, actor, workflow_id)
    _require_control(actor, workflow)
    db.refresh(workflow, with_for_update=True)
    if not can_retry(workflow):
        raise Conflict("This workflow cannot be retried. Fix the request and submit it again.")
    ensure_transition(workflow.status, "queued")
    workflow.status = "queued"
    workflow.finished_at = None
    record_audit(
        db,
        actor.organization_id,
        "workflow.retry_requested",
        str(workflow.id),
        "queued",
        actor.user_id,
        workflow.id,
    )
    db.commit()
    return workflow


def cancel_workflow(db: Session, actor: Actor, workflow_id: UUID) -> Workflow:
    workflow = get_visible_workflow(db, actor, workflow_id)
    _require_control(actor, workflow)
    db.refresh(workflow, with_for_update=True)
    ensure_transition(workflow.status, "cancelled")
    pending = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.workflow_id == workflow.id, ApprovalRequest.status == "pending")
        .with_for_update()
    ).all()
    for approval in pending:
        approval.status = "expired"
        approval.invalidation_reason = "the workflow was cancelled"
    workflow.status = "cancelled"
    workflow.finished_at = datetime.now(UTC)
    record_audit(
        db,
        actor.organization_id,
        "workflow.cancelled",
        str(workflow.id),
        "cancelled",
        actor.user_id,
        workflow.id,
    )
    db.commit()
    return workflow


def finish_workflow(
    db: Session, workflow: Workflow, status: str, message: str | None = None
) -> None:
    db.refresh(workflow)
    ensure_transition(workflow.status, status)
    workflow.status = status
    workflow.error_message = message
    workflow.finished_at = datetime.now(UTC)
    record_audit(
        db,
        workflow.organization_id,
        f"workflow.{status}",
        str(workflow.id),
        status,
        workflow.created_by,
        workflow.id,
    )
    enqueue_event(
        db,
        workflow.organization_id,
        f"workflow.{status}",
        {"workflow_id": str(workflow.id)},
    )
    metrics.WORKFLOW_FINISHED.labels(status).inc()
    metrics.WORKFLOW_DURATION.observe((workflow.finished_at - workflow.created_at).total_seconds())


def fail_workflow(
    db: Session, workflow: Workflow, category: str, message: str, needs_clarification: bool = False
) -> None:
    db.refresh(workflow)
    if workflow.status == "failed":
        return
    finish_workflow(db, workflow, "failed", message)
    workflow.error_category = category
    workflow.needs_clarification = needs_clarification
