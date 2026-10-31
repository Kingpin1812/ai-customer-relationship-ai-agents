from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.context import get_correlation_id
from app.core.errors import AppError, ErrorCategory

log = structlog.get_logger()


def _body(category: str, message: str, details: dict | list | None = None) -> dict:
    error: dict[str, Any] = {
        "category": category,
        "message": message,
        "correlation_id": get_correlation_id(),
    }
    if details:
        error["details"] = details
    return {"error": error}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            _body(exc.category.value, exc.message, exc.details), status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field names and reasons only: input values are not echoed back or logged.
        details = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()
        ]
        return JSONResponse(
            _body(ErrorCategory.VALIDATION.value, "Some fields are invalid.", details),
            status_code=422,
        )

    @app.exception_handler(Exception)
    def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_exception", error_type=type(exc).__name__, exc_info=exc)
        return JSONResponse(
            _body(ErrorCategory.INTERNAL.value, "Something went wrong on our side."),
            status_code=500,
        )
