"""The single way a workflow moves forward. Safe to call repeatedly, from any process."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from langgraph.types import Command
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import text

from app.agents.graph import get_graph
from app.core.context import get_correlation_id, set_correlation_id
from app.core.errors import AppError, ClarificationNeeded, ErrorCategory
from app.db.session import SessionLocal, engine
from app.models import Workflow
from app.services.approvals.service import latest_approval
from app.services.audit.service import record_audit
from app.services.workflows.service import fail_workflow
from app.services.workflows.state_machine import ensure_transition

log = structlog.get_logger()
tracer = trace.get_tracer("workflow.runner")
_PROPAGATOR = TraceContextTextMapPropagator()


def _prepare(workflow_id: UUID) -> tuple[bool, dict, str | None, dict]:
    """Move queued work to running. Returns (should_run, initial_state, correlation_id, trace)."""
    with SessionLocal() as db:
        workflow = db.get(Workflow, workflow_id, with_for_update=True)
        if workflow is None or workflow.status not in ("queued", "running", "waiting_for_approval"):
            return False, {}, None, {}
        if workflow.status == "queued":
            ensure_transition("queued", "running")
            workflow.status = "running"
            workflow.started_at = workflow.started_at or datetime.now(UTC)
            workflow.error_category = None
            workflow.error_message = None
            set_correlation_id(workflow.correlation_id)
            record_audit(
                db,
                workflow.organization_id,
                "workflow.started",
                str(workflow.id),
                "running",
                workflow.created_by,
                workflow.id,
            )
            db.commit()
        return (
            True,
            {
                "workflow_id": str(workflow.id),
                "organization_id": str(workflow.organization_id),
                "actor_id": str(workflow.created_by),
            },
            workflow.correlation_id,
            dict(workflow.trace_context or {}),
        )


def _resume_command(workflow_id: UUID) -> Command | None:
    """Read the recorded decision. No pending decision means stay paused."""
    with SessionLocal() as db:
        workflow = db.get(Workflow, workflow_id)
        approval = latest_approval(db, workflow)
        if approval is None or approval.status in ("pending", "expired"):
            return None
        return Command(resume={"approval_id": str(approval.id), "decision": approval.status})


def _run_graph(workflow_id: UUID, initial_state: dict) -> None:
    config = {"configurable": {"thread_id": str(workflow_id)}}
    graph = get_graph()
    snapshot = graph.get_state(config)
    graph_input: Any
    if "await_approval" in snapshot.next:
        graph_input = _resume_command(workflow_id)
        if graph_input is None:
            return
    elif snapshot.next:
        graph_input = None  # continue from the last durable checkpoint
    elif snapshot.values:
        return  # already finished
    else:
        graph_input = initial_state
    graph.invoke(graph_input, config)


def advance_workflow(workflow_id: UUID | str) -> None:
    workflow_id = UUID(str(workflow_id))
    # A session-level advisory lock serializes runs of one workflow across all workers.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock:
        lock.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:k, 0))"), {"k": str(workflow_id)}
        )
        try:
            _advance_locked(workflow_id)
        finally:
            lock.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:k, 0))"), {"k": str(workflow_id)}
            )


def _advance_locked(workflow_id: UUID) -> None:
    should_run, initial_state, correlation_id, trace_context = _prepare(workflow_id)
    if not should_run:
        return
    previous_correlation_id = get_correlation_id()
    set_correlation_id(correlation_id)
    token = otel_context.attach(_PROPAGATOR.extract(trace_context))
    try:
        with tracer.start_as_current_span("workflow.advance") as span:
            span.set_attribute("workflow.id", str(workflow_id))
            span.set_attribute("correlation.id", correlation_id or "")
            try:
                _run_graph(workflow_id, initial_state)
            except AppError as exc:
                _record_failure(
                    workflow_id,
                    exc.category.value,
                    exc.message,
                    isinstance(exc, ClarificationNeeded),
                )
            except Exception as exc:  # noqa: BLE001 - a worker must always record the failure
                log.error("workflow_crashed", error_type=type(exc).__name__, exc_info=exc)
                span.record_exception(exc)
                _record_failure(
                    workflow_id,
                    ErrorCategory.INTERNAL.value,
                    "Something went wrong while running this workflow. You can try again.",
                    False,
                )
    finally:
        otel_context.detach(token)
        set_correlation_id(previous_correlation_id)


def _record_failure(workflow_id: UUID, category: str, message: str, clarify: bool) -> None:
    with SessionLocal() as db:
        fail_workflow(db, db.get(Workflow, workflow_id), category, message, clarify)
        db.commit()
