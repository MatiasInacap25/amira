"""Customer images on a service request. Upload belongs to the customer who owns the request; reads follow the provider detail rule."""

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.chat_access import caller_account
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.evidence_storage import (
    EvidenceStorage,
    EvidenceStorageError,
    detect_photo_type,
    get_request_image_storage_resolver,
    read_capped,
)
from amira_api.models import FormularioServicio, ImagenFormulario
from amira_api.public_routes import _owned_provider, _provider_request_rows
from amira_api.request_image_schemas import RequestImageCreated, RequestImagePage, RequestImageUrl
from amira_api.settings import Settings, get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/requests", tags=["requests"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
ResolveRequestImageStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_request_image_storage_resolver)]
MAX_REQUEST_IMAGES = 5
IMAGE_MAX_SIZE_MESSAGE = "The request photo is larger than the allowed size."
IMAGE_TYPE_MESSAGE = "The request photo must be a JPEG, PNG or WebP image."
IMAGE_LIMIT_MESSAGE = "A request can have at most 5 photos."
IMAGE_STORAGE_MESSAGE = "The request photo could not be stored. Try again."
IMAGE_LINK_MESSAGE = "The request photo link could not be created. Try again."


def _discard_image(storage: EvidenceStorage, key: str) -> None:
    """Best effort: a failed delete leaves an unreferenced object, so it is logged and never raised."""
    try:
        storage.delete(key)
    except EvidenceStorageError:
        logger.warning("Could not delete the unreferenced request photo %s.", key, exc_info=True)


@router.post("/{request_id}/images", response_model=RequestImageCreated, status_code=201)
def upload_request_image(
    request_id: UUID,
    current_user: CurrentUser,
    session: Database,
    resolve_storage: ResolveRequestImageStorage,
    settings: AppSettings,
    photo: Annotated[UploadFile, File()],
) -> RequestImageCreated:
    account = caller_account(session, current_user)
    if account is None:
        raise HTTPException(status_code=404, detail="Request not found.")
    if not _owns_request(session, request_id, account.id):
        raise HTTPException(status_code=404, detail="Request not found.")

    # Storage is resolved after ownership, so an unconfigured deployment answers 503 only to the owner.
    storage = resolve_storage()
    data = read_capped(photo, settings.chat_attachment_max_bytes)
    if data is None:
        raise HTTPException(status_code=413, detail=IMAGE_MAX_SIZE_MESSAGE)
    photo_type = detect_photo_type(data[:12])
    if photo_type is None:
        raise HTTPException(status_code=415, detail=IMAGE_TYPE_MESSAGE)
    if _image_count(session, request_id) >= MAX_REQUEST_IMAGES:
        raise HTTPException(status_code=409, detail=IMAGE_LIMIT_MESSAGE)

    # No row lock and no open transaction while the object is in storage, so a slow upload never blocks the
    # request for providers. The key is server-generated; the client's filename never reaches the path.
    session.rollback()
    image_id = uuid4()
    key = f"requests/{request_id}/{image_id}.{photo_type.extension}"
    try:
        storage.upload(key, data, photo_type.content_type)
    except EvidenceStorageError as error:
        raise HTTPException(status_code=502, detail=IMAGE_STORAGE_MESSAGE) from error

    # Short transaction: other uploads may have finished while this object was stored, so ownership and the
    # count are checked again under the row lock before the row is written.
    try:
        if not _owns_request(session, request_id, account.id, lock=True):
            session.rollback()
            _discard_image(storage, key)
            raise HTTPException(status_code=404, detail="Request not found.")
        if _image_count(session, request_id) >= MAX_REQUEST_IMAGES:
            session.rollback()
            _discard_image(storage, key)
            raise HTTPException(status_code=409, detail=IMAGE_LIMIT_MESSAGE)
        session.add(ImagenFormulario(id=image_id, form_id=request_id, private_storage_key=key))
        session.commit()
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        _discard_image(storage, key)
        raise
    return RequestImageCreated(image_id=image_id)


def _owns_request(session: Session, request_id: UUID, customer_id: UUID, *, lock: bool = False) -> bool:
    statement = select(FormularioServicio.id).where(
        FormularioServicio.id == request_id, FormularioServicio.customer_id == customer_id
    )
    if lock:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none() is not None


def _image_count(session: Session, request_id: UUID) -> int:
    return session.execute(
        select(func.count()).select_from(ImagenFormulario).where(ImagenFormulario.form_id == request_id)
    ).scalar_one()


@router.get("/{request_id}/images", response_model=RequestImagePage)
def list_request_images(
    request_id: UUID,
    current_user: CurrentUser,
    session: Database,
    resolve_storage: ResolveRequestImageStorage,
    settings: AppSettings,
) -> RequestImagePage:
    account = caller_account(session, current_user)
    customer_owns = False
    if account is not None:
        customer_owns = (
            session.execute(
                select(FormularioServicio.id).where(
                    FormularioServicio.id == request_id, FormularioServicio.customer_id == account.id
                )
            ).scalar_one_or_none()
            is not None
        )
    if not customer_owns:
        # Same rule and same responses as GET /api/provider/requests/{id}: other providers get its 404.
        _, profile_id = _owned_provider(session, current_user)
        visible = session.execute(
            _provider_request_rows(profile_id).where(FormularioServicio.id == request_id)
        ).mappings().one_or_none()
        if visible is None:
            raise HTTPException(status_code=404, detail="Provider request not found.")

    keys = session.execute(
        select(ImagenFormulario.id, ImagenFormulario.private_storage_key).where(ImagenFormulario.form_id == request_id)
    ).all()
    if not keys:
        return RequestImagePage(items=[])

    storage = resolve_storage()
    ttl_seconds = settings.request_image_url_ttl_seconds
    expires_at = utc_now() + timedelta(seconds=ttl_seconds)
    items: list[RequestImageUrl] = []
    for image_id, key in keys:
        try:
            url = storage.create_signed_url(key, ttl_seconds)
        except EvidenceStorageError as error:
            raise HTTPException(status_code=502, detail=IMAGE_LINK_MESSAGE) from error
        items.append(RequestImageUrl(image_id=image_id, url=url, expires_at=expires_at))
    return RequestImagePage(items=items)
