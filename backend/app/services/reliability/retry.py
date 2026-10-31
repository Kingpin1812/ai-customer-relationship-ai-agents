import random

from app.core.errors import ErrorCategory

_RETRYABLE = frozenset(
    {ErrorCategory.TRANSIENT_NETWORK, ErrorCategory.PROVIDER_SERVER, ErrorCategory.RATE_LIMITED}
)


def is_retryable(category: ErrorCategory) -> bool:
    return category in _RETRYABLE


def backoff_delay(attempt: int, base: float, maximum: float) -> float:
    """Exponential backoff with full jitter, capped at `maximum`."""
    return random.uniform(0, min(maximum, base * (2 ** (attempt - 1))))  # noqa: S311 - not crypto
