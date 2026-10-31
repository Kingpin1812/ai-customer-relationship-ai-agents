from uuid import UUID

from app.integrations.crm.base import CrmAdapter
from app.integrations.crm.mock import MockCrmAdapter


def get_crm_adapter(organization_id: UUID, faults: dict | None = None) -> CrmAdapter:
    return MockCrmAdapter(organization_id, faults)
