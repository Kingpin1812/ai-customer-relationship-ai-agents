from app.core.errors import AppError, ErrorCategory


class IntegrationError(AppError):
    """A normalized provider failure. Adapters raise only this, so callers never see vendor types."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        retry_after: float | None = None,
        provider_request_id: str | None = None,
    ):
        super().__init__(category, message, 502)
        self.retry_after = retry_after
        self.provider_request_id = provider_request_id
