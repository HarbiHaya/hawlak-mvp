import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from typing import Annotated, Any
from uuid import uuid4

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends

from app.config import Settings, get_settings

_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MEDIA_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "audio/ogg": ".ogg",
}


class ObjectStorageError(RuntimeError):
    """Hawlak's private object store is unavailable or rejected an operation."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    sha256: str
    etag: str
    content_type: str


class ObjectStorage:
    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        object_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.bucket = settings.s3_bucket
        self._object_id_factory = object_id_factory or (lambda: str(uuid4()))
        self._client = client or boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError("Hawlak object-storage bucket is unavailable") from exc

    def store_case_media(
        self,
        *,
        case_id: str,
        content: bytes,
        content_type: str,
        source_media_id: str,
    ) -> StoredObject:
        if not _SAFE_CASE_ID.fullmatch(case_id):
            raise ValueError("case_id may contain only letters, digits, underscores, and hyphens")
        if not content:
            raise ValueError("cannot store empty media content")
        if not source_media_id:
            raise ValueError("source_media_id is required")

        digest = sha256(content).hexdigest()
        extension = _MEDIA_EXTENSIONS.get(content_type, ".bin")
        key = f"cases/{case_id}/media/{self._object_id_factory()}{extension}"

        try:
            response = self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                Metadata={"sha256": digest, "source-media-id": source_media_id},
            )
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError("Hawlak could not store the media object") from exc

        return StoredObject(
            key=key,
            size=len(content),
            sha256=digest,
            etag=str(response.get("ETag", "")).strip('"'),
            content_type=content_type,
        )

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise ObjectStorageError("Hawlak could not read the media object") from exc

    def create_download_url(self, key: str, *, expires_in: int = 300) -> str:
        if not 1 <= expires_in <= 3600:
            raise ValueError("expires_in must be between 1 and 3600 seconds")
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError("Hawlak could not create a media download URL") from exc


@lru_cache
def get_object_storage() -> ObjectStorage:
    return ObjectStorage(get_settings())


StorageDep = Annotated[ObjectStorage, Depends(get_object_storage)]
