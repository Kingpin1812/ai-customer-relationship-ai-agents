from uuid import UUID

from app.integrations.email.base import EmailAdapter
from app.integrations.email.mock import MockEmailAdapter


def get_email_adapter(organization_id: UUID, faults: dict | None = None) -> EmailAdapter:
    return MockEmailAdapter(organization_id, faults)
