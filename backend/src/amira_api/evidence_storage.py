"""Port for private evidence storage (delivery photos). The domain depends on this protocol; each backend is an adapter.

The composition root is ``get_evidence_storage``. Routes depend on it, and tests override it with an in-memory fake.
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, NamedTuple, Protocol

from fastapi import Depends, HTTPException, UploadFile

from amira_api.settings import Settings, get_settings

READ_CHUNK_BYTES = 64 * 1024


class EvidenceStorageError(Exception):
    """The storage backend refused or failed the request. Callers must treat the write as not done."""


class EvidenceStorage(Protocol):
    def upload(self, key: str, content: bytes, content_type: str) -> None:
        """Store the bytes under ``key`` in the private bucket. Raises EvidenceStorageError on failure."""
        ...

    def create_signed_url(self, key: str, expires_in: int) -> str:
        """A URL that reads ``key`` for ``expires_in`` seconds and nothing else. Raises EvidenceStorageError on failure."""
        ...

    def delete(self, key: str) -> None:
        """Remove ``key`` from the private bucket. Raises EvidenceStorageError on failure."""
        ...


class PhotoType(NamedTuple):
    content_type: str
    extension: str


def detect_photo_type(head: bytes) -> PhotoType | None:
    """Identify JPEG, PNG or WebP from the leading bytes. The declared content type is never trusted."""
    if head.startswith(b"\xff\xd8\xff"):
        return PhotoType("image/jpeg", "jpg")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PhotoType("image/png", "png")
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return PhotoType("image/webp", "webp")
    return None


def read_capped(upload: UploadFile, max_bytes: int) -> bytes | None:
    """Read the upload in chunks and stop once it exceeds ``max_bytes``. Returns None when it is too large.

    Content-Length is not trusted: the cap is enforced on the bytes actually read.
    """
    buffer = bytearray()
    while chunk := upload.file.read(READ_CHUNK_BYTES):
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            return None
    return bytes(buffer)


def get_evidence_storage(settings: Annotated[Settings, Depends(get_settings)]) -> EvidenceStorage:
    """Composition root for the evidence port. Only the Supabase Storage adapter exists today."""
    if not settings.supabase_url or settings.supabase_service_role_key is None:
        raise HTTPException(status_code=503, detail="Delivery photo storage is not configured.")
    return _supabase_storage(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
        settings.service_evidence_bucket,
    )


def get_evidence_storage_resolver(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Callable[[], EvidenceStorage]:
    """Defers the composition root until a handler calls it, so earlier checks in that handler run before a 503."""
    return lambda: get_evidence_storage(settings)


@lru_cache
def _supabase_storage(base_url: str, service_role_key: str, bucket: str) -> EvidenceStorage:
    # Imported here: the adapter imports EvidenceStorageError from this module.
    from amira_api.supabase_evidence_storage import SupabaseEvidenceStorage

    return SupabaseEvidenceStorage(base_url=base_url, service_role_key=service_role_key, bucket=bucket)
