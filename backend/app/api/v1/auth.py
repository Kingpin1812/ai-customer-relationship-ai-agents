from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.dependencies import CurrentActor, Db
from app.auth.permissions import permissions_for
from app.auth.tokens import issue_dev_token
from app.core.config import Settings, get_settings
from app.core.errors import NotFound, Unauthenticated
from app.models import Organization, User
from app.services.audit.service import record_audit

router = APIRouter(prefix="/auth", tags=["auth"])


class DevLoginRequest(BaseModel):
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class MeResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    organization_id: str
    organization_name: str
    role: str
    permissions: list[str]
    fault_injection_enabled: bool
    sandbox_enabled: bool


@router.post("/dev-login", response_model=TokenResponse, summary="Development sign-in only")
def dev_login(
    body: DevLoginRequest, db: Db, settings: Annotated[Settings, Depends(get_settings)]
) -> TokenResponse:
    if settings.auth_mode != "dev":
        raise NotFound("Endpoint")
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or user.status != "active":
        raise Unauthenticated("That demo account does not exist.")
    token, ttl = issue_dev_token(user.identity_subject)
    record_audit(db, user.organization_id, "auth.dev_login", user.email, "success", user.id)
    db.commit()
    return TokenResponse(access_token=token, expires_in=ttl)


@router.get("/me", response_model=MeResponse)
def me(
    actor: CurrentActor, db: Db, settings: Annotated[Settings, Depends(get_settings)]
) -> MeResponse:
    user = db.get(User, actor.user_id)
    org = db.get(Organization, actor.organization_id)
    return MeResponse(
        user_id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        organization_id=str(org.id),
        organization_name=org.name,
        role=actor.role,
        permissions=permissions_for(actor.role),
        fault_injection_enabled=settings.enable_fault_injection,
        sandbox_enabled=settings.environment != "production",
    )
