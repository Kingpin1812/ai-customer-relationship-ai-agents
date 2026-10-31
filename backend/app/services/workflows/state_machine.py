from app.core.errors import Conflict

ALLOWED: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled", "failed"}),
    "running": frozenset({"waiting_for_approval", "succeeded", "failed", "rejected"}),
    "waiting_for_approval": frozenset({"running", "rejected", "cancelled", "failed"}),
    "failed": frozenset({"queued"}),  # manual retry only
    "succeeded": frozenset(),
    "rejected": frozenset(),
    "cancelled": frozenset(),
}

RETRYABLE_ERROR_CATEGORIES = frozenset(
    {
        "transient_network_error",
        "authentication_error",  # after an admin reconnects the provider
        "provider_server_error",
        "rate_limited",
        "unknown_outcome",
        "internal_error",
    }
)


def can_transition(source: str, target: str) -> bool:
    return target in ALLOWED.get(source, frozenset())


def ensure_transition(source: str, target: str) -> None:
    if not can_transition(source, target):
        raise Conflict(f"A workflow cannot move from {source} to {target}.")
