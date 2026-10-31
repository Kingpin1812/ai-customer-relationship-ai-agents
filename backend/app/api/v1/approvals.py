from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import Actor, CurrentActor, Db
from app.auth.permissions import Permission
from app.core.errors import NotFound
from app.models import ApprovalRequest, User, Workflow
from app.schemas.approvals import ApprovalOut, ApprovalStatus, DecisionIn
from app.schemas.common import Limit, Offset, Page
from app.services.approvals.service import decide
from app.workers.executor import submit_advance

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _visible(actor: Actor):
    statement = select(ApprovalRequest).where(
        ApprovalRequest.organization_id == actor.organization_id
    )
    if not actor.can(Permission.WORKFLOW_VIEW_ALL):
        statement = statement.join(Workflow, Workflow.id == ApprovalRequest.workflow_id).where(
            Workflow.created_by == actor.user_id
        )
    return statement


def _out(db: Session, approval: ApprovalRequest) -> ApprovalOut:
    actions = approval.payload.get("actions", [])
    invoice = next((a for a in actions if a["type"] == "issue_invoice"), None)
    email = next((a for a in actions if a["type"] == "send_email"), None)
    decided_by = db.get(User, approval.decided_by) if approval.decided_by else None
    return ApprovalOut(
        id=approval.id,
        workflow_id=approval.workflow_id,
        action_type=approval.action_type,
        summary=approval.summary,
        risk_level=approval.risk_level,
        status=approval.status,
        payload=approval.payload,
        payload_hash=approval.payload_hash,
        amount=invoice["total"] if invoice else None,
        currency=invoice["currency"] if invoice else None,
        recipient=email["to"] if email else None,
        requested_by_email=db.get(User, approval.requested_by).email,
        decided_by_email=decided_by.email if decided_by else None,
        decided_at=approval.decided_at,
        reason=approval.reason,
        invalidation_reason=approval.invalidation_reason,
        expires_at=approval.expires_at,
        created_at=approval.created_at,
    )


@router.get("", response_model=Page[ApprovalOut])
def list_approvals(
    actor: CurrentActor,
    db: Db,
    status: ApprovalStatus | None = None,
    limit: Limit = 25,
    offset: Offset = 0,
) -> Page[ApprovalOut]:
    statement = _visible(actor)
    if status:
        statement = statement.where(ApprovalRequest.status == status)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(
        statement.order_by(ApprovalRequest.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return Page(items=[_out(db, a) for a in rows], total=total, limit=limit, offset=offset)


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: UUID, actor: CurrentActor, db: Db) -> ApprovalOut:
    approval = db.scalar(_visible(actor).where(ApprovalRequest.id == approval_id))
    if approval is None:
        raise NotFound("Approval")
    return _out(db, approval)


@router.post("/{approval_id}/decision", response_model=ApprovalOut)
def post_decision(approval_id: UUID, body: DecisionIn, actor: CurrentActor, db: Db) -> ApprovalOut:
    approval = decide(db, actor, approval_id, body.decision, body.reason)
    out = _out(db, approval)
    submit_advance(approval.workflow_id)
    return out
