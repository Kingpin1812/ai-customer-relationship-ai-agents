"""Graph nodes. Each one calls a deterministic service; none of them talks to the model but `plan`."""

import functools
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agents.planner import build_plan
from app.agents.state import WorkflowState
from app.core.config import get_settings
from app.core.errors import ClarificationNeeded, ErrorCategory
from app.db.session import SessionLocal
from app.integrations.crm import get_crm_adapter
from app.models import ApprovalRequest, Customer, EmailDraft, Invoice, Workflow, WorkflowStep
from app.observability import metrics
from app.services.approvals.service import (
    ApprovalInvalidated,
    create_approval,
    execute_approved,
    latest_approval,
)
from app.services.audit.service import record_audit
from app.services.invoices.calculator import LineInput
from app.services.invoices.service import create_draft_invoice
from app.services.reliability.errors import IntegrationError
from app.services.reliability.operations import OperationContext, run_operation
from app.services.reports.service import generate_report
from app.services.workflows.service import finish_workflow
from app.services.workflows.state_machine import ensure_transition

tracer = trace.get_tracer("workflow.graph")

_FAULTS: dict[str, dict] = {
    "crm_timeout": {"crm_timeouts": 2},
    "crm_down": {"crm_timeouts": 1_000_000},
    "email_unknown_sent": {"email_unknown_sent": True},
    "email_unknown_lost": {"email_unknown_lost": True},
}


def faults_for(workflow: Workflow) -> dict:
    """Simulated provider faults. Inert unless fault injection is on (refused in production)."""
    if not get_settings().enable_fault_injection:
        return {}
    return _FAULTS.get(workflow.context.get("simulate", ""), {})


def _begin_step(db: Session, workflow: Workflow, key: str) -> None:
    now = datetime.now(UTC)
    db.execute(
        insert(WorkflowStep)
        .values(
            organization_id=workflow.organization_id,
            workflow_id=workflow.id,
            step_key=key,
            status="running",
            started_at=now,
            runs=1,
        )
        .on_conflict_do_update(
            index_elements=["workflow_id", "step_key"],
            set_={
                "status": "running",
                "error": None,
                "finished_at": None,
                "runs": WorkflowStep.runs + 1,
            },
        )
    )
    db.commit()


def _end_step(
    db: Session,
    workflow: Workflow,
    key: str,
    status: str,
    output: str | None = None,
    error: str | None = None,
) -> None:
    step = db.scalar(
        select(WorkflowStep)
        .where(WorkflowStep.workflow_id == workflow.id, WorkflowStep.step_key == key)
        .execution_options(populate_existing=True)
    )
    step.status = status
    step.output_summary = output
    step.error = error
    step.finished_at = datetime.now(UTC)


def step(key: str) -> Callable:
    """Make a node traceable, audited and visible on the timeline."""

    def decorator(fn: Callable[[Session, Workflow, WorkflowState], tuple[dict, str]]) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: WorkflowState) -> dict:
            started = time.perf_counter()
            with tracer.start_as_current_span(f"node.{key}") as span, SessionLocal() as db:
                span.set_attribute("workflow.id", state["workflow_id"])
                workflow = db.get(Workflow, UUID(state["workflow_id"]))
                _begin_step(db, workflow, key)
                try:
                    update, summary = fn(db, workflow, state)
                except Exception as exc:
                    db.rollback()
                    safe = getattr(exc, "message", "This step failed unexpectedly.")
                    _end_step(db, workflow, key, "failed", error=safe)
                    record_audit(
                        db,
                        workflow.organization_id,
                        f"step.{key}",
                        str(workflow.id),
                        "failed",
                        workflow.created_by,
                        workflow.id,
                        {"category": str(getattr(exc, "category", "internal_error"))},
                    )
                    db.commit()
                    span.record_exception(exc)
                    raise
                _end_step(db, workflow, key, "succeeded", output=summary)
                record_audit(
                    db,
                    workflow.organization_id,
                    f"step.{key}",
                    str(workflow.id),
                    "succeeded",
                    workflow.created_by,
                    workflow.id,
                )
                db.commit()
                metrics.STEP_DURATION.labels(key).observe(time.perf_counter() - started)
                return update

        return wrapper

    return decorator


@step("plan")
def plan_node(db: Session, workflow: Workflow, state: WorkflowState) -> tuple[dict, str]:
    plan, source = build_plan(workflow.request_text, workflow.context)
    dumped = plan.model_dump(mode="json")
    workflow.plan = dumped
    workflow.planner_source = source
    record_audit(
        db,
        workflow.organization_id,
        "workflow.plan_created",
        str(workflow.id),
        "succeeded",
        workflow.created_by,
        workflow.id,
        {"planner": source, "actions": dumped["actions"]},
    )
    db.commit()
    if plan.clarifications:
        raise ClarificationNeeded(" ".join(plan.clarifications))
    return {"plan": dumped}, f"Planned by {source}: {', '.join(plan.actions)}"


@step("resolve_customer")
def resolve_customer_node(
    db: Session, workflow: Workflow, state: WorkflowState
) -> tuple[dict, str]:
    reference = state["plan"]["customer_reference"]
    crm = get_crm_adapter(workflow.organization_id, faults_for(workflow))
    ctx = OperationContext(workflow.organization_id, workflow.id, workflow.created_by)
    result = run_operation(
        db,
        ctx,
        crm.provider,
        "search_customer",
        f"wf:{workflow.id}:search_customer",
        lambda: {
            "matches": [
                {"id": c.provider_customer_id, "name": c.name, "email": c.email}
                for c in crm.search(reference)
            ]
        },
    )
    matches = result["matches"]
    if not matches:
        raise ClarificationNeeded(f"No customer named '{reference}' was found in the CRM.")
    if len(matches) > 1:
        names = ", ".join(m["name"] for m in matches)
        raise ClarificationNeeded(f"'{reference}' matches several customers: {names}. Which one?")

    match = matches[0]
    db.execute(
        insert(Customer)
        .values(
            organization_id=workflow.organization_id,
            provider=crm.provider,
            provider_customer_id=match["id"],
            name=match["name"],
            email=match["email"],
            created_at=datetime.now(UTC),
        )
        .on_conflict_do_update(
            index_elements=["organization_id", "provider", "provider_customer_id"],
            set_={"name": match["name"], "email": match["email"], "sync_status": "synced"},
        )
    )
    customer = db.scalar(
        select(Customer)
        .where(
            Customer.organization_id == workflow.organization_id,
            Customer.provider == crm.provider,
            Customer.provider_customer_id == match["id"],
        )
        .execution_options(populate_existing=True)
    )
    workflow.customer_id = customer.id
    db.commit()
    return {}, f"Resolved to {customer.name} ({customer.provider_customer_id})"


@step("create_invoice")
def create_invoice_node(db: Session, workflow: Workflow, state: WorkflowState) -> tuple[dict, str]:
    plan = state["plan"]
    lines = [
        LineInput(i["description"], Decimal(str(i["quantity"])), Decimal(str(i["unit_price"])))
        for i in plan["line_items"]
    ]
    invoice = create_draft_invoice(
        db,
        workflow.organization_id,
        workflow.id,
        db.get(Customer, workflow.customer_id),
        lines,
        plan.get("currency") or get_settings().default_currency,
    )
    record_audit(
        db,
        workflow.organization_id,
        "invoice.drafted",
        invoice.invoice_number,
        "succeeded",
        workflow.created_by,
        workflow.id,
        {"currency": invoice.currency, "total": f"{invoice.total:.2f}"},
    )
    db.commit()
    return {}, f"Draft {invoice.invoice_number}: {invoice.currency} {invoice.total:,.2f}"


@step("generate_report")
def generate_report_node(db: Session, workflow: Workflow, state: WorkflowState) -> tuple[dict, str]:
    if get_settings().enable_fault_injection and workflow.context.get("simulate") == "report_down":
        raise IntegrationError(ErrorCategory.PROVIDER_SERVER, "The reporting store is unavailable.")
    spec = state["plan"]["report"]
    report = generate_report(
        db, workflow.organization_id, workflow.id, spec["type"], {"period": spec["period"]}
    )
    record_audit(
        db,
        workflow.organization_id,
        "report.generated",
        report.report_type,
        "succeeded",
        workflow.created_by,
        workflow.id,
        {
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
        },
    )
    db.commit()
    return {}, f"{report.report_type}: {report.period_start} to {report.period_end}"


@step("draft_email")
def draft_email_node(db: Session, workflow: Workflow, state: WorkflowState) -> tuple[dict, str]:
    customer = db.get(Customer, workflow.customer_id)
    invoice = db.scalar(
        select(Invoice).where(
            Invoice.organization_id == workflow.organization_id, Invoice.workflow_id == workflow.id
        )
    )
    # Fixed templates over verified fields. No model text and no CRM notes reach the customer.
    if invoice:
        subject = f"Invoice {invoice.invoice_number}"
        body = (
            f"Dear {customer.name},\n\n"
            f"Please find attached invoice {invoice.invoice_number} for "
            f"{invoice.currency} {invoice.total:,.2f}, due on {invoice.due_date.isoformat()}.\n\n"
            "Kind regards,\nAccounts team"
        )
    else:
        subject = "An update on your account"
        body = (
            f"Dear {customer.name},\n\nWe have an update on your account and will follow up "
            "shortly.\n\nKind regards,\nAccounts team"
        )
    db.execute(
        insert(EmailDraft)
        .values(
            organization_id=workflow.organization_id,
            workflow_id=workflow.id,
            customer_id=customer.id,
            recipient=customer.email,
            subject=subject,
            body=body,
            artifact_ids=[str(invoice.artifact_id)] if invoice and invoice.artifact_id else [],
            status="draft",
            created_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "workflow_id"])
    )
    db.commit()
    return {}, f"Draft to {customer.email}"


@step("request_approval")
def request_approval_node(
    db: Session, workflow: Workflow, state: WorkflowState
) -> tuple[dict, str]:
    approval = latest_approval(db, workflow)
    if approval is None or approval.status == "expired":
        approval = create_approval(db, workflow)
    if workflow.status != "waiting_for_approval":  # already paused if a crash forced a re-run
        ensure_transition(workflow.status, "waiting_for_approval")
        workflow.status = "waiting_for_approval"
    db.commit()
    return {"approval_id": str(approval.id)}, approval.summary


@step("execute_actions")
def execute_actions_node(db: Session, workflow: Workflow, state: WorkflowState) -> tuple[dict, str]:
    approval = db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.id == UUID(state["approval_id"]),
            ApprovalRequest.organization_id == workflow.organization_id,
        )
    )
    try:
        execute_approved(db, workflow, approval, faults_for(workflow))
    except ApprovalInvalidated as exc:
        return {"needs_new_approval": True}, exc.message
    return (
        {"needs_new_approval": False},
        f"Executed {len(approval.payload['actions'])} approved action(s)",
    )


@step("complete")
def complete_node(db: Session, workflow: Workflow, state: WorkflowState) -> tuple[dict, str]:
    finish_workflow(db, workflow, "succeeded")
    db.commit()
    return {}, "Workflow finished"


@step("stop_after_decision")
def stop_node(db: Session, workflow: Workflow, state: WorkflowState) -> tuple[dict, str]:
    approval = db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.id == UUID(state["approval_id"]),
            ApprovalRequest.organization_id == workflow.organization_id,
        )
    )
    reason = approval.reason or "No reason given."
    prefix = "Changes requested" if approval.status == "changes_requested" else "Rejected"
    finish_workflow(db, workflow, "rejected", message=f"{prefix}: {reason}")
    db.commit()
    return {}, f"{prefix}. No protected action ran."
