from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.auth.dependencies import Actor, Db, require
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.core.errors import NotFound
from app.models import MockEmail
from app.schemas.common import Limit, Offset, Page, Schema

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


class SandboxEmail(Schema):
    provider_message_id: str
    recipient: str
    subject: str
    body: str
    attachments: list[dict]
    sent_at: datetime


@router.get("/emails", response_model=Page[SandboxEmail])
def sandbox_emails(
    actor: Annotated[Actor, Depends(require(Permission.BUSINESS_VIEW_ALL))],
    db: Db,
    limit: Limit = 25,
    offset: Offset = 0,
) -> Page[SandboxEmail]:
    """What the mock mail provider received. Proves exactly-one-send during a demo."""
    if get_settings().environment == "production":
        raise NotFound("Endpoint")
    scoped = select(MockEmail).where(MockEmail.organization_id == actor.organization_id)
    total = db.scalar(select(func.count()).select_from(scoped.subquery()))
    rows = db.scalars(scoped.order_by(MockEmail.sent_at.desc()).limit(limit).offset(offset)).all()
    return Page(
        items=[SandboxEmail.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
