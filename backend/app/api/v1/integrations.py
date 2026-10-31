from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Actor, CurrentActor, Db, require
from app.auth.permissions import Permission
from app.core.errors import NotFound
from app.models import Integration
from app.schemas.common import Page, Schema
from app.services.audit.service import record_audit

router = APIRouter(prefix="/integrations", tags=["integrations"])

Admin = Annotated[Actor, Depends(require(Permission.INTEGRATION_CONFIGURE))]


class IntegrationOut(Schema):
    id: UUID
    provider: str
    kind: str
    status: str
    scopes: list[str]
    last_success_at: datetime | None


@router.get("", response_model=Page[IntegrationOut])
def list_integrations(actor: CurrentActor, db: Db) -> Page[IntegrationOut]:
    rows = db.scalars(
        select(Integration)
        .where(Integration.organization_id == actor.organization_id)
        .order_by(Integration.provider)
    ).all()
    return Page(
        items=[IntegrationOut.model_validate(r) for r in rows],
        total=len(rows),
        limit=len(rows),
        offset=0,
    )


def _set_status(db: Session, actor: Actor, provider: str, status: str) -> IntegrationOut:
    integration = db.scalar(
        select(Integration).where(
            Integration.organization_id == actor.organization_id, Integration.provider == provider
        )
    )
    if integration is None:
        raise NotFound("Integration")
    integration.status = status
    record_audit(
        db,
        actor.organization_id,
        f"integration.{status}",
        provider,
        "success",
        actor.user_id,
    )
    db.commit()
    return IntegrationOut.model_validate(integration)


@router.post("/{provider}/connect", response_model=IntegrationOut)
def connect(provider: str, actor: Admin, db: Db) -> IntegrationOut:
    """Mock providers connect immediately. A real provider would begin its OAuth flow here."""
    return _set_status(db, actor, provider, "connected")


@router.post("/{provider}/disconnect", response_model=IntegrationOut)
def disconnect(provider: str, actor: Admin, db: Db) -> IntegrationOut:
    return _set_status(db, actor, provider, "disconnected")
