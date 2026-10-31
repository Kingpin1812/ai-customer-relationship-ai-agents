"""Correlation IDs, request limits and request metrics, as one ASGI wrapper around the app."""

import hashlib
import json
import re
import time
from collections import defaultdict

from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.tokens import verify_token
from app.core.config import get_settings
from app.core.context import new_correlation_id, set_correlation_id
from app.core.errors import ErrorCategory
from app.observability import metrics

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_UPLOAD_PATH = re.compile(r"/attachments/?$")
_MULTIPART_OVERHEAD = 65_536

# In-process, so the limit is per API instance. Good enough for one instance; see run.md.
_windows: dict[tuple[str, int], int] = defaultdict(int)


def reset_rate_limits() -> None:
    _windows.clear()


class _BodyTooLarge(Exception):
    pass


def _rate_limited(key: str, limit: int) -> bool:
    window = int(time.time() // 60)
    for old in [k for k in _windows if k[1] < window]:
        del _windows[old]
    _windows[(key, window)] += 1
    return _windows[(key, window)] > limit


async def _rate_limit_identity(headers: dict[str, str], scope: Scope) -> str:
    token = headers.get("authorization", "").removeprefix("Bearer ").strip()
    if token:
        try:
            return "user:" + await run_in_threadpool(verify_token, token)
        except Exception:  # noqa: BLE001, S110 - an unverifiable token earns no bucket of its own
            pass
    return "address:" + (scope.get("client") or ("unknown",))[0]


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        supplied = headers.get("x-correlation-id", "")
        correlation_id = supplied if _SAFE_ID.match(supplied) else new_correlation_id()
        set_correlation_id(correlation_id)
        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message.setdefault("headers", []).append(
                    (b"x-correlation-id", correlation_id.encode())
                )
                metrics.HTTP_REQUESTS.labels(scope["method"], str(message["status"])).inc()
            await send(message)

        async def refuse(status: int, category: ErrorCategory, text: str) -> None:
            body = json.dumps(
                {
                    "error": {
                        "category": category.value,
                        "message": text,
                        "correlation_id": correlation_id,
                    }
                }
            ).encode()
            await send_with_id(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})

        if scope["method"] in _WRITE_METHODS:
            who = await _rate_limit_identity(headers, scope)
            key = hashlib.sha256(who.encode()).hexdigest()
            if _rate_limited(key, settings.rate_limit_per_minute):
                await refuse(
                    429, ErrorCategory.RATE_LIMITED, "Too many requests. Try again shortly."
                )
                return

        limit = settings.max_body_bytes
        if _UPLOAD_PATH.search(scope["path"]):
            limit = settings.max_upload_bytes + _MULTIPART_OVERHEAD
        too_large = (ErrorCategory.VALIDATION, "That request is too large.")
        declared = headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await refuse(413, *too_large)
            return

        seen = 0

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send_with_id)
        except _BodyTooLarge:
            if not started:
                await refuse(413, *too_large)
