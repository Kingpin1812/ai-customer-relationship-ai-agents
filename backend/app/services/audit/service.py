from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.context import get_correlation_id
from app.models import AuditEvent
from app.observability.redaction import redact


def record_audit(
    db: Session,
    organization_id: UUID,
    action: str,
    target: str,
    result: str,
    actor_id: UUID | None = None,
    workflow_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> AuditEvent:
    """Add an audit row to the caller's transaction, so it commits or rolls back with the change."""
    event = AuditEvent(
        organization_id=organization_id,
        actor_id=actor_id,
        workflow_id=workflow_id,
        action=action,
        target=target[:200],
        result=result,
        correlation_id=correlation_id or get_correlation_id(),
        event_metadata=redact(metadata or {}),
    )
    db.add(event)
    return event
