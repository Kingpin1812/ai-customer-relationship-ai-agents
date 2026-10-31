import hashlib
import re
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Actor
from app.auth.permissions import Permission
from app.core.errors import Conflict, NotFound
from app.integrations.storage import get_storage
from app.models import Artifact, Workflow


def safe_filename(name: str) -> str:
    base = re.split(r"[\\/]", name)[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base).lstrip(".")
    return cleaned[:200] or "file"


def store_artifact(
    db: Session,
    organization_id: UUID,
    workflow_id: UUID,
    kind: str,
    filename: str,
    media_type: str,
    data: bytes,
) -> Artifact:
    artifact_id = uuid4()
    filename = safe_filename(filename)
    key = f"{organization_id}/{workflow_id}/{artifact_id}/{filename}"
    get_storage().put(key, data, media_type)
    artifact = Artifact(
        id=artifact_id,
        organization_id=organization_id,
        workflow_id=workflow_id,
        kind=kind,
        filename=filename,
        storage_key=key,
        media_type=media_type,
        size_bytes=len(data),
        checksum=hashlib.sha256(data).hexdigest(),
    )
    db.add(artifact)
    db.flush()
    return artifact


def get_artifact(db: Session, organization_id: UUID, artifact_id: UUID) -> Artifact:
    artifact = db.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id, Artifact.organization_id == organization_id
        )
    )
    if artifact is None:
        raise NotFound("Artifact")
    return artifact


def read_artifact(db: Session, organization_id: UUID, artifact_id: UUID) -> bytes:
    artifact = get_artifact(db, organization_id, artifact_id)
    data = get_storage().get(artifact.storage_key)
    if hashlib.sha256(data).hexdigest() != artifact.checksum:
        raise Conflict("This file no longer matches its recorded checksum.")
    return data


def get_artifact_for_actor(db: Session, actor: Actor, artifact_id: UUID) -> Artifact:
    artifact = get_artifact(db, actor.organization_id, artifact_id)
    if not actor.can(Permission.BUSINESS_VIEW_ALL):
        workflow = db.get(Workflow, artifact.workflow_id)
        if workflow is None or workflow.created_by != actor.user_id:
            raise NotFound("Artifact")
    return artifact
