from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import ErrorCategory
from app.db.session import SessionLocal
from app.integrations.email.base import OutgoingEmail
from app.models import MockEmail
from app.services.reliability.errors import IntegrationError


class MockEmailAdapter:
    """A sandbox mail provider. It records messages in its own table; nothing leaves the machine."""

    provider = "mock_email"

    def __init__(self, organization_id: UUID, faults: dict | None = None):
        self.organization_id = organization_id
        self.faults = dict(faults or {})

    def _record_send(self, message: OutgoingEmail, idempotency_key: str) -> None:
        with SessionLocal() as db:
            db.execute(
                insert(MockEmail)
                .values(
                    id=uuid4(),
                    organization_id=self.organization_id,
                    idempotency_key=idempotency_key,
                    provider_message_id=f"mock-{uuid4().hex}",
                    recipient=message.to,
                    subject=message.subject,
                    body=message.body,
                    attachments=message.attachments,
                )
                .on_conflict_do_nothing(index_elements=["organization_id", "idempotency_key"])
            )
            db.commit()

    def send(self, message: OutgoingEmail, idempotency_key: str) -> dict:
        if self.faults.pop("email_unknown_lost", False):
            raise IntegrationError(
                ErrorCategory.UNKNOWN_OUTCOME, "The mail provider did not answer."
            )
        self._record_send(message, idempotency_key)
        if self.faults.pop("email_unknown_sent", False):
            raise IntegrationError(
                ErrorCategory.UNKNOWN_OUTCOME, "The mail provider did not answer."
            )
        found = self.find_by_idempotency_key(idempotency_key)
        assert found is not None  # noqa: S101 - just inserted or already present
        return found

    def find_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        with SessionLocal() as db:
            row = db.scalar(
                select(MockEmail).where(
                    MockEmail.organization_id == self.organization_id,
                    MockEmail.idempotency_key == idempotency_key,
                )
            )
        if row is None:
            return None
        return {
            "provider_message_id": row.provider_message_id,
            "provider_request_id": row.provider_message_id,
            "delivery_status": "sent",
        }
