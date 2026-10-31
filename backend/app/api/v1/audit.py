from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.auth.dependencies import Actor, Db, require_any
from app.auth.permissions import Permission
from app.models import AuditEvent, User
from app.schemas.common import Limit, Offset, Page, Schema

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(Schema):
    id: UUID
    created_at: datetime
    actor_email: str | None
    action: str
    target: str
    workflow_id: UUID | None
    result: str
    correlation_id: str | None
    metadata: dict


@router.get("", response_model=Page[AuditOut])
def list_audit(
    actor: Annotated[
        Actor, Depends(require_any(Permission.AUDIT_VIEW_ALL, Permission.AUDIT_VIEW_OWN))
    ],
    db: Db,
    actor_email: str | None = None,
    action: str | None = None,
    workflow_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[AuditOut]:
    statement = (
        select(AuditEvent, User.email)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(AuditEvent.organization_id == actor.organization_id)
    )
    if not actor.can(Permission.AUDIT_VIEW_ALL):
        statement = statement.where(AuditEvent.actor_id == actor.user_id)
    if actor_email:
        statement = statement.where(User.email == actor_email)
    if action:
        statement = statement.where(AuditEvent.action == action)
    if workflow_id:
        statement = statement.where(AuditEvent.workflow_id == workflow_id)
    if date_from:
        statement = statement.where(
            AuditEvent.created_at >= datetime.combine(date_from, time.min, tzinfo=UTC)
        )
    if date_to:
        statement = statement.where(
            AuditEvent.created_at
            < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.execute(
        statement.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return Page(
        items=[
            AuditOut(
                id=e.id,
                created_at=e.created_at,
                actor_email=email,
                action=e.action,
                target=e.target,
                workflow_id=e.workflow_id,
                result=e.result,
                correlation_id=e.correlation_id,
                metadata=e.event_metadata,
            )
            for e, email in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
