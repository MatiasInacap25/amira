"""Read-only, allowlisted public catalog and shared-route endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.models import (
    Conductor,
    FormularioServicio,
    ParadaViaje,
    Perfil,
    RolPerfil,
    RolUsuario,
    ServicioDisponible,
    TipoServicio,
    Usuario,
    Vehiculo,
    Viaje,
)
from amira_api.public_schemas import (
    PublicRouteStop,
    PublicProviderDriver,
    PublicProviderProfile,
    PublicProviderService,
    PublicProviderVehicle,
    PublicServiceItem,
    PublicServicePage,
    PublicSharedRoute,
    PublicSharedRoutePage,
    ServiceRequestCreate,
    ServiceRequestCreated,
)

router = APIRouter(prefix="/api", tags=["public marketplace"])
MAX_PAGE_SIZE = 50
MAX_OFFSET = 5000
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]


def _clean_filter(value: str | None) -> str | None:
    normalized = value.strip() if value is not None else None
    return normalized or None


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/providers/{profile_id}", response_model=PublicProviderProfile)
def get_public_provider_profile(profile_id: UUID, session: Database) -> PublicProviderProfile:
    profile = session.execute(
        select(
            Perfil.id.label("profile_id"),
            Perfil.name.label("provider_name"),
            Perfil.kind.label("kind"),
            Perfil.description.label("description"),
            Perfil.location.label("location"),
            Perfil.public_activated_at.label("public_activated_at"),
            Usuario.first_name.label("owner_first_name"),
            Usuario.last_name.label("owner_last_name"),
        )
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
        .join(RolPerfil, RolPerfil.id == Perfil.role_id)
        .where(
            Perfil.id == profile_id,
            Perfil.public_activated_at.is_not(None),
            Perfil.kind.in_(("company", "independent_driver")),
            RolPerfil.code.in_(("company", "independent_driver")),
        )
    ).mappings().one_or_none()
    if profile is None or profile["public_activated_at"] is None:
        raise HTTPException(status_code=404, detail="Provider profile not found.")

    driver_rows = session.execute(
        select(Usuario.first_name.label("first_name"), Usuario.last_name.label("last_name"))
        .join(Conductor, Conductor.user_id == Usuario.id)
        .where(Conductor.employer_profile_id == profile_id)
        .order_by(Usuario.first_name.asc(), Usuario.last_name.asc(), Usuario.id.asc())
    ).mappings().all()
    service_rows = session.execute(
        select(
            TipoServicio.id.label("service_type_id"),
            TipoServicio.name.label("name"),
        )
        .join(ServicioDisponible, ServicioDisponible.service_type_id == TipoServicio.id)
        .where(ServicioDisponible.profile_id == profile_id)
        .order_by(TipoServicio.name.asc(), TipoServicio.id.asc())
    ).mappings().all()
    vehicle_rows = session.execute(
        select(
            Vehiculo.brand.label("brand"),
            Vehiculo.model.label("model"),
            Vehiculo.year.label("year"),
            Vehiculo.maximum_weight.label("maximum_weight"),
        )
        .where(Vehiculo.profile_id == profile_id)
        .order_by(Vehiculo.brand.asc(), Vehiculo.model.asc(), Vehiculo.year.asc().nulls_last())
    ).mappings().all()

    return PublicProviderProfile(
        profile_id=profile["profile_id"],
        provider_name=(
            f"{profile['owner_first_name']} {profile['owner_last_name']}"
            if profile["kind"] == "independent_driver"
            else profile["provider_name"]
        ),
        kind=profile["kind"],
        description=profile["description"],
        location=profile["location"],
        owner_name=f"{profile['owner_first_name']} {profile['owner_last_name']}",
        drivers=[PublicProviderDriver(**row) for row in driver_rows],
        services=[PublicProviderService(**row) for row in service_rows],
        vehicles=[PublicProviderVehicle(**row) for row in vehicle_rows],
    )


@router.post(
    "/service-requests",
    response_model=ServiceRequestCreated,
    status_code=201,
)
def create_service_request(
    payload: ServiceRequestCreate,
    current_user: CurrentUser,
    session: Database,
) -> ServiceRequestCreated:
    account = session.execute(
        select(Usuario.id, RolUsuario.code)
        .join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .where(Usuario.auth_user_id == current_user.id)
    ).one_or_none()
    if account is None:
        raise HTTPException(status_code=403, detail="A provisioned customer account is required.")
    customer_id, role_code = account
    if role_code != "client":
        raise HTTPException(status_code=403, detail="Only customer accounts can request a quote.")

    matching_service = session.execute(
        select(ServicioDisponible.service_type_id)
        .join(Perfil, Perfil.id == ServicioDisponible.profile_id)
        .join(RolPerfil, RolPerfil.id == Perfil.role_id)
        .where(
            Perfil.id == payload.profile_id,
            Perfil.public_activated_at.is_not(None),
            Perfil.kind.in_(("company", "independent_driver")),
            RolPerfil.code.in_(("company", "independent_driver")),
            ServicioDisponible.service_type_id == payload.service_type_id,
        )
    ).scalar_one_or_none()
    if matching_service is None:
        raise HTTPException(status_code=404, detail="Provider or available service not found.")

    request = FormularioServicio(
        id=uuid4(),
        profile_id=payload.profile_id,
        service_type_id=matching_service,
        origin=payload.origin,
        destination=payload.destination,
        estimated_weight=payload.estimated_weight,
        estimated_volume=payload.estimated_volume,
        requested_at=payload.requested_at,
        status="pending",
        description=payload.description,
        customer_id=customer_id,
        is_exclusive=False,
        cargo_measurements=payload.cargo_measurements,
    )
    session.add(request)
    session.commit()
    return ServiceRequestCreated(request_id=request.id, status=request.status)


@router.get("/services", response_model=PublicServicePage)
def list_services(
    session: Annotated[Session, Depends(get_db_session)],
    q: Annotated[str | None, Query(max_length=120)] = None,
    category: Annotated[str | None, Query(max_length=120)] = None,
    location: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> PublicServicePage:
    filters = [Perfil.public_activated_at.is_not(None)]
    query = _clean_filter(q)
    category_filter = _clean_filter(category)
    location_filter = _clean_filter(location)

    if query:
        pattern = _contains(query)
        filters.append(
            or_(
                Perfil.name.ilike(pattern, escape="\\"),
                Usuario.first_name.ilike(pattern, escape="\\"),
                Usuario.last_name.ilike(pattern, escape="\\"),
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
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
        .join(ServicioDisponible, ServicioDisponible.profile_id == Perfil.id)
        .join(TipoServicio, TipoServicio.id == ServicioDisponible.service_type_id)
        .where(*filters)
    )
    total = session.execute(select(func.count()).select_from(joins.subquery())).scalar_one()

    rows = session.execute(
        select(
            Perfil.id.label("profile_id"),
            case(
                (Perfil.kind == "independent_driver", Usuario.first_name + " " + Usuario.last_name),
                else_=Perfil.name,
            ).label("provider_name"),
            TipoServicio.name.label("category"),
            Perfil.description.label("description"),
            Perfil.location.label("location"),
        )
        .select_from(Perfil)
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
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

    filters = [
        Viaje.is_published.is_(True),
        Viaje.accepts_requests.is_(True),
        Viaje.profile_id.in_(select(Perfil.id).where(Perfil.public_activated_at.is_not(None))),
    ]
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
            Viaje.profile_id.label("profile_id"),
            case(
                (Perfil.kind == "independent_driver", Usuario.first_name + " " + Usuario.last_name),
                else_=Perfil.name,
            ).label("provider_name"),
            Viaje.origin.label("origin"),
            Viaje.destination.label("destination"),
            Viaje.departure_at.label("departure_at"),
        )
        .join(Perfil, Perfil.id == Viaje.profile_id)
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
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
