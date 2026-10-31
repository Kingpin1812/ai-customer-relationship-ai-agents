from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Date

from app.auth.dependencies import Actor, CurrentActor, Db
from app.auth.permissions import Permission
from app.models import ApprovalRequest, AuditEvent, Integration, User
from app.schemas.common import Schema
from app.services.workflows.service import visible_workflows

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_STATUSES = (
    "queued",
    "running",
    "waiting_for_approval",
    "succeeded",
    "failed",
    "rejected",
    "cancelled",
)


class ActivityItem(Schema):
    action: str
    target: str
    result: str
    workflow_id: UUID | None
    actor_email: str | None
    created_at: datetime


class IntegrationHealth(Schema):
    provider: str
    kind: str
    status: str
    last_success_at: datetime | None


class DayCount(BaseModel):
    day: str
    succeeded: int
    failed: int


class DashboardSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    pending_approvals: int
    recent_activity: list[ActivityItem]
    integrations: list[IntegrationHealth]
    trend: list[DayCount]


def build_summary(db: Session, actor: Actor) -> DashboardSummary:
    visible = visible_workflows(actor).subquery()
    counts: dict[str, int] = dict(
        db.execute(select(visible.c.status, func.count()).group_by(visible.c.status)).all()
    )
    by_status = {status: counts.get(status, 0) for status in _STATUSES}

    pending = (
        select(func.count())
        .select_from(ApprovalRequest)
        .where(
            ApprovalRequest.organization_id == actor.organization_id,
            ApprovalRequest.status == "pending",
            ApprovalRequest.workflow_id.in_(select(visible.c.id)),
        )
    )

    activity = (
        select(AuditEvent, User.email)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(
            AuditEvent.organization_id == actor.organization_id,
            AuditEvent.action.not_like("step.%"),
            AuditEvent.action.not_like("auth.%"),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(10)
    )
    if not actor.can(Permission.AUDIT_VIEW_ALL):
        activity = activity.where(AuditEvent.actor_id == actor.user_id)

    integrations = db.scalars(
        select(Integration)
        .where(Integration.organization_id == actor.organization_id)
        .order_by(Integration.provider)
    ).all()

    today = datetime.now(UTC).date()
    since = today - timedelta(days=6)
    day = cast(visible.c.created_at, Date)
    rows = db.execute(
        select(day, visible.c.status, func.count())
        .where(day >= since, visible.c.status.in_(("succeeded", "failed")))
        .group_by(day, visible.c.status)
    ).all()
    per_day: dict = {(d, s): n for d, s, n in rows}
    trend = [
        DayCount(
            day=(since + timedelta(days=i)).isoformat(),
            succeeded=per_day.get((since + timedelta(days=i), "succeeded"), 0),
            failed=per_day.get((since + timedelta(days=i), "failed"), 0),
        )
        for i in range(7)
    ]

    return DashboardSummary(
        total=sum(by_status.values()),
        by_status=by_status,
        pending_approvals=db.scalar(pending),
        recent_activity=[
            ActivityItem(
                action=e.action,
                target=e.target,
                result=e.result,
                workflow_id=e.workflow_id,
                actor_email=email,
                created_at=e.created_at,
            )
            for e, email in db.execute(activity)
        ],
        integrations=[IntegrationHealth.model_validate(i) for i in integrations],
        trend=trend,
    )


@router.get("/summary", response_model=DashboardSummary)
def summary(actor: CurrentActor, db: Db) -> DashboardSummary:
    return build_summary(db, actor)
