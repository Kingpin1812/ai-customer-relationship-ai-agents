from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OutboxEvent

log = structlog.get_logger()


def enqueue_event(db: Session, organization_id: UUID, event_type: str, payload: dict) -> None:
    """Add to the caller's transaction, so the event exists only if the change commits."""
    db.add(OutboxEvent(organization_id=organization_id, event_type=event_type, payload=payload))


def log_publisher(event: OutboxEvent) -> None:
    log.info("outbox_event", event_type=event.event_type, event_id=str(event.id))


def dispatch_outbox(
    db: Session, publish: Callable[[OutboxEvent], None] = log_publisher, batch: int = 100
) -> int:
    """Publish pending events. SKIP LOCKED lets several dispatchers run without double-sending."""
    events = db.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at)
        .limit(batch)
        .with_for_update(skip_locked=True)
    ).all()
    published = 0
    for event in events:
        try:
            publish(event)
        except Exception as exc:  # noqa: BLE001 - stay unpublished and try again next tick
            log.warning("outbox_publish_failed", error_type=type(exc).__name__)
            break
        event.published_at = datetime.now(UTC)
        published += 1
    db.commit()
    return published
