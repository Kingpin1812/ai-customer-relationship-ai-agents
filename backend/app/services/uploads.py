"""Supporting files. Stored for people to read; their content is never sent to the planner."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory, ValidationFailed
from app.models import Artifact
from app.services.artifacts import safe_filename, store_artifact

_TYPES: dict[str, tuple[set[str], bytes | None]] = {
    "application/pdf": ({".pdf"}, b"%PDF"),
    "image/png": ({".png"}, b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": ({".jpg", ".jpeg"}, b"\xff\xd8\xff"),
    "text/csv": ({".csv"}, None),
    "text/plain": ({".txt"}, None),
}


def store_upload(
    db: Session,
    organization_id: UUID,
    workflow_id: UUID,
    filename: str,
    media_type: str,
    data: bytes,
) -> Artifact:
    settings = get_settings()
    if len(data) > settings.max_upload_bytes:
        raise AppError(ErrorCategory.VALIDATION, "That file is too large.", 413)
    if media_type not in _TYPES:
        raise ValidationFailed("That file type is not allowed. Use PDF, PNG, JPEG, CSV or TXT.")
    extensions, magic = _TYPES[media_type]
    safe = safe_filename(filename)
    if not any(safe.lower().endswith(ext) for ext in extensions):
        raise ValidationFailed("The file name does not match its type.")
    if magic is not None and not data.startswith(magic):
        raise ValidationFailed("The file content does not match its type.")
    if magic is None:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationFailed("Text files must be UTF-8.") from exc
        if b"\x00" in data:
            raise ValidationFailed("The file content does not match its type.")
    return store_artifact(db, organization_id, workflow_id, "upload", safe, media_type, data)
