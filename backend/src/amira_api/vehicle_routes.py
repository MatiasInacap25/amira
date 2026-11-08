"""Provider vehicles: registration with one photo, signed photo reads, and deletion only when nothing references the vehicle.

Ownership comes from the verified JWT through the same provider-profile helper as the request routes. Another provider's
vehicle answers 404, like any resource the caller cannot see. Photos live in the private ``VEHICLE_IMAGES_BUCKET``.
"""

import logging
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.evidence_storage import (
    EvidenceStorage,
    EvidenceStorageError,
    _supabase_storage,
    detect_photo_type,
    read_capped,
)
from amira_api.models import Servicio, ServicioAsignacion, Vehiculo, ViajeVehiculo
from amira_api.public_routes import _owned_provider
from amira_api.settings import Settings, get_settings
from amira_api.vehicle_schemas import VehicleCreated, VehicleItem, VehiclePage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/provider/vehicles", tags=["provider-vehicles"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
PLATE_DUPLICATE_MESSAGE = "Ya existe un vehículo registrado con esta patente."
PHOTO_MAX_SIZE_MESSAGE = "La foto del vehículo es más grande que el tamaño permitido."
PHOTO_TYPE_MESSAGE = "La foto del vehículo debe ser una imagen JPEG, PNG o WebP."
PHOTO_STORAGE_MESSAGE = "No pudimos guardar la foto del vehículo. Inténtalo nuevamente."
PHOTO_LINK_MESSAGE = "No pudimos crear el enlace de la foto del vehículo. Inténtalo nuevamente."
PLATE_REQUIRED_MESSAGE = "La patente es obligatoria."
NOT_FOUND_MESSAGE = "Vehículo no encontrado."
IN_USE_MESSAGE = "El vehículo está asignado a un servicio o viaje y no se puede eliminar."


def _vehicle_image_storage(settings: Settings) -> EvidenceStorage:
    bucket = (settings.vehicle_images_bucket or "").strip()
    if not settings.supabase_url or settings.supabase_service_role_key is None or not bucket:
        raise HTTPException(status_code=503, detail="Vehicle photo storage is not configured.")
    return _supabase_storage(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
        bucket,
    )


def get_vehicle_image_storage_resolver(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Callable[[], EvidenceStorage]:
    """Same port and adapter, bound to the vehicle images bucket. Deferred so ownership checks run before a 503."""
    return lambda: _vehicle_image_storage(settings)


ResolveVehicleImageStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_vehicle_image_storage_resolver)]


def _discard_photo(storage: EvidenceStorage, key: str) -> None:
    """Best effort: a failed delete leaves an unreferenced object, so it is logged and never raised."""
    try:
        storage.delete(key)
    except EvidenceStorageError:
        logger.warning("Could not delete the unreferenced vehicle photo %s.", key, exc_info=True)


def _plate_taken(session: Session, plate: str) -> bool:
    # Same expression as the unique index uq_vehiculo_patente_normalizada: trimmed and lowercased.
    return session.execute(
        select(Vehiculo.id).where(func.lower(func.btrim(Vehiculo.plate)) == plate.lower())
    ).scalar_one_or_none() is not None


@router.post("", response_model=VehicleCreated, status_code=201)
def create_vehicle(
    current_user: CurrentUser,
    session: Database,
    resolve_storage: ResolveVehicleImageStorage,
    settings: AppSettings,
    plate: Annotated[str, Form(max_length=16)],
    brand: Annotated[str, Form(max_length=80)],
    model: Annotated[str, Form(max_length=100)],
    photo: Annotated[UploadFile, File()],
    year: Annotated[int | None, Form(ge=1886, le=2200)] = None,
    maximum_weight: Annotated[Decimal | None, Form(gt=0)] = None,
) -> VehicleCreated:
    _, profile_id = _owned_provider(session, current_user)
    plate = plate.strip()
    brand = brand.strip()
    model = model.strip()
    if not plate or not brand or not model:
        raise HTTPException(status_code=422, detail=PLATE_REQUIRED_MESSAGE)

    # Storage is resolved after ownership, so an unconfigured deployment answers 503 only to the owner.
    storage = resolve_storage()
    data = read_capped(photo, settings.chat_attachment_max_bytes)
    if data is None:
        raise HTTPException(status_code=413, detail=PHOTO_MAX_SIZE_MESSAGE)
    photo_type = detect_photo_type(data[:12])
    if photo_type is None:
        raise HTTPException(status_code=415, detail=PHOTO_TYPE_MESSAGE)
    if _plate_taken(session, plate):
        raise HTTPException(status_code=409, detail=PLATE_DUPLICATE_MESSAGE)

    # No open transaction while the object is in storage. The key is server-generated, never the client's filename.
    session.rollback()
    vehicle_id = uuid4()
    key = f"vehicles/{profile_id}/{vehicle_id}.{photo_type.extension}"
    try:
        storage.upload(key, data, photo_type.content_type)
    except EvidenceStorageError as error:
        raise HTTPException(status_code=502, detail=PHOTO_STORAGE_MESSAGE) from error

    # The unique index is the final guard against two registrations of the same plate during the upload.
    try:
        session.add(Vehiculo(
            id=vehicle_id,
            profile_id=profile_id,
            plate=plate,
            brand=brand,
            model=model,
            year=year,
            maximum_weight=maximum_weight,
            image_storage_key=key,
        ))
        session.commit()
    except IntegrityError as error:
        session.rollback()
        _discard_photo(storage, key)
        raise HTTPException(status_code=409, detail=PLATE_DUPLICATE_MESSAGE) from error
    except Exception:
        session.rollback()
        _discard_photo(storage, key)
        raise
    return VehicleCreated(vehicle_id=vehicle_id)


@router.get("", response_model=VehiclePage)
def list_vehicles(
    current_user: CurrentUser,
    session: Database,
    resolve_storage: ResolveVehicleImageStorage,
    settings: AppSettings,
) -> VehiclePage:
    _, profile_id = _owned_provider(session, current_user)
    rows = session.execute(
        select(Vehiculo).where(Vehiculo.profile_id == profile_id).order_by(Vehiculo.registered_at, Vehiculo.id)
    ).scalars().all()
    if not rows:
        return VehiclePage(items=[])

    storage = resolve_storage()
    ttl_seconds = settings.vehicle_image_url_ttl_seconds
    expires_at = utc_now() + timedelta(seconds=ttl_seconds)
    items: list[VehicleItem] = []
    for row in rows:
        try:
            url = storage.create_signed_url(row.image_storage_key, ttl_seconds)
        except EvidenceStorageError as error:
            raise HTTPException(status_code=502, detail=PHOTO_LINK_MESSAGE) from error
        items.append(VehicleItem(
            vehicle_id=row.id,
            plate=row.plate,
            brand=row.brand,
            model=row.model,
            year=row.year,
            maximum_weight=float(row.maximum_weight) if row.maximum_weight is not None else None,
            url=url,
            expires_at=expires_at,
        ))
    return VehiclePage(items=items)


@router.delete("/{vehicle_id}", status_code=204, response_class=Response)
def delete_vehicle(
    vehicle_id: UUID,
    current_user: CurrentUser,
    session: Database,
    resolve_storage: ResolveVehicleImageStorage,
) -> Response:
    _, profile_id = _owned_provider(session, current_user)
    storage = resolve_storage()
    vehicle = session.execute(
        select(Vehiculo).where(Vehiculo.id == vehicle_id, Vehiculo.profile_id == profile_id).with_for_update()
    ).scalar_one_or_none()
    if vehicle is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND_MESSAGE)

    referenced = any(
        session.execute(select(func.count()).select_from(table).where(column == vehicle_id)).scalar_one() > 0
        for table, column in (
            (Servicio, Servicio.vehicle_id),
            (ServicioAsignacion, ServicioAsignacion.vehicle_id),
            (ViajeVehiculo, ViajeVehiculo.vehicle_id),
        )
    )
    if referenced:
        session.rollback()
        raise HTTPException(status_code=409, detail=IN_USE_MESSAGE)

    key = vehicle.image_storage_key
    try:
        session.delete(vehicle)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=IN_USE_MESSAGE) from error
    _discard_photo(storage, key)
    return Response(status_code=204)
