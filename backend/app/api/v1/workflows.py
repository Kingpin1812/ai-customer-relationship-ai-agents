from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, UploadFile
from sqlalchemy import select

from app.auth.dependencies import Actor, CurrentActor, Db, require
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.models import (
    ApprovalRequest,
    Artifact,
    AuditEvent,
    EmailDraft,
    IntegrationOperation,
    Invoice,
    User,
    Workflow,
    WorkflowStep,
)
from app.schemas.common import Limit, Offset, Page
from app.schemas.workflows import (
    ApprovalBrief,
    ArtifactOut,
    EmailDraftOut,
    OperationOut,
    StepOut,
    TimelineEvent,
    WorkflowAccepted,
    WorkflowCreate,
    WorkflowDetail,
    WorkflowStatus,
    WorkflowSummary,
)
from app.services.audit.service import record_audit
from app.services.uploads import store_upload
from app.services.workflows.service import (
    can_retry,
    cancel_workflow,
    create_workflow,
    get_visible_workflow,
    list_workflows,
    retry_workflow,
)
from app.workers.executor import submit_advance

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _duration(workflow: Workflow) -> float | None:
    if workflow.started_at and workflow.finished_at:
        return (workflow.finished_at - workflow.started_at).total_seconds()
    return None


def _summary(workflow: Workflow, creator_email: str) -> WorkflowSummary:
    text = workflow.request_text
    return WorkflowSummary(
        id=workflow.id,
        request_summary=text if len(text) <= 120 else f"{text[:117]}...",
        creator_email=creator_email,
        status=workflow.status,
        created_at=workflow.created_at,
        duration_seconds=_duration(workflow),
        needs_clarification=workflow.needs_clarification,
        error_category=workflow.error_category,
    )


def _detail(db, workflow: Workflow) -> WorkflowDetail:
    steps = db.scalars(
        select(WorkflowStep)
        .where(WorkflowStep.workflow_id == workflow.id)
        .order_by(WorkflowStep.started_at)
    ).all()
    artifacts = db.scalars(
        select(Artifact).where(Artifact.workflow_id == workflow.id).order_by(Artifact.created_at)
    ).all()
    approvals = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.workflow_id == workflow.id)
        .order_by(ApprovalRequest.created_at)
    ).all()
    operations = db.scalars(
        select(IntegrationOperation)
        .where(IntegrationOperation.workflow_id == workflow.id)
        .order_by(IntegrationOperation.created_at)
    ).all()
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.workflow_id == workflow.id)
        .order_by(AuditEvent.created_at)
    ).all()
    invoice_id = db.scalar(select(Invoice.id).where(Invoice.workflow_id == workflow.id))
    draft = db.scalar(select(EmailDraft).where(EmailDraft.workflow_id == workflow.id))
    return WorkflowDetail(
        id=workflow.id,
        request_text=workflow.request_text,
        context=workflow.context,
        plan=workflow.plan,
        planner_source=workflow.planner_source,
        status=workflow.status,
        creator_email=db.get(User, workflow.created_by).email,
        error_category=workflow.error_category,
        error_message=workflow.error_message,
        needs_clarification=workflow.needs_clarification,
        can_retry=can_retry(workflow),
        can_cancel=workflow.status in ("queued", "waiting_for_approval"),
        correlation_id=workflow.correlation_id,
        trace_id=workflow.trace_id,
        created_at=workflow.created_at,
        started_at=workflow.started_at,
        finished_at=workflow.finished_at,
        steps=[StepOut.model_validate(s) for s in steps],
        artifacts=[ArtifactOut.model_validate(a) for a in artifacts],
        approvals=[ApprovalBrief.model_validate(a) for a in approvals],
        operations=[OperationOut.model_validate(o) for o in operations],
        timeline=[TimelineEvent.model_validate(e) for e in events],
        invoice_id=invoice_id,
        email_draft=EmailDraftOut.model_validate(draft) if draft else None,
    )


@router.post("", response_model=WorkflowAccepted, status_code=202)
def submit_workflow(
    body: WorkflowCreate,
    response: Response,
    db: Db,
    actor: Annotated[Actor, Depends(require(Permission.WORKFLOW_SUBMIT))],
) -> WorkflowAccepted:
    workflow, created = create_workflow(db, actor, body)
    accepted = WorkflowAccepted(
        workflow_id=workflow.id, status=workflow.status, created_at=workflow.created_at
    )
    if created:
        submit_advance(workflow.id)
    else:
        response.status_code = 200
    return accepted


@router.get("", response_model=Page[WorkflowSummary])
def get_workflows(
    actor: CurrentActor,
    db: Db,
    status: WorkflowStatus | None = None,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Limit = 25,
    offset: Offset = 0,
) -> Page[WorkflowSummary]:
    rows, total = list_workflows(db, actor, status, q, date_from, date_to, limit, offset)
    return Page(items=[_summary(w, e) for w, e in rows], total=total, limit=limit, offset=offset)


@router.get("/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(workflow_id: UUID, actor: CurrentActor, db: Db) -> WorkflowDetail:
    return _detail(db, get_visible_workflow(db, actor, workflow_id))


@router.post("/{workflow_id}/cancel", response_model=WorkflowDetail)
def cancel(workflow_id: UUID, actor: CurrentActor, db: Db) -> WorkflowDetail:
    return _detail(db, cancel_workflow(db, actor, workflow_id))


@router.post("/{workflow_id}/attachments", response_model=ArtifactOut, status_code=201)
def add_attachment(workflow_id: UUID, file: UploadFile, actor: CurrentActor, db: Db) -> ArtifactOut:
    workflow = get_visible_workflow(db, actor, workflow_id)
    actor.require(Permission.WORKFLOW_SUBMIT)
    data = file.file.read(get_settings().max_upload_bytes + 1)
    artifact = store_upload(
        db,
        actor.organization_id,
        workflow.id,
        file.filename or "file",
        file.content_type or "",
        data,
    )
    record_audit(
        db,
        actor.organization_id,
        "workflow.attachment_added",
        artifact.filename,
        "success",
        actor.user_id,
        workflow.id,
        {"size_bytes": artifact.size_bytes, "checksum": artifact.checksum},
    )
    db.commit()
    return ArtifactOut.model_validate(artifact)


@router.post("/{workflow_id}/retry", response_model=WorkflowAccepted, status_code=202)
def retry(workflow_id: UUID, actor: CurrentActor, db: Db) -> WorkflowAccepted:
    workflow = retry_workflow(db, actor, workflow_id)
    accepted = WorkflowAccepted(
        workflow_id=workflow.id, status=workflow.status, created_at=workflow.created_at
    )
    submit_advance(workflow.id)
    return accepted
