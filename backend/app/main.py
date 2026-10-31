import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.errors import install_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.v1 import (
    approvals,
    audit,
    auth,
    business,
    dashboard,
    health,
    integrations,
    members,
    sandbox,
    workflows,
)
from app.core.config import get_settings
from app.observability.logging import configure_logging
from app.observability.tracing import instrument_app
from app.services.maintenance import run_maintenance
from app.workers.executor import submit_advance

log = structlog.get_logger()


def _maintenance_loop(stop: threading.Event, interval: int) -> None:
    while not stop.wait(interval):
        try:
            run_maintenance(submit_advance)
        except Exception as exc:  # noqa: BLE001 - keep ticking; the next run tries again
            log.error("maintenance_failed", error_type=type(exc).__name__, exc_info=exc)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    stop = threading.Event()
    if settings.task_executor == "thread":
        threading.Thread(
            target=_maintenance_loop,
            args=(stop, settings.maintenance_interval_seconds),
            daemon=True,
            name="maintenance",
        ).start()
    yield
    stop.set()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Enterprise AI Workflow Automation",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        lifespan=_lifespan,
    )
    install_error_handlers(app)
    instrument_app(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    api = APIRouter(prefix="/api/v1")
    for router in (
        health.router,
        auth.router,
        members.router,
        dashboard.router,
        workflows.router,
        approvals.router,
        business.invoices,
        business.reports,
        business.artifacts,
        audit.router,
        integrations.router,
        sandbox.router,
    ):
        api.include_router(router)
    app.include_router(api)

    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
