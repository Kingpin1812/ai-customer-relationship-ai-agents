import re
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Protocol

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory

_SAFE_KEY = re.compile(r"^[A-Za-z0-9_\-./]+$")


class StorageError(AppError):
    def __init__(self, message: str = "The file store is unavailable."):
        super().__init__(ErrorCategory.INTERNAL, message, 500)


def _validate_key(key: str) -> str:
    parts = PurePosixPath(key).parts
    if not _SAFE_KEY.match(key) or key.startswith("/") or ".." in parts or not parts:
        raise StorageError("That file path is not allowed.")
    return key


class StorageBackend(Protocol):
    def put(self, key: str, data: bytes, media_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def check(self) -> None: ...


class LocalStorage:
    """Filesystem store for running without MinIO."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / _validate_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("That file path is not allowed.")
        return path

    def put(self, key: str, data: bytes, media_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as exc:
            raise StorageError("That file could not be read.") from exc

    def check(self) -> None:
        if not self.root.is_dir():
            raise StorageError()


class S3Storage:
    """MinIO locally, S3 in production."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None,
        access_key: str | None,
        secret_key: str | None,
        region: str,
    ):
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, data: bytes, media_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=_validate_key(key), Body=data, ContentType=media_type
        )

    def get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=_validate_key(key))["Body"].read()
        except ClientError as exc:
            raise StorageError("That file could not be read.") from exc

    def check(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)


@lru_cache
def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "s3":
        storage = S3Storage(
            settings.s3_bucket,
            settings.s3_endpoint_url,
            settings.s3_access_key,
            settings.s3_secret_key,
            settings.s3_region,
        )
        storage.ensure_bucket()
        return storage
    return LocalStorage(settings.storage_local_path)
