import logging
import sys
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.context import get_correlation_id
from app.observability.redaction import redact


def redact_processor(_logger, _method: str | None, event_dict: dict) -> dict:
    return redact(event_dict)


def _add_correlation(_logger, _method: str, event_dict: dict) -> dict:
    correlation_id = get_correlation_id()
    if correlation_id:
        event_dict.setdefault("correlation_id", correlation_id)
    return event_dict


def configure_logging() -> None:
    level = get_settings().log_level.upper()
    logging.basicConfig(stream=sys.stdout, format="%(message)s", level=level, force=True)
    processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_correlation,
        structlog.processors.format_exc_info,
        redact_processor,
        structlog.processors.JSONRenderer(),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
