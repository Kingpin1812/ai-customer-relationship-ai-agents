from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class CrmCustomer:
    provider_customer_id: str
    name: str
    email: str
    notes: list[str] = field(default_factory=list)


class CrmAdapter(Protocol):
    """Provider-neutral CRM. Implementations raise only IntegrationError."""

    provider: str

    def search(self, reference: str) -> list[CrmCustomer]: ...
    def get(self, provider_customer_id: str) -> CrmCustomer: ...
    def update_note(self, provider_customer_id: str, note: str, idempotency_key: str) -> dict: ...
    def note_applied(self, provider_customer_id: str, idempotency_key: str) -> dict | None: ...
