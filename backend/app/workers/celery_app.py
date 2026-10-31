from celery import Celery
from celery.signals import worker_init
from prometheus_client import start_http_server

from app.core.config import get_settings
from app.observability.logging import configure_logging
from app.observability.tracing import configure_tracing

settings = get_settings()

celery_app = Celery(
    "workflow",
    broker=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_ignore_result=True,
    # Redelivered after a worker crash. Safe because advance_workflow is idempotent.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "maintenance": {
            "task": "workflow.maintenance",
            "schedule": float(settings.maintenance_interval_seconds),
        }
    },
)


@worker_init.connect
def _start_worker_observability(**_: object) -> None:
    """Workers finish the workflows, so their metrics and traces must leave this process too."""
    configure_logging()
    configure_tracing()
    port = get_settings().worker_metrics_port
    if port:
        start_http_server(port)
