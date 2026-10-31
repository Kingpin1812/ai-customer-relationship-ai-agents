"""Run one external operation exactly as safely as its provider allows.

The operation row is committed before and after each attempt, so a crash leaves evidence that a
call may have happened. On the way back in, that evidence forces reconciliation before any repeat.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ErrorCategory
from app.models import Integration, IntegrationOperation
from app.observability import metrics
from app.services.audit.service import record_audit
from app.services.reliability.errors import IntegrationError
from app.services.reliability.retry import backoff_delay, is_retryable

log = structlog.get_logger()


@dataclass(frozen=True)
class OperationContext:
    organization_id: UUID
    workflow_id: UUID
    actor_id: UUID | None = None


def _load(db: Session, ctx: OperationContext, provider: str, operation: str, key: str):
    db.execute(
        insert(IntegrationOperation)
        .values(
            organization_id=ctx.organization_id,
            workflow_id=ctx.workflow_id,
            provider=provider,
            operation=operation,
            op_key=key,
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "op_key"])
    )
    return db.scalar(
        select(IntegrationOperation)
        .where(
            IntegrationOperation.organization_id == ctx.organization_id,
            IntegrationOperation.op_key == key,
        )
        .execution_options(populate_existing=True)
    )


def _integration_disconnected(db: Session, ctx: OperationContext, provider: str) -> bool:
    status = db.scalar(
        select(Integration.status).where(
            Integration.organization_id == ctx.organization_id, Integration.provider == provider
        )
    )
    return status is not None and status != "connected"


def _audit(db: Session, ctx: OperationContext, op: IntegrationOperation, result: str, **extra):
    record_audit(
        db,
        ctx.organization_id,
        f"integration.{op.operation}",
        f"{op.provider}:{op.op_key}",
        result,
        ctx.actor_id,
        ctx.workflow_id,
        {"attempt": op.attempt_count, **extra},
    )


def _succeed(db: Session, ctx: OperationContext, op: IntegrationOperation, result: dict) -> dict:
    op.status = "succeeded"
    op.result = result
    op.next_retry_at = None
    op.error_category = None
    op.last_error = None
    op.provider_request_id = result.get("provider_request_id") or op.provider_request_id
    db.execute(
        update(Integration)
        .where(
            Integration.organization_id == ctx.organization_id,
            Integration.provider == op.provider,
        )
        .values(last_success_at=datetime.now(UTC))
    )
    _audit(db, ctx, op, "succeeded")
    db.commit()
    return result


def _reconcile_first(
    db: Session,
    ctx: OperationContext,
    op: IntegrationOperation,
    reconcile: Callable[[], dict | None],
) -> dict | None:
    found = reconcile()
    _audit(db, ctx, op, "reconciled", happened=found is not None)
    db.commit()
    metrics.RECONCILIATIONS.labels(op.provider, str(found is not None)).inc()
    return found


def run_operation(
    db: Session,
    ctx: OperationContext,
    provider: str,
    operation: str,
    op_key: str,
    fn: Callable[[], dict],
    reconcile: Callable[[], dict | None] | None = None,
) -> dict:
    settings = get_settings()
    op = _load(db, ctx, provider, operation, op_key)
    if op.status == "succeeded":
        return op.result or {}
    outcome_uncertain = (
        op.status in ("running", "unknown_outcome")
        or op.error_category == ErrorCategory.UNKNOWN_OUTCOME
    )
    if _integration_disconnected(db, ctx, provider):
        message = f"{provider} is disconnected. Ask an administrator to reconnect it, then retry."
        if not outcome_uncertain:  # uncertain state must survive, so a later retry reconciles
            op.status = "failed"
            op.error_category = ErrorCategory.AUTHENTICATION.value
        op.last_error = message
        _audit(db, ctx, op, "failed", category=ErrorCategory.AUTHENTICATION.value)
        db.commit()
        raise IntegrationError(ErrorCategory.AUTHENTICATION, message)

    if outcome_uncertain and reconcile is not None:
        found = _reconcile_first(db, ctx, op, reconcile)
        if found is not None:
            return _succeed(db, ctx, op, found)
    elif op.error_category == ErrorCategory.UNKNOWN_OUTCOME:
        raise IntegrationError(
            ErrorCategory.UNKNOWN_OUTCOME, "This operation needs manual review before any retry."
        )

    for attempt in range(1, settings.retry_max_attempts + 1):
        op.status = "running"
        op.attempt_count += 1
        db.commit()  # durable evidence before the call leaves this process
        started = time.perf_counter()
        try:
            result = fn()
        except IntegrationError as exc:
            metrics.TOOL_LATENCY.labels(provider, operation).observe(time.perf_counter() - started)
            metrics.TOOL_FAILURES.labels(provider, operation, exc.category.value).inc()
            op.error_category = exc.category.value
            op.last_error = exc.message[:500]
            op.provider_request_id = exc.provider_request_id or op.provider_request_id

            if exc.category == ErrorCategory.UNKNOWN_OUTCOME:
                op.status = "unknown_outcome"
                _audit(db, ctx, op, "unknown_outcome")
                db.commit()
                if reconcile is None:
                    op.status = "manual_review_required"
                    _audit(db, ctx, op, "manual_review_required")
                    db.commit()
                    raise
                found = _reconcile_first(db, ctx, op, reconcile)
                if found is not None:
                    return _succeed(db, ctx, op, found)
                retry_after = 0.0  # confirmed not applied, so a repeat is safe
            elif is_retryable(exc.category):
                retry_after = exc.retry_after or backoff_delay(
                    attempt, settings.retry_base_delay_seconds, settings.retry_max_delay_seconds
                )
            else:
                op.status = "failed"
                _audit(db, ctx, op, "failed", category=exc.category.value)
                db.commit()
                raise

            if attempt == settings.retry_max_attempts:
                op.status = "manual_review_required"
                _audit(db, ctx, op, "manual_review_required", category=exc.category.value)
                db.commit()
                raise

            op.status = "retry_scheduled"
            op.next_retry_at = datetime.now(UTC) + timedelta(seconds=retry_after)
            _audit(db, ctx, op, "retry_scheduled", category=exc.category.value)
            db.commit()
            metrics.RETRIES.labels(provider, operation).inc()
            log.info("operation_retry", provider=provider, operation=operation, attempt=attempt)
            time.sleep(retry_after)
        else:
            metrics.TOOL_LATENCY.labels(provider, operation).observe(time.perf_counter() - started)
            return _succeed(db, ctx, op, result)

    raise AssertionError("retry loop exits by return or raise")  # pragma: no cover
