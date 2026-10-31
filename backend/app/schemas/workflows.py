from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.config import get_settings
from app.schemas.common import Schema

WorkflowStatus = Literal[
    "queued", "running", "waiting_for_approval", "succeeded", "failed", "rejected", "cancelled"
]
Simulation = Literal[
    "crm_timeout", "crm_down", "report_down", "email_unknown_sent", "email_unknown_lost"
]


class WorkflowContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_reference: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ] = None
    currency: Annotated[str | None, StringConstraints(pattern=r"^[A-Z]{3}$")] = None
    simulate: Simulation | None = None

    @field_validator("simulate")
    @classmethod
    def _simulation_only_when_enabled(cls, value: str | None) -> str | None:
        if value and not get_settings().enable_fault_injection:
            raise ValueError("Simulated failures are not enabled here.")
        return value


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3)]
    context: WorkflowContext = Field(default_factory=WorkflowContext)
    idempotency_key: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]

    @field_validator("request")
    @classmethod
    def _not_too_long(cls, value: str) -> str:
        limit = get_settings().max_request_chars
        if len(value) > limit:
            raise ValueError(f"Keep the request under {limit} characters.")
        return value


class WorkflowAccepted(BaseModel):
    workflow_id: UUID
    status: WorkflowStatus
    created_at: datetime


class WorkflowSummary(Schema):
    id: UUID
    request_summary: str
    creator_email: str
    status: WorkflowStatus
    created_at: datetime
    duration_seconds: float | None
    needs_clarification: bool
    error_category: str | None


class StepOut(Schema):
    step_key: str
    status: str
    output_summary: str | None
    error: str | None
    runs: int
    started_at: datetime
    finished_at: datetime | None


class ArtifactOut(Schema):
    id: UUID
    kind: str
    filename: str
    media_type: str
    size_bytes: int
    checksum: str
    created_at: datetime


class OperationOut(Schema):
    provider: str
    operation: str
    status: str
    attempt_count: int
    error_category: str | None
    last_error: str | None
    next_retry_at: datetime | None
    provider_request_id: str | None
    updated_at: datetime


class ApprovalBrief(Schema):
    id: UUID
    status: str
    summary: str
    risk_level: str
    decided_at: datetime | None
    reason: str | None
    invalidation_reason: str | None
    created_at: datetime


class TimelineEvent(Schema):
    action: str
    target: str
    result: str
    created_at: datetime


class EmailDraftOut(Schema):
    recipient: str
    subject: str
    body: str
    status: str
    provider_message_id: str | None
    sent_at: datetime | None


class WorkflowDetail(Schema):
    id: UUID
    request_text: str
    context: dict
    plan: dict | None
    planner_source: str | None
    status: WorkflowStatus
    creator_email: str
    error_category: str | None
    error_message: str | None
    needs_clarification: bool
    can_retry: bool
    can_cancel: bool
    correlation_id: str | None
    trace_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    steps: list[StepOut]
    artifacts: list[ArtifactOut]
    approvals: list[ApprovalBrief]
    operations: list[OperationOut]
    timeline: list[TimelineEvent]
    invoice_id: UUID | None
    email_draft: EmailDraftOut | None
