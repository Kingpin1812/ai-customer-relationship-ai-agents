from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth.dependencies import Actor, Db, require
from app.auth.permissions import Permission
from app.core.errors import Conflict, NotFound
from app.models import Membership, User
from app.services.audit.service import record_audit

router = APIRouter(prefix="/members", tags=["members"])

Role = Literal["admin", "manager", "operator", "viewer"]
Admin = Annotated[Actor, Depends(require(Permission.USER_MANAGE))]


class MemberOut(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    role: Role
    status: str


class MemberList(BaseModel):
    items: list[MemberOut]


class RoleChange(BaseModel):
    role: Role


@router.get("", response_model=MemberList)
def list_members(actor: Admin, db: Db) -> MemberList:
    rows = db.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == actor.organization_id)
        .order_by(User.email)
    ).all()
    return MemberList(
        items=[
            MemberOut(
                user_id=u.id,
                email=u.email,
                display_name=u.display_name,
                role=m.role,
                status=u.status,
            )
            for u, m in rows
        ]
    )


@router.patch("/{user_id}", response_model=MemberOut)
def change_role(user_id: UUID, body: RoleChange, actor: Admin, db: Db) -> MemberOut:
    membership = db.scalar(
        select(Membership)
        .where(Membership.user_id == user_id, Membership.organization_id == actor.organization_id)
        .with_for_update()
    )
    if membership is None:
        raise NotFound("Member")
    if membership.role == "admin" and body.role != "admin":
        admins = db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.organization_id == actor.organization_id, Membership.role == "admin")
        )
        if admins <= 1:
            raise Conflict("An organization must keep at least one administrator.")
    old_role = membership.role
    membership.role = body.role
    user = db.get(User, user_id)
    record_audit(
        db,
        actor.organization_id,
        "member.role_changed",
        user.email,
        "success",
        actor.user_id,
        metadata={"old_role": old_role, "new_role": body.role},
    )
    db.commit()
    return MemberOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        status=user.status,
    )
