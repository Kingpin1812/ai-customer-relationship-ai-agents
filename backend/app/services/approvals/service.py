from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Actor
from app.auth.permissions import Permission, role_has
from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound
from app.integrations.crm import get_crm_adapter
from app.integrations.email import get_email_adapter
from app.integrations.email.base import OutgoingEmail
from app.models import ApprovalRequest, EmailDraft, Invoice, Membership, User, Workflow
from app.observability import metrics
from app.services.approvals.snapshot import build_snapshot, describe, payload_hash
from app.services.artifacts import read_artifact
from app.services.audit.service import record_audit
from app.services.invoices.service import issue_invoice
from app.services.reliability.operations import OperationContext, run_operation
from app.services.reliability.outbox import enqueue_event
from app.services.workflows.state_machine import ensure_transition

Decision = Literal["approve", "reject", "request_changes"]
_STATUS_FOR = {"approve": "approved", "reject": "rejected", "request_changes": "changes_requested"}


def create_approval(db: Session, workflow: Workflow) -> ApprovalRequest:
    snapshot = build_snapshot(db, workflow)
    send = next((a for a in snapshot["actions"] if a["type"] == "send_email"), None)
    if send:
        draft = db.scalar(
            select(EmailDraft).where(
                EmailDraft.organization_id == workflow.organization_id,
                EmailDraft.workflow_id == workflow.id,
            )
        )
        draft.recipient = send["to"]
    external = any(a["type"] in ("send_email", "issue_invoice") for a in snapshot["actions"])
    approval = ApprovalRequest(
        organization_id=workflow.organization_id,
        workflow_id=workflow.id,
        action_type=snapshot["action_type"],
        summary=describe(snapshot),
        risk_level="high" if external else "medium",
        payload=snapshot,
        payload_hash=payload_hash(snapshot),
        requested_by=workflow.created_by,
        expires_at=datetime.now(UTC) + timedelta(hours=get_settings().approval_ttl_hours),
    )
    db.add(approval)
    db.flush()
    record_audit(
        db,
        workflow.organization_id,
        "approval.requested",
        str(approval.id),
        "pending",
        workflow.created_by,
        workflow.id,
        {"payload_hash": approval.payload_hash},
    )
    return approval


def latest_approval(db: Session, workflow: Workflow) -> ApprovalRequest | None:
    return db.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.organization_id == workflow.organization_id,
            ApprovalRequest.workflow_id == workflow.id,
        )
        .order_by(ApprovalRequest.created_at.desc())
        .limit(1)
    )


class ApprovalInvalidated(Conflict):
    """The approval no longer covers the action. Nothing ran, and the graph asks for a new one."""


def _expire(db: Session, approval: ApprovalRequest, reason: str, actor_id: UUID | None) -> None:
    approval.status = "expired"
    approval.invalidation_reason = reason
    record_audit(
        db,
        approval.organization_id,
        "approval.expired",
        str(approval.id),
        "expired",
        actor_id,
        approval.workflow_id,
        {"reason": reason},
    )


def decide(
    db: Session, actor: Actor, approval_id: UUID, decision: Decision, reason: str | None
) -> ApprovalRequest:
    approval = db.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if approval is None:
        raise NotFound("Approval")
    actor.require(Permission.APPROVE)
    if not get_settings().allow_self_approval and approval.requested_by == actor.user_id:
        raise Forbidden("You cannot approve your own request.")
    if approval.status != "pending":
        raise Conflict(f"This approval is already {approval.status}.")

    workflow = db.scalar(
        select(Workflow).where(Workflow.id == approval.workflow_id).with_for_update()
    )
    now = datetime.now(UTC)
    if now >= approval.expires_at:
        _expire(db, approval, "approval window passed", actor.user_id)
        ensure_transition(workflow.status, "failed")
        workflow.status = "failed"
        workflow.error_category = "validation_error"
        workflow.error_message = "The approval window passed. Submit the request again."
        workflow.finished_at = now
        db.commit()
        raise Conflict("This approval has expired.")

    if decision == "approve":
        current_hash = payload_hash(build_snapshot(db, workflow))
        if current_hash != approval.payload_hash:
            _expire(
                db, approval, "the action changed after this approval was requested", actor.user_id
            )
            db.flush()
            replacement = create_approval(db, workflow)
            db.commit()
            raise Conflict(
                "The action changed since this was requested, so a new approval was created. "
                "Review it before approving.",
                {"new_approval_id": str(replacement.id)},
            )

    ensure_transition(workflow.status, "running")
    approval.status = _STATUS_FOR[decision]
    approval.decided_by = actor.user_id
    approval.decided_at = now
    approval.reason = reason
    workflow.status = "running"
    record_audit(
        db,
        actor.organization_id,
        f"approval.{approval.status}",
        str(approval.id),
        approval.status,
        actor.user_id,
        workflow.id,
        {"payload_hash": approval.payload_hash, "reason": reason},
    )
    enqueue_event(
        db,
        actor.organization_id,
        "approval.decided",
        {"approval_id": str(approval.id), "status": approval.status},
    )
    metrics.APPROVAL_WAIT.labels(approval.status).observe(
        (now - approval.created_at).total_seconds()
    )
    db.commit()
    return approval


def _invalidate(db: Session, approval: ApprovalRequest, reason: str) -> None:
    _expire(db, approval, reason, None)
    db.commit()
    raise ApprovalInvalidated(f"This needs a new approval because {reason}.")


def verify_for_execution(db: Session, workflow: Workflow, approval: ApprovalRequest) -> None:
    """The last gate before side effects. Any doubt stops execution."""
    if approval.status != "approved" or approval.workflow_id != workflow.id:
        raise Forbidden("This action has no valid approval.")
    membership = db.get(Membership, (approval.decided_by, workflow.organization_id))
    approver = db.get(User, approval.decided_by)
    if (
        membership is None
        or approver is None
        or approver.status != "active"
        or not role_has(membership.role, Permission.APPROVE)
    ):
        raise Forbidden("The approver no longer has permission, so this action was stopped.")
    if payload_hash(approval.payload) != approval.payload_hash:
        raise Conflict("The approved action was altered, so it was stopped.")
    if datetime.now(UTC) >= approval.expires_at:
        _invalidate(db, approval, "the approval window passed before it could run")
    if payload_hash(build_snapshot(db, workflow)) != approval.payload_hash:
        _invalidate(db, approval, "the action changed after it was approved")


def execute_approved(
    db: Session, workflow: Workflow, approval: ApprovalRequest, faults: dict | None = None
) -> None:
    """Run the stored payload and nothing else. Stable keys make every action safe to re-enter."""
    verify_for_execution(db, workflow, approval)
    ctx = OperationContext(workflow.organization_id, workflow.id, approval.decided_by)
    key_suffix = approval.payload_hash[:16]
    crm = get_crm_adapter(workflow.organization_id, faults)
    email = get_email_adapter(workflow.organization_id, faults)

    for action in approval.payload["actions"]:
        if action["type"] == "issue_invoice":
            invoice = db.scalar(
                select(Invoice).where(
                    Invoice.organization_id == workflow.organization_id,
                    Invoice.id == UUID(action["invoice_id"]),
                )
            )
            issue_invoice(db, invoice)
            record_audit(
                db,
                workflow.organization_id,
                "invoice.issued",
                invoice.invoice_number,
                "succeeded",
                approval.decided_by,
                workflow.id,
            )
            db.commit()
        elif action["type"] == "update_crm_note":
            key = f"wf:{workflow.id}:crm_note:{key_suffix}"
            customer_ref = action["provider_customer_id"]
            run_operation(
                db,
                ctx,
                crm.provider,
                "update_crm_note",
                key,
                partial(crm.update_note, customer_ref, action["note"], key),
                reconcile=partial(crm.note_applied, customer_ref, key),
            )
        elif action["type"] == "send_email":
            key = f"wf:{workflow.id}:email:{key_suffix}"
            for attachment in action["attachments"]:
                read_artifact(db, workflow.organization_id, UUID(attachment["artifact_id"]))
            message = OutgoingEmail(
                action["to"], action["subject"], action["body"], action["attachments"]
            )
            result = run_operation(
                db,
                ctx,
                email.provider,
                "send_email",
                key,
                partial(email.send, message, key),
                reconcile=partial(email.find_by_idempotency_key, key),
            )
            draft = db.scalar(
                select(EmailDraft).where(
                    EmailDraft.organization_id == workflow.organization_id,
                    EmailDraft.workflow_id == workflow.id,
                )
            )
            draft.status = result.get("delivery_status", "sent")
            draft.provider_message_id = result.get("provider_message_id")
            draft.sent_at = datetime.now(UTC)
            db.commit()
