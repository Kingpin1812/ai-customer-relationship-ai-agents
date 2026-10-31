from uuid import UUID

from sqlalchemy import func, or_, select

from app.core.errors import ErrorCategory
from app.db.session import SessionLocal
from app.integrations.crm.base import CrmCustomer
from app.models import MockCrmRecord
from app.services.reliability.errors import IntegrationError


class MockCrmAdapter:
    """Behaves like a remote CRM: its own connection, its own commits, optional simulated faults."""

    provider = "mock_crm"

    def __init__(self, organization_id: UUID, faults: dict | None = None):
        self.organization_id = organization_id
        self.faults = dict(faults or {})

    def _maybe_fail(self) -> None:
        if self.faults.get("crm_timeouts", 0) > 0:
            self.faults["crm_timeouts"] -= 1
            raise IntegrationError(
                ErrorCategory.TRANSIENT_NETWORK, "The CRM did not respond in time."
            )

    @staticmethod
    def _to_customer(record: MockCrmRecord) -> CrmCustomer:
        return CrmCustomer(
            record.provider_customer_id, record.name, record.email, list(record.notes)
        )

    def search(self, reference: str) -> list[CrmCustomer]:
        self._maybe_fail()
        needle = reference.strip().lower()
        with SessionLocal() as db:
            scoped = select(MockCrmRecord).where(
                MockCrmRecord.organization_id == self.organization_id
            )
            exact = db.scalars(
                scoped.where(
                    or_(
                        func.lower(MockCrmRecord.provider_customer_id) == needle,
                        func.lower(MockCrmRecord.name) == needle,
                    )
                )
            ).all()
            if exact:
                return [self._to_customer(r) for r in exact]
            partial = db.scalars(
                scoped.where(MockCrmRecord.name.icontains(needle, autoescape=True)).order_by(
                    MockCrmRecord.name
                )
            ).all()
            return [self._to_customer(r) for r in partial]

    def _record(self, db, provider_customer_id: str, lock: bool = False) -> MockCrmRecord:
        statement = select(MockCrmRecord).where(
            MockCrmRecord.organization_id == self.organization_id,
            MockCrmRecord.provider_customer_id == provider_customer_id,
        )
        record = db.scalar(statement.with_for_update() if lock else statement)
        if record is None:
            raise IntegrationError(
                ErrorCategory.PERMANENT_PROVIDER, "That CRM record does not exist."
            )
        return record

    def get(self, provider_customer_id: str) -> CrmCustomer:
        self._maybe_fail()
        with SessionLocal() as db:
            return self._to_customer(self._record(db, provider_customer_id))

    def update_note(self, provider_customer_id: str, note: str, idempotency_key: str) -> dict:
        self._maybe_fail()
        with SessionLocal() as db:
            record = self._record(db, provider_customer_id, lock=True)
            if idempotency_key not in record.applied_keys:
                record.notes = [*record.notes, note]
                record.applied_keys = [*record.applied_keys, idempotency_key]
                db.commit()
        return {"provider_request_id": idempotency_key}

    def note_applied(self, provider_customer_id: str, idempotency_key: str) -> dict | None:
        with SessionLocal() as db:
            record = self._record(db, provider_customer_id)
            if idempotency_key in record.applied_keys:
                return {"provider_request_id": idempotency_key}
        return None
