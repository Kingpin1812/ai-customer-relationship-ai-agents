from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import Permission, role_has
from app.auth.tokens import verify_token
from app.core.errors import Forbidden, Unauthenticated
from app.db.session import get_db
from app.models import Membership, User

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    organization_id: UUID
    role: str

    def can(self, permission: Permission) -> bool:
        return role_has(self.role, permission)

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise Forbidden()


Db = Annotated[Session, Depends(get_db)]


def current_actor(
    db: Db,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    x_organization_id: Annotated[UUID | None, Header()] = None,
) -> Actor:
    if credentials is None:
        raise Unauthenticated()
    subject = verify_token(credentials.credentials)
    user = db.scalar(select(User).where(User.identity_subject == subject))
    if user is None or user.status != "active":
        raise Unauthenticated("Your account is not active.")
    organization_id = x_organization_id or user.organization_id
    membership = db.get(Membership, (user.id, organization_id))
    if membership is None:
        raise Forbidden("You are not a member of this organization.")
    return Actor(user.id, organization_id, membership.role)


CurrentActor = Annotated[Actor, Depends(current_actor)]


def require(permission: Permission) -> Callable[[Actor], Actor]:
    def _check(actor: CurrentActor) -> Actor:
        actor.require(permission)
        return actor

    return _check


def require_any(*permissions: Permission) -> Callable[[Actor], Actor]:
    def _check(actor: CurrentActor) -> Actor:
        if not any(actor.can(p) for p in permissions):
            raise Forbidden()
        return actor

    return _check
