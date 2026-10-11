"""Authenticated provider queries and actions over contracted services.

A provider viewer is either the owner of a provider ``Perfil`` (company owner or independent driver), who sees
every service of that profile, or a company-employed driver (``Conductor.employer_profile_id`` set) who does not
own a profile, who sees only services they are assigned to through ``Servicio_Asignacion``. Any other account
gets 403. A service the viewer cannot see answers 404, never 403.

Only the profile owner assigns drivers and vehicles. Assigned drivers and the owner can start a service.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import and_, delete, exists, or_, select, update
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.clock import as_utc, utc_now
from amira_api.db import get_db_session
from amira_api.evidence_storage import (
    EvidenceStorage,
    EvidenceStorageError,
    detect_photo_type,
    get_evidence_storage,
    read_capped,
)
from amira_api.models import Conductor, Perfil, Servicio, ServicioAsignacion, Usuario, Vehiculo
from amira_api.provider_service_schemas import (
    DeliveryPhotoUrl,
    SameDayConflict,
    SameDayConflictResponse,
    ServiceAssignmentsUpdate,
    ServiceDetail,
    ServicePage,
    ServiceStatus,
)
from amira_api.service_views import (
    DELIVERY_PHOTO_LINK_MESSAGE,
    load_assignments,
    service_count,
    service_rows,
    shape_detail,
    shape_list_item,
    signed_delivery_photo,
)
from amira_api.settings import Settings, get_settings

router = APIRouter(prefix="/api/provider", tags=["provider-services"])
MAX_PAGE_SIZE = 50
MAX_OFFSET = 5000
SANTIAGO = ZoneInfo("America/Santiago")
OPEN_STATUSES = ("confirmed", "in_progress")
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
Storage = Annotated[EvidenceStorage, Depends(get_evidence_storage)]
AppSettings = Annotated[Settings, Depends(get_settings)]
PHOTO_MAX_SIZE_MESSAGE = "The delivery photo is larger than the allowed size."
PHOTO_TYPE_MESSAGE = "The delivery photo must be a JPEG, PNG or WebP image."
PHOTO_STORAGE_MESSAGE = "The delivery photo could not be stored. Try again."


@dataclass(frozen=True)
class ProviderViewer:
    user_id: UUID
    owned_profile_id: UUID | None
    driver_id: UUID | None
    employer_profile_id: UUID | None

    @property
    def is_owner(self) -> bool:
        return self.owned_profile_id is not None

    def visibility(self) -> list:
        """SQL conditions selecting the services this viewer may see."""
        if self.is_owner:
            return [Servicio.profile_id == self.owned_profile_id]
        assigned = exists().where(
            ServicioAsignacion.service_id == Servicio.id,
            ServicioAsignacion.driver_id == self.driver_id,
        )
        return [Servicio.profile_id == self.employer_profile_id, assigned]


def _provider_viewer(session: Session, current_user: AuthenticatedUser) -> ProviderViewer:
    # The unique constraints on Usuario, Perfil.ID_user and Conductor.ID_user make this a single row. The ordering
    # keeps the choice deterministic if that ever stops holding: the independent owner's own driver row wins.
    account = session.execute(
        select(Usuario.id, Perfil.id, Conductor.id, Conductor.employer_profile_id)
        .outerjoin(Perfil, Perfil.owner_user_id == Usuario.id)
        .outerjoin(Conductor, Conductor.user_id == Usuario.id)
        .where(Usuario.auth_user_id == current_user.id)
        .order_by(Conductor.employer_profile_id.is_(None).desc(), Conductor.id)
        .limit(1)
    ).first()
    if account is None:
        raise HTTPException(status_code=403, detail="A provisioned provider account is required.")
    viewer = ProviderViewer(*account)
    if not viewer.is_owner and viewer.employer_profile_id is None:
        raise HTTPException(status_code=403, detail="Only provider accounts can access provider services.")
    return viewer


def _visible_detail(session: Session, viewer: ProviderViewer, service_id: UUID) -> ServiceDetail | None:
    row = session.execute(service_rows(Servicio.id == service_id, *viewer.visibility())).mappings().one_or_none()
    if row is None:
        return None
    return shape_detail(
        row, "provider", can_manage=viewer.is_owner, assignments=load_assignments(session, service_id)
    )


def _lock_visible_service(session: Session, viewer: ProviderViewer, service_id: UUID):
    """Lock the service row for the viewer; a service the viewer cannot see is a 404."""
    service = session.execute(
        select(Servicio.id, Servicio.status, Servicio.service_at)
        .where(Servicio.id == service_id, *viewer.visibility())
        .with_for_update()
    ).one_or_none()
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found.")
    return service


def _unprocessable(message: str, error_type: str, location: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=[{"loc": ["body", location], "msg": message, "type": error_type}],
    )


def _ensure_drivers_belong(session: Session, viewer: ProviderViewer, driver_ids: list[UUID]) -> None:
    """Drivers must be employed by the owned profile, or be the independent owner's own driver row."""
    belonging = set(
        session.execute(
            select(Conductor.id).where(
                Conductor.id.in_(driver_ids),
                or_(
                    Conductor.employer_profile_id == viewer.owned_profile_id,
                    and_(Conductor.employer_profile_id.is_(None), Conductor.user_id == viewer.user_id),
                ),
            )
        ).scalars()
    )
    if belonging != set(driver_ids):
        raise _unprocessable("Every driver must belong to this provider profile.", "driver_not_in_profile", "assignments")


def _ensure_vehicles_belong(session: Session, profile_id: UUID, vehicle_ids: list[UUID]) -> None:
    belonging = set(
        session.execute(
            select(Vehiculo.id).where(Vehiculo.id.in_(vehicle_ids), Vehiculo.profile_id == profile_id)
        ).scalars()
    )
    if belonging != set(vehicle_ids):
        raise _unprocessable("Every vehicle must belong to this provider profile.", "vehicle_not_in_profile", "assignments")


def _santiago_day_bounds(service_at: datetime) -> tuple[datetime, datetime]:
    """UTC bounds of the America/Santiago calendar day that contains ``service_at``."""
    day = as_utc(service_at).astimezone(SANTIAGO).date()
    start = datetime.combine(day, time.min, tzinfo=SANTIAGO)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=SANTIAGO)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _same_day_conflicts(
    session: Session, service_id: UUID, service_at: datetime | None, driver_ids: list[UUID]
) -> list[SameDayConflict]:
    if service_at is None:
        return []
    start, end = _santiago_day_bounds(service_at)
    rows = session.execute(
        select(ServicioAsignacion.driver_id, Servicio.id, Servicio.service_at)
        .join(Servicio, Servicio.id == ServicioAsignacion.service_id)
        .where(
            ServicioAsignacion.driver_id.in_(driver_ids),
            Servicio.id != service_id,
            Servicio.status.in_(OPEN_STATUSES),
            Servicio.service_at >= start,
            Servicio.service_at < end,
        )
        .order_by(Servicio.service_at, Servicio.id)
    ).all()
    return [SameDayConflict(driver_id=row[0], service_id=row[1], service_at=row[2]) for row in rows]


@router.get("/services", response_model=ServicePage)
def list_provider_services(
    current_user: CurrentUser,
    session: Database,
    status: ServiceStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> ServicePage:
    viewer = _provider_viewer(session, current_user)
    conditions = viewer.visibility()
    if status is not None:
        conditions.append(Servicio.status == status)
    total = session.execute(service_count(*conditions)).scalar_one()
    rows = session.execute(
        service_rows(*conditions)
        .order_by(Servicio.created_at.desc(), Servicio.id.desc())
        .limit(limit)
        .offset(offset)
    ).mappings().all()
    return ServicePage(
        items=[shape_list_item(row, "provider") for row in rows], total=total, limit=limit, offset=offset
    )


@router.get("/services/{service_id}", response_model=ServiceDetail)
def get_provider_service(service_id: UUID, current_user: CurrentUser, session: Database) -> ServiceDetail:
    viewer = _provider_viewer(session, current_user)
    detail = _visible_detail(session, viewer, service_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Service not found.")
    return detail


@router.put("/services/{service_id}/assignments", response_model=ServiceDetail)
def replace_service_assignments(
    service_id: UUID,
    payload: ServiceAssignmentsUpdate,
    current_user: CurrentUser,
    session: Database,
) -> ServiceDetail | JSONResponse:
    viewer = _provider_viewer(session, current_user)
    service = _lock_visible_service(session, viewer, service_id)
    if not viewer.is_owner:
        raise HTTPException(status_code=403, detail="Only the profile owner can manage this service.")
    if service.status != "confirmed":
        raise HTTPException(status_code=409, detail="Only confirmed services can be assigned.")

    driver_ids = [pair.driver_id for pair in payload.assignments]
    vehicle_ids = [pair.vehicle_id for pair in payload.assignments]
    _ensure_drivers_belong(session, viewer, driver_ids)
    _ensure_vehicles_belong(session, viewer.owned_profile_id, vehicle_ids)

    if not payload.confirm_same_day_conflicts:
        conflicts = _same_day_conflicts(session, service_id, service.service_at, driver_ids)
        if conflicts:
            body = SameDayConflictResponse(
                detail="Some drivers already have a service on the same day.", conflicts=conflicts
            )
            return JSONResponse(status_code=409, content=body.model_dump(by_alias=True, mode="json"))

    session.execute(delete(ServicioAsignacion).where(ServicioAsignacion.service_id == service_id))
    session.add_all([
        ServicioAsignacion(
            id=uuid4(),
            service_id=service_id,
            driver_id=pair.driver_id,
            vehicle_id=pair.vehicle_id,
            assigned_by_user_id=viewer.user_id,
        )
        for pair in payload.assignments
    ])
    session.commit()
    return _visible_detail(session, viewer, service_id)


@router.post("/services/{service_id}/start", response_model=ServiceDetail)
def start_provider_service(service_id: UUID, current_user: CurrentUser, session: Database) -> ServiceDetail:
    viewer = _provider_viewer(session, current_user)
    service = _lock_visible_service(session, viewer, service_id)
    if service.status != "confirmed":
        raise HTTPException(status_code=409, detail="Only confirmed services can be started.")
    has_assignment = session.execute(
        select(exists().where(ServicioAsignacion.service_id == service_id))
    ).scalar_one()
    if not has_assignment:
        raise HTTPException(status_code=409, detail="Assign at least one driver and vehicle before starting.")

    session.execute(
        update(Servicio)
        .where(Servicio.id == service_id)
        .values(status="in_progress", starts_at=utc_now(), started_by_user_id=viewer.user_id)
    )
    session.commit()
    return _visible_detail(session, viewer, service_id)


def _is_assigned_driver(session: Session, viewer: ProviderViewer, service_id: UUID) -> bool:
    if viewer.driver_id is None:
        return False
    return session.execute(
        select(
            exists().where(
                ServicioAsignacion.service_id == service_id,
                ServicioAsignacion.driver_id == viewer.driver_id,
            )
        )
    ).scalar_one()


@router.post("/services/{service_id}/complete", response_model=ServiceDetail)
def complete_provider_service(
    service_id: UUID,
    current_user: CurrentUser,
    session: Database,
    storage: Storage,
    settings: AppSettings,
    photo: Annotated[UploadFile, File()],
) -> ServiceDetail:
    viewer = _provider_viewer(session, current_user)
    service = _lock_visible_service(session, viewer, service_id)
    if not _is_assigned_driver(session, viewer, service_id):
        raise HTTPException(status_code=403, detail="Only an assigned driver can complete this service.")
    if service.status != "in_progress":
        raise HTTPException(status_code=409, detail="Only in-progress services can be completed.")

    content = read_capped(photo, settings.service_evidence_max_bytes)
    if content is None:
        raise HTTPException(status_code=413, detail=PHOTO_MAX_SIZE_MESSAGE)
    photo_type = detect_photo_type(content[:12])
    if photo_type is None:
        raise HTTPException(status_code=415, detail=PHOTO_TYPE_MESSAGE)

    # The upload happens before any write: if it fails, nothing is recorded and the service stays in progress.
    key = f"services/{service_id}/{uuid4()}.{photo_type.extension}"
    try:
        storage.upload(key, content, photo_type.content_type)
    except EvidenceStorageError as error:
        session.rollback()
        raise HTTPException(status_code=502, detail=PHOTO_STORAGE_MESSAGE) from error

    now = utc_now()
    session.execute(
        update(Servicio)
        .where(Servicio.id == service_id)
        .values(
            status="completed",
            delivery_evidence_key=key,
            completed_at=now,
            completion_notified_at=now,
            payout_deadline_at=now + timedelta(hours=settings.service_claim_window_hours),
        )
    )
    session.commit()
    return _visible_detail(session, viewer, service_id)


@router.get("/services/{service_id}/delivery-photo", response_model=DeliveryPhotoUrl)
def get_provider_delivery_photo(
    service_id: UUID,
    current_user: CurrentUser,
    session: Database,
    storage: Storage,
    settings: AppSettings,
) -> DeliveryPhotoUrl:
    viewer = _provider_viewer(session, current_user)
    row = session.execute(
        select(Servicio.delivery_evidence_key).where(Servicio.id == service_id, *viewer.visibility())
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Service not found.")
    if row[0] is None:
        raise HTTPException(status_code=404, detail="Delivery photo not found.")
    try:
        return signed_delivery_photo(storage, row[0], settings.service_evidence_url_ttl_seconds)
    except EvidenceStorageError as error:
        raise HTTPException(status_code=502, detail=DELIVERY_PHOTO_LINK_MESSAGE) from error
