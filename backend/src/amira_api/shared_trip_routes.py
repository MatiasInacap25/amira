"""Provider shared trips: publish a paid service as a trip, close it, list trips, and list the caller's drivers.

Ownership comes from the verified JWT through the provider-profile helper the other provider routes use. A service,
vehicle or driver that is not the caller's answers 404, like any resource the caller cannot see; a customer account
answers 403 on these routes.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.models import Conductor, Servicio, Usuario, Vehiculo, Viaje
from amira_api.public_routes import MAX_OFFSET, MAX_PAGE_SIZE, _owned_provider
from amira_api.shared_trip_schemas import (
    ProviderDriverItem,
    ProviderDriverPage,
    ProviderSharedTripItem,
    ProviderSharedTripPage,
    SharedTripClosed,
    SharedTripPublished,
    SharedTripPublishRequest,
)
from amira_api.shared_trip_service import (
    SharedTripConflict,
    close_shared_trip,
    provider_drivers_query,
    publish_shared_trip,
)

router = APIRouter(tags=["provider-shared-trips"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]

SERVICE_NOT_FOUND_MESSAGE = "Service not found."
VEHICLE_NOT_FOUND_MESSAGE = "Vehículo no encontrado."
DRIVER_NOT_FOUND_MESSAGE = "Conductor no encontrado."
TRIP_NOT_FOUND_MESSAGE = "Viaje compartido no encontrado."


@router.post("/api/provider/services/{service_id}/shared-trip", response_model=SharedTripPublished, status_code=201)
def publish_provider_shared_trip(
    service_id: UUID,
    payload: SharedTripPublishRequest,
    current_user: CurrentUser,
    session: Database,
) -> SharedTripPublished:
    owner_account_id, profile_id = _owned_provider(session, current_user)
    service = session.execute(
        select(Servicio).where(Servicio.id == service_id, Servicio.profile_id == profile_id).with_for_update()
    ).scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=404, detail=SERVICE_NOT_FOUND_MESSAGE)
    vehicle = session.execute(
        select(Vehiculo).where(Vehiculo.id == payload.vehicle_id, Vehiculo.profile_id == profile_id)
    ).scalar_one_or_none()
    if vehicle is None:
        raise HTTPException(status_code=404, detail=VEHICLE_NOT_FOUND_MESSAGE)
    driver_id = session.execute(
        provider_drivers_query(profile_id, owner_account_id).where(Conductor.id == payload.driver_id)
    ).scalar_one_or_none()
    if driver_id is None:
        raise HTTPException(status_code=404, detail=DRIVER_NOT_FOUND_MESSAGE)
    driver = session.get(Conductor, driver_id)

    try:
        trip = publish_shared_trip(session, service=service, vehicle=vehicle, driver=driver, now=utc_now())
    except SharedTripConflict as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    session.commit()
    return SharedTripPublished(trip_id=trip.id)


@router.post("/api/provider/shared-trips/{trip_id}/close", response_model=SharedTripClosed)
def close_provider_shared_trip(
    trip_id: UUID,
    current_user: CurrentUser,
    session: Database,
) -> SharedTripClosed:
    _, profile_id = _owned_provider(session, current_user)
    trip = session.execute(
        select(Viaje).where(Viaje.id == trip_id, Viaje.profile_id == profile_id).with_for_update()
    ).scalar_one_or_none()
    if trip is None:
        raise HTTPException(status_code=404, detail=TRIP_NOT_FOUND_MESSAGE)
    close_shared_trip(trip)
    session.commit()
    return SharedTripClosed(trip_id=trip.id, accepts_requests=trip.accepts_requests)


@router.get("/api/provider/shared-trips", response_model=ProviderSharedTripPage)
def list_provider_shared_trips(
    current_user: CurrentUser,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> ProviderSharedTripPage:
    _, profile_id = _owned_provider(session, current_user)
    filters = (Viaje.profile_id == profile_id,)
    total = session.execute(select(func.count()).select_from(Viaje).where(*filters)).scalar_one()
    joined = (
        select(func.count())
        .select_from(Servicio)
        .where(Servicio.trip_id == Viaje.id)
        .scalar_subquery()
    )
    rows = session.execute(
        select(
            Viaje.id.label("trip_id"),
            Viaje.accepts_requests.label("accepts_requests"),
            Viaje.origin.label("origin"),
            Viaje.destination.label("destination"),
            Viaje.departure_at.label("departure_at"),
            joined.label("joined_services"),
        )
        .where(*filters)
        .order_by(Viaje.departure_at.asc().nulls_last(), Viaje.id.asc())
        .limit(limit)
        .offset(offset)
    ).mappings().all()
    items = [
        ProviderSharedTripItem(
            trip_id=row["trip_id"],
            status="open" if row["accepts_requests"] else "closed",
            origin=row["origin"],
            destination=row["destination"],
            departure_at=row["departure_at"],
            joined_services=int(row["joined_services"]),
        )
        for row in rows
    ]
    return ProviderSharedTripPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/api/provider/drivers", response_model=ProviderDriverPage)
def list_provider_drivers(current_user: CurrentUser, session: Database) -> ProviderDriverPage:
    owner_account_id, profile_id = _owned_provider(session, current_user)
    rows = session.execute(
        provider_drivers_query(profile_id, owner_account_id).order_by(Usuario.first_name, Conductor.id)
    ).all()
    items = [
        ProviderDriverItem(driver_id=driver_id, name=f"{first_name} {last_name}")
        for driver_id, first_name, last_name in rows
    ]
    return ProviderDriverPage(items=items)
