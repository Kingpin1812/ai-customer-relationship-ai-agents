"""Every provider adapter must pass these. A real CRM or mail adapter plugs into the same fixtures."""

import pytest
from sqlalchemy import func, select

from app.core.errors import ErrorCategory
from app.integrations.crm.mock import MockCrmAdapter
from app.integrations.email.base import OutgoingEmail
from app.integrations.email.mock import MockEmailAdapter
from app.models import MockEmail, Organization
from app.services.reliability.errors import IntegrationError


@pytest.fixture
def org_id(db):
    return db.scalar(select(Organization.id).where(Organization.name == "Demo Trading Co"))


@pytest.fixture
def other_org_id(db):
    return db.scalar(select(Organization.id).where(Organization.name == "Other Corp"))


MESSAGE = OutgoingEmail("billing@acme-ltd.example", "Subject", "Body", [])


def test_crm_search_exact_name_wins_over_partial(org_id):
    results = MockCrmAdapter(org_id).search("Acme Ltd")
    assert [r.provider_customer_id for r in results] == ["acme-ltd"]


def test_crm_search_ambiguous_returns_all(org_id):
    assert len(MockCrmAdapter(org_id).search("Acme")) == 2


def test_crm_search_by_stable_id(org_id):
    assert MockCrmAdapter(org_id).search("globex")[0].name == "Globex Corporation"


def test_crm_search_none(org_id):
    assert MockCrmAdapter(org_id).search("Nobody Inc") == []


def test_crm_search_treats_wildcards_as_text(org_id):
    assert MockCrmAdapter(org_id).search("%") == []


def test_crm_is_tenant_scoped(org_id, other_org_id):
    mine = MockCrmAdapter(org_id).get("acme-ltd")
    theirs = MockCrmAdapter(other_org_id).get("acme-ltd")
    assert mine.email != theirs.email
    assert MockCrmAdapter(other_org_id).search("Globex") == []


def test_crm_get_missing_is_a_permanent_error(org_id):
    with pytest.raises(IntegrationError) as exc:
        MockCrmAdapter(org_id).get("missing")
    assert exc.value.category == ErrorCategory.PERMANENT_PROVIDER


def test_crm_note_update_is_idempotent_with_key(org_id):
    crm = MockCrmAdapter(org_id)
    crm.update_note("acme-ltd", "hello", "key-1")
    crm.update_note("acme-ltd", "hello", "key-1")
    assert crm.get("acme-ltd").notes == ["hello"]


def test_crm_timeout_fault_clears_after_configured_failures(org_id):
    crm = MockCrmAdapter(org_id, faults={"crm_timeouts": 2})
    for _ in range(2):
        with pytest.raises(IntegrationError) as exc:
            crm.search("Acme Ltd")
        assert exc.value.category == ErrorCategory.TRANSIENT_NETWORK
    assert crm.search("Acme Ltd")


def test_email_send_records_once_per_key(org_id, db):
    email = MockEmailAdapter(org_id)
    first = email.send(MESSAGE, "key-a")
    second = email.send(MESSAGE, "key-a")
    assert first["provider_message_id"] == second["provider_message_id"]
    assert db.scalar(select(func.count()).select_from(MockEmail)) == 1


def test_email_find_by_key(org_id):
    email = MockEmailAdapter(org_id)
    assert email.find_by_idempotency_key("nope") is None
    sent = email.send(MESSAGE, "key-b")
    assert (
        email.find_by_idempotency_key("key-b")["provider_message_id"] == sent["provider_message_id"]
    )


def test_email_unknown_outcome_that_was_delivered(org_id):
    email = MockEmailAdapter(org_id, faults={"email_unknown_sent": True})
    with pytest.raises(IntegrationError) as exc:
        email.send(MESSAGE, "key-c")
    assert exc.value.category == ErrorCategory.UNKNOWN_OUTCOME
    assert email.find_by_idempotency_key("key-c") is not None


def test_email_unknown_outcome_that_was_not_delivered(org_id):
    email = MockEmailAdapter(org_id, faults={"email_unknown_lost": True})
    with pytest.raises(IntegrationError):
        email.send(MESSAGE, "key-d")
    assert email.find_by_idempotency_key("key-d") is None
