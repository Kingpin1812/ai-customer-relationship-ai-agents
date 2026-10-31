from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.schemas.common import Schema

ApprovalStatus = Literal["pending", "approved", "rejected", "changes_requested", "expired"]


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject", "request_changes"]
    reason: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=1000)] = None

    @model_validator(mode="after")
    def _reason_required(self) -> "DecisionIn":
        if self.decision != "approve" and not self.reason:
            raise ValueError("Give a reason when rejecting or requesting changes.")
        return self


class ApprovalOut(Schema):
    id: UUID
    workflow_id: UUID
    action_type: str
    summary: str
    risk_level: str
    status: ApprovalStatus
    payload: dict
    payload_hash: str
    amount: str | None
    currency: str | None
    recipient: str | None
    requested_by_email: str
    decided_by_email: str | None
    decided_at: datetime | None
    reason: str | None
    invalidation_reason: str | None
    expires_at: datetime
    created_at: datetime
