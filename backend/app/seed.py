"""Synthetic demo data. Safe to run repeatedly; does nothing if the demo tenant exists."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Integration,
    Membership,
    MockCrmRecord,
    Organization,
    SalesRecord,
    User,
)

DEMO_ORG = "Demo Trading Co"
OTHER_ORG = "Other Corp"


def _add_user(db: Session, org: Organization, email: str, name: str, role: str) -> None:
    user = User(
        organization_id=org.id, identity_subject=f"dev|{email}", email=email, display_name=name
    )
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role=role))


def _add_integrations(db: Session, org: Organization) -> None:
    db.add_all(
        [
            Integration(
                organization_id=org.id,
                provider="mock_crm",
                kind="crm",
                status="connected",
                scopes=["customers.read", "customers.notes.write"],
            ),
            Integration(
                organization_id=org.id,
                provider="mock_email",
                kind="email",
                status="connected",
                scopes=["mail.send"],
            ),
        ]
    )


def _add_sales(
    db: Session, org: Organization, today: date, customers: list[str], base: int
) -> None:
    first_of_month = today.replace(day=1)
    previous_month = (first_of_month - timedelta(days=1)).replace(day=10)
    days = [first_of_month, first_of_month + timedelta(days=1), previous_month]
    for i, sold_on in enumerate(days):
        for j, name in enumerate(customers):
            db.add(
                SalesRecord(
                    organization_id=org.id,
                    customer_name=name,
                    sold_on=sold_on,
                    amount=Decimal(base + 1500 * i + 700 * j),
                    currency="INR",
                )
            )


def main() -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        seed_demo(db)
        db.commit()


def seed_demo(db: Session, today: date | None = None) -> None:
    if db.scalar(select(Organization).where(Organization.name == DEMO_ORG)):
        return
    today = today or date.today()

    demo = Organization(name=DEMO_ORG)
    other = Organization(name=OTHER_ORG)
    db.add_all([demo, other])
    db.flush()

    _add_user(db, demo, "admin@demo.test", "Asha Admin", "admin")
    _add_user(db, demo, "manager@demo.test", "Maya Manager", "manager")
    _add_user(db, demo, "operator@demo.test", "Omar Operator", "operator")
    _add_user(db, demo, "viewer@demo.test", "Vik Viewer", "viewer")
    _add_user(db, other, "admin@other.test", "Olu Other", "admin")
    _add_user(db, other, "manager@other.test", "Mo Other", "manager")

    crm_records = [
        ("acme-ltd", "Acme Ltd", "billing@acme-ltd.example"),
        ("acme-logistics", "Acme Logistics", "accounts@acme-logistics.example"),
        ("globex", "Globex Corporation", "ap@globex.example"),
        ("initech", "Initech", "finance@initech.example"),
    ]
    for ref, name, email in crm_records:
        db.add(
            MockCrmRecord(
                organization_id=demo.id,
                provider_customer_id=ref,
                name=name,
                email=email,
                notes=[],
            )
        )
    # Same company name in another tenant: isolation tests rely on this collision.
    db.add(
        MockCrmRecord(
            organization_id=other.id,
            provider_customer_id="acme-ltd",
            name="Acme Ltd",
            email="other-tenant@acme.example",
            notes=[],
        )
    )

    _add_integrations(db, demo)
    _add_integrations(db, other)
    _add_sales(db, demo, today, ["Acme Ltd", "Globex Corporation", "Initech"], 12000)
    _add_sales(db, other, today, ["Secret Other Customer"], 999000)
    db.flush()


if __name__ == "__main__":
    main()
