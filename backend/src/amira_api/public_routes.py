"""Read-only, allowlisted public catalog and shared-route endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session, aliased

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.models import (
    Chat,
    ChatParticipante,
    Commune,
    Conductor,
    Region,
    FormularioServicio,
    ParadaViaje,
    Perfil,
    RolPerfil,
    RolUsuario,
    Servicio,
    ServicioDisponible,
    TipoServicio,
    Usuario,
    Vehiculo,
    Valoracion,
    Viaje,
)
from amira_api.public_schemas import (
    PublicRouteStop,
    PublicProviderDriver,
    PublicProviderProfile,
    PublicProviderRating,
    PublicProviderRatingSummary,
    PublicProviderService,
    PublicProviderVehicle,
    PublicServiceItem,
    PublicServicePage,
    PublicServiceType,
    PublicServiceTypePage,
    PublicSharedRoute,
    PublicSharedRoutePage,
    ProviderRequestCounts,
    ProviderRequestDecision,
    ProviderRequestItem,
    ProviderRequestPage,
    ProviderServiceDriverAssignment,
    ProviderServiceDriverAssignmentRequest,
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


def _profile_location(commune_name: str | None, region_name: str | None, legacy_location: str | None) -> str | None:
    """Join only the catalog parts that exist; fall back to the legacy free text when none do."""
    parts = [part.strip() for part in (commune_name, region_name) if part and part.strip()]
    if parts:
        return ", ".join(parts)
    return legacy_location


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
            Commune.code.label("commune_code"),
            Commune.name.label("commune_name"),
            Region.name.label("region_name"),
            Usuario.first_name.label("owner_first_name"),
            Usuario.last_name.label("owner_last_name"),
        )
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
        .join(RolPerfil, RolPerfil.id == Perfil.role_id)
        .outerjoin(Commune, Commune.code == Perfil.commune_code)
        .outerjoin(Region, Region.code == Commune.region_code)
        .where(
            Perfil.id == profile_id,
            Perfil.public_activated_at.is_not(None),
            Perfil.kind.in_(("company", "independent_driver")),
            RolPerfil.code.in_(("company", "independent_driver")),
        )
    ).mappings().one_or_none()
    if profile is None or profile["public_activated_at"] is None:
        raise HTTPException(status_code=404, detail="Provider profile not found.")

    owner_user_id = select(Perfil.owner_user_id).where(Perfil.id == profile_id).scalar_subquery()
    driver_rows = session.execute(
        select(
            Usuario.first_name.label("first_name"),
            Usuario.last_name.label("last_name"),
            (Conductor.user_id == owner_user_id).label("is_owner"),
        )
        .join(Conductor, Conductor.user_id == Usuario.id)
        .where(
            or_(
                Conductor.employer_profile_id == profile_id,
                (Conductor.user_id == owner_user_id) & Conductor.employer_profile_id.is_(None),
            )
        )
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
    eligible_ratings = (
        Valoracion.user_id == Servicio.customer_id,
        Servicio.profile_id == profile_id,
        Servicio.completed_at.is_not(None),
    )
    rating_summary = session.execute(
        select(
            func.avg(Valoracion.rating).label("average_rating"),
            func.count(Valoracion.id).label("rating_count"),
        )
        .join(Servicio, Servicio.id == Valoracion.service_id)
        .where(*eligible_ratings)
    ).mappings().one_or_none()
    rating_rows = session.execute(
        select(
            Valoracion.rating.label("rating"),
            Valoracion.comment.label("comment"),
            Valoracion.created_at.label("created_at"),
        )
        .join(Servicio, Servicio.id == Valoracion.service_id)
        .where(*eligible_ratings)
        .order_by(Valoracion.created_at.desc(), Valoracion.id.desc())
        .limit(20)
    ).mappings().all()
    rating_count = int(rating_summary["rating_count"] or 0) if rating_summary else 0

    return PublicProviderProfile(
        profile_id=profile["profile_id"],
        provider_name=(
            f"{profile['owner_first_name']} {profile['owner_last_name']}"
            if profile["kind"] == "independent_driver"
            else profile["provider_name"]
        ),
        kind=profile["kind"],
        description=profile["description"],
        location=_profile_location(profile["commune_name"], profile["region_name"], profile["location"]),
        commune_code=profile["commune_code"],
        commune_name=profile["commune_name"],
        region_name=profile["region_name"],
        owner_name=f"{profile['owner_first_name']} {profile['owner_last_name']}",
        drivers=[PublicProviderDriver(**row) for row in driver_rows],
        services=[PublicProviderService(**row) for row in service_rows],
        vehicles=[PublicProviderVehicle(**row) for row in vehicle_rows],
        ratings=PublicProviderRatingSummary(
            average_rating=(float(rating_summary["average_rating"]) if rating_summary and rating_count else None),
            rating_count=rating_count,
            recent=[PublicProviderRating(**row) for row in rating_rows],
        ),
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

    catalog_codes = {
        row[0]
        for row in session.execute(
            select(Commune.code).where(Commune.code.in_({payload.origin_commune_code, payload.destination_commune_code}))
        ).all()
    }
    for field, code in (
        ("originCommuneCode", payload.origin_commune_code),
        ("destinationCommuneCode", payload.destination_commune_code),
    ):
        if code not in catalog_codes:
            raise HTTPException(
                status_code=422,
                detail=[{"loc": ["body", field], "msg": "Selecciona una comuna válida del catálogo.", "type": "value_error"}],
            )

    request = FormularioServicio(
        id=uuid4(),
        profile_id=payload.profile_id,
        service_type_id=matching_service,
        origin=payload.origin,
        destination=payload.destination,
        origin_commune_code=payload.origin_commune_code,
        destination_commune_code=payload.destination_commune_code,
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


def _owned_provider(session: Session, current_user: AuthenticatedUser) -> tuple[UUID, UUID]:
    account = session.execute(
        select(Usuario.id, RolUsuario.code)
        .join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .where(Usuario.auth_user_id == current_user.id)
    ).one_or_none()
    if account is None:
        raise HTTPException(status_code=403, detail="A provider account is required.")
    account_id, role_code = account
    expected_profile_role = {
        "company_owner": ("company", "company"),
        "independent_driver": ("independent_driver", "independent_driver"),
    }.get(role_code)
    if expected_profile_role is None:
        raise HTTPException(status_code=403, detail="Only provider accounts can manage requests.")
    profile_kind, profile_role = expected_profile_role
    profile_id = session.execute(
        select(Perfil.id)
        .join(RolPerfil, RolPerfil.id == Perfil.role_id)
        .where(
            Perfil.owner_user_id == account_id,
            Perfil.kind == profile_kind,
            RolPerfil.code == profile_role,
        )
        .limit(1)
    ).scalar_one_or_none()
    if profile_id is None:
        raise HTTPException(status_code=403, detail="An owned provider profile is required.")
    return account_id, profile_id


PROVIDER_REQUEST_STATUSES = ("pending", "accepted", "rejected")


def _provider_status_filter(status: str | None) -> str | None:
    if status is None:
        return None
    if status not in PROVIDER_REQUEST_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["query", "status"],
                    "msg": "Selecciona un estado válido: pending, accepted o rejected.",
                    "type": "value_error",
                }
            ],
        )
    return status


def _customer_name_for_provider(status: str, first_name: str, last_name: str | None) -> tuple[str, str | None]:
    """Providers see the customer's first name before acceptance; the last name is shared only after it."""
    return first_name, (last_name if status == "accepted" else None)


def _provider_request_rows(profile_id: UUID) -> Select:
    origin_commune = aliased(Commune)
    origin_region = aliased(Region)
    destination_commune = aliased(Commune)
    destination_region = aliased(Region)
    return (
        select(
            FormularioServicio.id.label("request_id"),
            FormularioServicio.status.label("status"),
            FormularioServicio.origin.label("origin"),
            FormularioServicio.destination.label("destination"),
            FormularioServicio.requested_at.label("requested_at"),
            FormularioServicio.created_at.label("created_at"),
            FormularioServicio.estimated_weight.label("estimated_weight"),
            FormularioServicio.estimated_volume.label("estimated_volume"),
            FormularioServicio.description.label("description"),
            FormularioServicio.cargo_measurements.label("cargo_measurements"),
            FormularioServicio.is_exclusive.label("is_exclusive"),
            FormularioServicio.origin_commune_code.label("origin_commune_code"),
            origin_commune.name.label("origin_commune_name"),
            origin_region.name.label("origin_region_name"),
            FormularioServicio.destination_commune_code.label("destination_commune_code"),
            destination_commune.name.label("destination_commune_name"),
            destination_region.name.label("destination_region_name"),
            Usuario.first_name.label("customer_first_name"),
            Usuario.last_name.label("customer_last_name"),
            TipoServicio.name.label("service_name"),
            Chat.id.label("chat_id"),
        )
        .join(TipoServicio, TipoServicio.id == FormularioServicio.service_type_id)
        .join(Usuario, Usuario.id == FormularioServicio.customer_id)
        .outerjoin(Chat, Chat.form_id == FormularioServicio.id)
        .outerjoin(origin_commune, origin_commune.code == FormularioServicio.origin_commune_code)
        .outerjoin(origin_region, origin_region.code == origin_commune.region_code)
        .outerjoin(destination_commune, destination_commune.code == FormularioServicio.destination_commune_code)
        .outerjoin(destination_region, destination_region.code == destination_commune.region_code)
        .where(FormularioServicio.profile_id == profile_id)
    )


def _provider_request_item(row) -> ProviderRequestItem:
    payload = dict(row)
    first_name, last_name = _customer_name_for_provider(
        payload["status"], payload.pop("customer_first_name"), payload.pop("customer_last_name")
    )
    return ProviderRequestItem(**payload, customer_first_name=first_name, customer_last_name=last_name)


def _provider_request_counts(session: Session, profile_id: UUID) -> ProviderRequestCounts:
    # Counts ignore the status filter so each tab can show its badge while another tab is open.
    status_rows = session.execute(
        select(FormularioServicio.status, func.count())
        .where(FormularioServicio.profile_id == profile_id)
        .group_by(FormularioServicio.status)
    ).all()
    by_status = dict(status_rows)
    return ProviderRequestCounts(**{status: int(by_status.get(status, 0)) for status in PROVIDER_REQUEST_STATUSES})


@router.get("/provider/requests", response_model=ProviderRequestPage)
def list_provider_requests(
    current_user: CurrentUser,
    session: Database,
    status: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> ProviderRequestPage:
    _, profile_id = _owned_provider(session, current_user)
    status_filter = _provider_status_filter(status)
    status_clause = [FormularioServicio.status == status_filter] if status_filter else []
    counts = _provider_request_counts(session, profile_id)
    total = session.execute(
        select(func.count())
        .select_from(FormularioServicio)
        .where(FormularioServicio.profile_id == profile_id, *status_clause)
    ).scalar_one()
    rows = session.execute(
        _provider_request_rows(profile_id)
        .where(*status_clause)
        .order_by(FormularioServicio.created_at.desc(), FormularioServicio.id.desc())
        .limit(limit)
        .offset(offset)
    ).mappings().all()
    return ProviderRequestPage(
        items=[_provider_request_item(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        counts=counts,
    )


@router.get("/provider/requests/{request_id}", response_model=ProviderRequestItem)
def get_provider_request(request_id: UUID, current_user: CurrentUser, session: Database) -> ProviderRequestItem:
    _, profile_id = _owned_provider(session, current_user)
    # Requests owned by another profile and unknown ids both return 404, so existence is not leaked.
    row = session.execute(
        _provider_request_rows(profile_id).where(FormularioServicio.id == request_id)
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Provider request not found.")
    return _provider_request_item(row)


def _decide_provider_request(
    request_id: UUID,
    decision: str,
    current_user: AuthenticatedUser,
    session: Session,
) -> ProviderRequestDecision:
    account_id, profile_id = _owned_provider(session, current_user)
    request = session.execute(
        select(FormularioServicio)
        .where(FormularioServicio.id == request_id, FormularioServicio.profile_id == profile_id)
        .with_for_update()
    ).scalar_one_or_none()
    if request is None:
        raise HTTPException(status_code=404, detail="Provider request not found.")

    chats = session.execute(select(Chat).where(Chat.form_id == request.id)).scalars().all()
    if request.status == decision:
        if decision == "accepted" and len(chats) != 1:
            raise HTTPException(status_code=409, detail="Accepted request has an inconsistent chat state.")
        if decision == "rejected" and chats:
            raise HTTPException(status_code=409, detail="Rejected request has an inconsistent chat state.")
        session.commit()
        return ProviderRequestDecision(
            request_id=request.id,
            status=request.status,
            chat_id=chats[0].id if chats else None,
        )
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="This request has already been decided.")
    if chats:
        raise HTTPException(status_code=409, detail="Pending request already has a chat.")

    try:
        request.status = decision
        chat_id = None
        if decision == "accepted":
            chat_id = uuid4()
            session.add(Chat(id=chat_id, form_id=request.id))
            session.flush()
            session.add_all([
                ChatParticipante(user_id=request.customer_id, chat_id=chat_id),
                ChatParticipante(user_id=account_id, chat_id=chat_id),
            ])
        session.commit()
    except Exception:
        session.rollback()
        raise
    return ProviderRequestDecision(request_id=request.id, status=request.status, chat_id=chat_id)


@router.post("/provider/requests/{request_id}/accept", response_model=ProviderRequestDecision)
def accept_provider_request(request_id: UUID, current_user: CurrentUser, session: Database) -> ProviderRequestDecision:
    return _decide_provider_request(request_id, "accepted", current_user, session)


@router.post("/provider/requests/{request_id}/reject", response_model=ProviderRequestDecision)
def reject_provider_request(request_id: UUID, current_user: CurrentUser, session: Database) -> ProviderRequestDecision:
    return _decide_provider_request(request_id, "rejected", current_user, session)


@router.put("/provider/services/{service_id}/driver", response_model=ProviderServiceDriverAssignment)
def assign_provider_service_driver(
    service_id: UUID,
    payload: ProviderServiceDriverAssignmentRequest,
    current_user: CurrentUser,
    session: Database,
) -> ProviderServiceDriverAssignment:
    owner_account_id, profile_id = _owned_provider(session, current_user)
    service = session.execute(
        select(Servicio)
        .where(Servicio.id == service_id, Servicio.profile_id == profile_id)
        .with_for_update()
    ).scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found.")

    driver = session.execute(
        select(Conductor)
        .join(Usuario, Usuario.id == Conductor.user_id)
        .join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .where(
            Conductor.id == payload.driver_id,
            or_(
                and_(Conductor.employer_profile_id == profile_id, RolUsuario.code == "company_driver"),
                and_(
                    Conductor.user_id == owner_account_id,
                    or_(Conductor.employer_profile_id.is_(None), Conductor.employer_profile_id == profile_id),
                ),
            ),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if driver is None:
        raise HTTPException(status_code=404, detail="Driver not found for this provider profile.")

    service.contracted_driver_id = driver.id
    session.commit()
    return ProviderServiceDriverAssignment(service_id=service.id, driver_id=driver.id)


@router.get("/service-types", response_model=PublicServiceTypePage)
def list_service_types(session: Annotated[Session, Depends(get_db_session)]) -> PublicServiceTypePage:
    rows = session.execute(
        select(TipoServicio.id.label("id"), TipoServicio.slug.label("slug"), TipoServicio.name.label("name"))
        .order_by(TipoServicio.name.asc(), TipoServicio.id.asc())
    ).mappings().all()
    return PublicServiceTypePage(items=[PublicServiceType(**row) for row in rows])


@router.get("/services", response_model=PublicServicePage)
def list_services(
    session: Annotated[Session, Depends(get_db_session)],
    q: Annotated[str | None, Query(max_length=120)] = None,
    service_type: Annotated[
        str | None,
        Query(alias="serviceType", max_length=120, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"),
    ] = None,
    region_code: Annotated[str | None, Query(alias="regionCode", pattern=r"^\d{2}$")] = None,
    commune_code: Annotated[str | None, Query(alias="communeCode", pattern=r"^\d{5}$")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> PublicServicePage:
    filters = [Perfil.public_activated_at.is_not(None)]
    query = _clean_filter(q)

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
    if service_type:
        filters.append(TipoServicio.slug == service_type)
    if region_code:
        filters.append(Region.code == region_code)
    if commune_code:
        filters.append(Commune.code == commune_code)

    total = session.execute(
        select(func.count(func.distinct(Perfil.id)))
        .select_from(Perfil)
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
        .join(ServicioDisponible, ServicioDisponible.profile_id == Perfil.id)
        .join(TipoServicio, TipoServicio.id == ServicioDisponible.service_type_id)
        .outerjoin(Commune, Commune.code == Perfil.commune_code)
        .outerjoin(Region, Region.code == Commune.region_code)
        .where(*filters)
    ).scalar_one()

    rows = session.execute(
        select(
            Perfil.id.label("profile_id"),
            case(
                (Perfil.kind == "independent_driver", Usuario.first_name + " " + Usuario.last_name),
                else_=Perfil.name,
            ).label("provider_name"),
            func.min(TipoServicio.name).label("category"),
            Perfil.description.label("description"),
            case(
                (Commune.name.is_not(None), Commune.name + ", " + Region.name),
                else_=None,
            ).label("location"),
            Commune.code.label("commune_code"),
            Commune.name.label("commune_name"),
            Region.name.label("region_name"),
            func.json_agg(
                aggregate_order_by(
                    func.json_build_object(
                        "serviceTypeId", TipoServicio.id,
                        "name", TipoServicio.name,
                    ),
                    TipoServicio.name,
                )
            ).label("services"),
        )
        .select_from(Perfil)
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
        .join(ServicioDisponible, ServicioDisponible.profile_id == Perfil.id)
        .join(TipoServicio, TipoServicio.id == ServicioDisponible.service_type_id)
        .outerjoin(Commune, Commune.code == Perfil.commune_code)
        .outerjoin(Region, Region.code == Commune.region_code)
        .where(*filters)
        .group_by(
            Perfil.id,
            Perfil.kind,
            Perfil.name,
            Perfil.description,
            Commune.code,
            Commune.name,
            Region.name,
            Usuario.first_name,
            Usuario.last_name,
        )
        .order_by(Perfil.name.asc(), Perfil.id.asc())
        .limit(limit)
        .offset(offset)
    ).mappings().all()

    items = [PublicServiceItem(**row, logo_url=None) for row in rows]
    return PublicServicePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/shared-routes", response_model=PublicSharedRoutePage)
def list_shared_routes(
    session: Annotated[Session, Depends(get_db_session)],
    origin_commune_code: Annotated[str | None, Query(alias="originCommuneCode", pattern=r"^\d{5}$")] = None,
    destination_commune_code: Annotated[str | None, Query(alias="destinationCommuneCode", pattern=r"^\d{5}$")] = None,
    departure_from: Annotated[datetime | None, Query(alias="departureFrom")] = None,
    departure_to: Annotated[datetime | None, Query(alias="departureTo")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> PublicSharedRoutePage:
    if departure_from and departure_to and departure_from > departure_to:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["query", "departureFrom"],
                    "msg": "La salida inicial no puede ser posterior a la salida final.",
                    "type": "departure_window_inverted",
                }
            ],
        )
    if any(
        value is not None and (value.tzinfo is None or value.utcoffset() is None)
        for value in (departure_from, departure_to)
    ):
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["query", "departureFrom"],
                    "msg": "Las fechas de salida deben incluir zona horaria.",
                    "type": "departure_timezone",
                }
            ],
        )

    filters = [
        Viaje.is_published.is_(True),
        Viaje.accepts_requests.is_(True),
        Viaje.profile_id.in_(select(Perfil.id).where(Perfil.public_activated_at.is_not(None))),
    ]
    if origin_commune_code:
        filters.append(Viaje.origin_commune_code == origin_commune_code)
    if destination_commune_code:
        filters.append(Viaje.destination_commune_code == destination_commune_code)
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
            Viaje.origin_commune_code.label("origin_commune_code"),
            Viaje.destination_commune_code.label("destination_commune_code"),
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
