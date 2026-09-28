"""Read-only, allowlisted public catalog and shared-route endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from amira_api.db import get_db_session
from amira_api.models import ParadaViaje, Perfil, ServicioDisponible, TipoServicio, Viaje
from amira_api.public_schemas import (
    PublicRouteStop,
    PublicServiceItem,
    PublicServicePage,
    PublicSharedRoute,
    PublicSharedRoutePage,
)

router = APIRouter(prefix="/api", tags=["public marketplace"])
MAX_PAGE_SIZE = 50
MAX_OFFSET = 5000


def _clean_filter(value: str | None) -> str | None:
    normalized = value.strip() if value is not None else None
    return normalized or None


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/services", response_model=PublicServicePage)
def list_services(
    session: Annotated[Session, Depends(get_db_session)],
    q: Annotated[str | None, Query(max_length=120)] = None,
    category: Annotated[str | None, Query(max_length=120)] = None,
    location: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> PublicServicePage:
    filters = []
    query = _clean_filter(q)
    category_filter = _clean_filter(category)
    location_filter = _clean_filter(location)

    if query:
        pattern = _contains(query)
        filters.append(
            or_(
                Perfil.name.ilike(pattern, escape="\\"),
                Perfil.description.ilike(pattern, escape="\\"),
                TipoServicio.name.ilike(pattern, escape="\\"),
            )
        )
    if category_filter:
        filters.append(TipoServicio.name.ilike(_contains(category_filter), escape="\\"))
    if location_filter:
        filters.append(Perfil.location.ilike(_contains(location_filter), escape="\\"))

    joins = (
        select(Perfil.id, Perfil.name, Perfil.description, Perfil.location, TipoServicio.name)
        .select_from(Perfil)
        .join(ServicioDisponible, ServicioDisponible.profile_id == Perfil.id)
        .join(TipoServicio, TipoServicio.id == ServicioDisponible.service_type_id)
        .where(*filters)
    )
    total = session.execute(select(func.count()).select_from(joins.subquery())).scalar_one()

    rows = session.execute(
        select(
            Perfil.id.label("profile_id"),
            Perfil.name.label("provider_name"),
            TipoServicio.name.label("category"),
            Perfil.description.label("description"),
            Perfil.location.label("location"),
        )
        .select_from(Perfil)
        .join(ServicioDisponible, ServicioDisponible.profile_id == Perfil.id)
        .join(TipoServicio, TipoServicio.id == ServicioDisponible.service_type_id)
        .where(*filters)
        .order_by(Perfil.name.asc(), Perfil.id.asc(), TipoServicio.name.asc())
        .limit(limit)
        .offset(offset)
    ).mappings().all()

    items = [PublicServiceItem(**row, logo_url=None) for row in rows]
    return PublicServicePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/shared-routes", response_model=PublicSharedRoutePage)
def list_shared_routes(
    session: Annotated[Session, Depends(get_db_session)],
    origin: Annotated[str | None, Query(max_length=300)] = None,
    destination: Annotated[str | None, Query(max_length=300)] = None,
    departure_from: Annotated[datetime | None, Query(alias="departureFrom")] = None,
    departure_to: Annotated[datetime | None, Query(alias="departureTo")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> PublicSharedRoutePage:
    if departure_from and departure_to and departure_from > departure_to:
        raise HTTPException(status_code=422, detail="departureFrom must not be after departureTo.")
    if any(
        value is not None and (value.tzinfo is None or value.utcoffset() is None)
        for value in (departure_from, departure_to)
    ):
        raise HTTPException(status_code=422, detail="Departure filters must include a timezone.")

    filters = [Viaje.is_published.is_(True), Viaje.accepts_requests.is_(True)]
    origin_filter = _clean_filter(origin)
    destination_filter = _clean_filter(destination)
    if origin_filter:
        filters.append(Viaje.origin.ilike(_contains(origin_filter), escape="\\"))
    if destination_filter:
        filters.append(Viaje.destination.ilike(_contains(destination_filter), escape="\\"))
    if departure_from:
        filters.append(Viaje.departure_at >= departure_from)
    if departure_to:
        filters.append(Viaje.departure_at <= departure_to)

    total = session.execute(
        select(func.count()).select_from(Viaje).where(*filters)
    ).scalar_one()
    rows = session.execute(
        select(
            Viaje.id.label("trip_id"),
            Perfil.name.label("provider_name"),
            Viaje.origin.label("origin"),
            Viaje.destination.label("destination"),
            Viaje.departure_at.label("departure_at"),
        )
        .join(Perfil, Perfil.id == Viaje.profile_id)
        .where(*filters)
        .order_by(Viaje.departure_at.asc().nulls_last(), Viaje.id.asc())
        .limit(limit)
        .offset(offset)
    ).mappings().all()

    trip_ids = [row["trip_id"] for row in rows]
    stop_rows = (
        session.execute(
            select(
                ParadaViaje.trip_id.label("trip_id"),
                ParadaViaje.order.label("stop_number"),
                ParadaViaje.estimated_at.label("estimated_at"),
            )
            .where(ParadaViaje.trip_id.in_(trip_ids))
            .order_by(ParadaViaje.trip_id.asc(), ParadaViaje.order.asc())
        ).mappings().all()
        if trip_ids
        else []
    )
    stops_by_trip: dict[UUID, list[PublicRouteStop]] = {}
    for row in stop_rows:
        stops_by_trip.setdefault(row["trip_id"], []).append(
            PublicRouteStop(stop_number=row["stop_number"], estimated_at=row["estimated_at"])
        )

    items = [
        PublicSharedRoute(**row, stops=stops_by_trip.get(row["trip_id"], []))
        for row in rows
    ]
    return PublicSharedRoutePage(items=items, total=total, limit=limit, offset=offset)
