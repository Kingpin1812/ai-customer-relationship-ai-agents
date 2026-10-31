from typing import TypedDict


class WorkflowState(TypedDict, total=False):
    """Only identifiers and the plan. Business data stays in PostgreSQL."""

    workflow_id: str
    organization_id: str
    actor_id: str
    plan: dict
    approval_id: str
    decision: str
    needs_new_approval: bool
