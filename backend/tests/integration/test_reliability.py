from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.errors import ErrorCategory
from app.models import IntegrationOperation, Organization, OutboxEvent, User, Workflow
from app.services.reliability.errors import IntegrationError
from app.services.reliability.operations import OperationContext, run_operation
from app.services.reliability.outbox import dispatch_outbox, enqueue_event
from app.services.reliability.retry import backoff_delay, is_retryable


@pytest.fixture
def ctx(db):
    org_id = db.scalar(select(Organization.id).where(Organization.name == "Demo Trading Co"))
    user_id = db.scalar(select(User.id).where(User.organization_id == org_id).limit(1))
    workflow = Workflow(
        organization_id=org_id,
        created_by=user_id,
        request_text="t",
        status="running",
        graph_thread_id=uuid4().hex,
        idempotency_key=uuid4().hex,
    )
    db.add(workflow)
    db.commit()
    return OperationContext(org_id, workflow.id, user_id)


class Flaky:
    def __init__(self, *errors, result=None):
        self.errors = list(errors)
        self.calls = 0
        self.result = result or {"ok": True}

    def __call__(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.result


def _transient():
    return IntegrationError(ErrorCategory.TRANSIENT_NETWORK, "timeout")


def _op(db, key):
    db.expire_all()
    return db.scalar(select(IntegrationOperation).where(IntegrationOperation.op_key == key))


def test_transient_error_recovers_within_limit(db, ctx):
    fn = Flaky(_transient(), _transient())
    assert run_operation(db, ctx, "p", "o", "k1", fn) == {"ok": True}
    assert fn.calls == 3
    op = _op(db, "k1")
    assert op.status == "succeeded"
    assert op.attempt_count == 3


def test_retries_are_bounded_and_end_in_manual_review(db, ctx, settings):
    fn = Flaky(*[_transient() for _ in range(20)])
    with pytest.raises(IntegrationError):
        run_operation(db, ctx, "p", "o", "k2", fn)
    assert fn.calls == settings.retry_max_attempts
    op = _op(db, "k2")
    assert op.status == "manual_review_required"
    assert op.error_category == "transient_network_error"


@pytest.mark.parametrize(
    "category",
    [
        ErrorCategory.VALIDATION,
        ErrorCategory.AUTHENTICATION,
        ErrorCategory.AUTHORIZATION,
        ErrorCategory.PERMANENT_PROVIDER,
    ],
)
def test_permanent_errors_are_tried_once(db, ctx, category):
    fn = Flaky(IntegrationError(category, "nope"), {"never": True})
    with pytest.raises(IntegrationError):
        run_operation(db, ctx, "p", "o", f"k3-{category}", fn)
    assert fn.calls == 1
    assert _op(db, f"k3-{category}").status == "failed"


def test_retry_after_is_honoured(db, ctx, monkeypatch):
    slept = []
    monkeypatch.setattr("app.services.reliability.operations.time.sleep", slept.append)
    fn = Flaky(IntegrationError(ErrorCategory.RATE_LIMITED, "slow down", retry_after=7.0))
    run_operation(db, ctx, "p", "o", "k4", fn)
    assert slept == [7.0]


def test_backoff_is_bounded_and_jittered(settings):
    delays = [backoff_delay(10, base=1.0, maximum=5.0) for _ in range(50)]
    assert all(0 <= d <= 5.0 for d in delays)
    assert len(set(delays)) > 1


def test_retry_classification():
    assert is_retryable(ErrorCategory.TRANSIENT_NETWORK)
    assert is_retryable(ErrorCategory.PROVIDER_SERVER)
    assert is_retryable(ErrorCategory.RATE_LIMITED)
    assert not is_retryable(ErrorCategory.VALIDATION)
    assert not is_retryable(ErrorCategory.UNKNOWN_OUTCOME)


def test_succeeded_key_is_not_called_again(db, ctx):
    fn = Flaky()
    run_operation(db, ctx, "p", "o", "k5", fn)
    run_operation(db, ctx, "p", "o", "k5", fn)
    assert fn.calls == 1


def test_unknown_outcome_that_actually_happened_is_not_repeated(db, ctx):
    fn = Flaky(IntegrationError(ErrorCategory.UNKNOWN_OUTCOME, "no response"))
    result = run_operation(db, ctx, "p", "o", "k6", fn, reconcile=lambda: {"found": True})
    assert result == {"found": True}
    assert fn.calls == 1
    assert _op(db, "k6").status == "succeeded"


def test_unknown_outcome_confirmed_not_happened_retries(db, ctx):
    fn = Flaky(IntegrationError(ErrorCategory.UNKNOWN_OUTCOME, "no response"))
    result = run_operation(db, ctx, "p", "o", "k7", fn, reconcile=lambda: None)
    assert result == {"ok": True}
    assert fn.calls == 2


def test_unknown_outcome_without_reconcile_goes_to_manual_review(db, ctx):
    fn = Flaky(IntegrationError(ErrorCategory.UNKNOWN_OUTCOME, "no response"))
    with pytest.raises(IntegrationError):
        run_operation(db, ctx, "p", "o", "k8", fn)
    assert fn.calls == 1
    assert _op(db, "k8").status == "manual_review_required"


def test_crash_mid_call_reconciles_before_calling_again(db, ctx):
    op = IntegrationOperation(
        organization_id=ctx.organization_id,
        workflow_id=ctx.workflow_id,
        provider="p",
        operation="o",
        op_key="k9",
        status="running",
        attempt_count=1,
    )
    db.add(op)
    db.commit()
    fn = Flaky()
    assert run_operation(db, ctx, "p", "o", "k9", fn, reconcile=lambda: {"found": True}) == {
        "found": True
    }
    assert fn.calls == 0


def test_outbox_rolls_back_with_the_caller(db, ctx):
    enqueue_event(db, ctx.organization_id, "x.happened", {"a": 1})
    db.rollback()
    assert db.scalar(select(OutboxEvent)) is None


def test_outbox_publishes_each_event_once(db, ctx):
    enqueue_event(db, ctx.organization_id, "x.happened", {"a": 1})
    db.commit()
    seen = []
    assert dispatch_outbox(db, seen.append) == 1
    assert dispatch_outbox(db, seen.append) == 0
    assert [e.event_type for e in seen] == ["x.happened"]


def test_outbox_leaves_event_unpublished_when_publish_fails(db, ctx):
    enqueue_event(db, ctx.organization_id, "x.happened", {"a": 1})
    db.commit()

    def boom(_):
        raise RuntimeError("broker down")

    assert dispatch_outbox(db, boom) == 0
    assert db.scalar(select(OutboxEvent)).published_at is None


def test_disconnecting_a_provider_does_not_erase_an_uncertain_send(ctx, db):
    from app.models import Integration

    send = Flaky(IntegrationError(ErrorCategory.UNKNOWN_OUTCOME, "silent"))
    with pytest.raises(IntegrationError):
        run_operation(db, ctx, "mock_email", "send_email", "uncertain", send)

    def set_status(status):
        db.execute(
            update(Integration)
            .where(
                Integration.organization_id == ctx.organization_id,
                Integration.provider == "mock_email",
            )
            .values(status=status)
        )
        db.commit()

    set_status("disconnected")
    with pytest.raises(IntegrationError) as refused:
        run_operation(db, ctx, "mock_email", "send_email", "uncertain", send)
    assert refused.value.category == ErrorCategory.AUTHENTICATION
    assert _op(db, "uncertain").error_category == ErrorCategory.UNKNOWN_OUTCOME.value
    calls_before = send.calls

    set_status("connected")
    result = run_operation(
        db,
        ctx,
        "mock_email",
        "send_email",
        "uncertain",
        send,
        reconcile=lambda: {"provider_message_id": "found"},
    )
    assert result == {"provider_message_id": "found"}
    assert send.calls == calls_before
