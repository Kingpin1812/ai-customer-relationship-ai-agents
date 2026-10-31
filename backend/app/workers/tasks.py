from app.agents.runner import advance_workflow
from app.services.maintenance import run_maintenance
from app.workers.celery_app import celery_app


@celery_app.task(name="workflow.advance")
def advance_workflow_task(workflow_id: str) -> None:
    advance_workflow(workflow_id)


@celery_app.task(name="workflow.maintenance")
def maintenance_task() -> None:
    from app.workers.executor import submit_advance

    run_maintenance(submit_advance)
