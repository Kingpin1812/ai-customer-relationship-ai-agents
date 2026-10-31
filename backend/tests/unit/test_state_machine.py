import pytest

from app.core.errors import Conflict
from app.services.workflows.state_machine import ALLOWED, can_transition, ensure_transition

STATUSES = [
    "queued",
    "running",
    "waiting_for_approval",
    "succeeded",
    "failed",
    "rejected",
    "cancelled",
]


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("queued", "running"),
        ("queued", "cancelled"),
        ("running", "waiting_for_approval"),
        ("running", "succeeded"),
        ("running", "failed"),
        ("running", "rejected"),
        ("waiting_for_approval", "running"),
        ("waiting_for_approval", "rejected"),
        ("waiting_for_approval", "cancelled"),
        ("waiting_for_approval", "failed"),
        ("failed", "queued"),
    ],
)
def test_allowed_edges(source, target):
    assert can_transition(source, target)


@pytest.mark.parametrize("terminal", ["succeeded", "rejected", "cancelled"])
@pytest.mark.parametrize("target", STATUSES)
def test_terminal_states_never_move(terminal, target):
    assert not can_transition(terminal, target)


def test_running_cannot_be_cancelled_midway():
    assert not can_transition("running", "cancelled")


def test_illegal_transition_raises_conflict():
    with pytest.raises(Conflict):
        ensure_transition("succeeded", "running")


def test_every_status_is_defined():
    assert set(ALLOWED) == set(STATUSES)
