"""Hand a workflow to whichever executor is configured. Durable state lives in PostgreSQL either way."""

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from uuid import UUID

from app.agents.runner import advance_workflow
from app.core.config import get_settings


@lru_cache
def _pool() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=4, thread_name_prefix="workflow")


def submit_advance(workflow_id: UUID | str) -> None:
    mode = get_settings().task_executor
    if mode == "celery":
        from app.workers.tasks import advance_workflow_task

        advance_workflow_task.delay(str(workflow_id))
    elif mode == "thread":
        _pool().submit(advance_workflow, workflow_id)
    else:
        advance_workflow(workflow_id)
