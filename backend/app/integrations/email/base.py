from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str
    attachments: list[dict] = field(default_factory=list)


class EmailAdapter(Protocol):
    """Provider-neutral mail. Implementations raise only IntegrationError."""

    provider: str

    def send(self, message: OutgoingEmail, idempotency_key: str) -> dict: ...
    def find_by_idempotency_key(self, idempotency_key: str) -> dict | None: ...
