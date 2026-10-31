from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    VALIDATION = "validation_error"
    AUTHENTICATION = "authentication_error"
    AUTHORIZATION = "authorization_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    TRANSIENT_NETWORK = "transient_network_error"
    PROVIDER_SERVER = "provider_server_error"
    PERMANENT_PROVIDER = "permanent_provider_error"
    UNKNOWN_OUTCOME = "unknown_outcome"
    INTERNAL = "internal_error"


class AppError(Exception):
    """An error whose message is safe to show to the user."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFound(AppError):
    def __init__(self, what: str = "Resource"):
        super().__init__(ErrorCategory.NOT_FOUND, f"{what} not found.", 404)


class Forbidden(AppError):
    def __init__(self, message: str = "You do not have permission to do this."):
        super().__init__(ErrorCategory.AUTHORIZATION, message, 403)


class Unauthenticated(AppError):
    def __init__(self, message: str = "Sign in to continue."):
        super().__init__(ErrorCategory.AUTHENTICATION, message, 401)


class Conflict(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(ErrorCategory.CONFLICT, message, 409, details)


class ValidationFailed(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(ErrorCategory.VALIDATION, message, 422, details)


class ClarificationNeeded(ValidationFailed):
    """The workflow cannot continue until a person supplies or corrects something."""
