from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UuidPk


class Organization(UuidPk, CreatedAt, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))


class User(UuidPk, CreatedAt, Base):
    __tablename__ = "users"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    identity_subject: Mapped[str] = mapped_column(String(320), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")


class Membership(CreatedAt, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("role IN ('admin','manager','operator','viewer')", name="role"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20))


class Integration(UuidPk, CreatedAt, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("organization_id", "provider"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="connected")
    # Name of a secret held by the secret manager; never the credential itself.
    secret_reference: Mapped[str | None] = mapped_column(String(200))
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
