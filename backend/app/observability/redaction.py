import re
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(token|secret|password|passwd|authorization|api[_-]?key|credential|cookie)", re.IGNORECASE
)
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
REDACTED = "[REDACTED]"


def redact(value: Any) -> Any:
    """Return a copy with secrets masked. Applied to audit metadata and every log line."""
    if isinstance(value, dict):
        return {
            k: REDACTED if _SENSITIVE_KEY.search(str(k)) else redact(v) for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _JWT.sub(REDACTED, _BEARER.sub(REDACTED, value))
    return value
