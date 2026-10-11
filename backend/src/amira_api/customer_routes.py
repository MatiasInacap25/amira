"""Authenticated customer service history and one-time service ratings."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.clock import as_utc, utc_now
from amira_api.customer_schemas import (
    CustomerClaimCreate,
    CustomerRatingCreate,
    CustomerServiceItem,
    CustomerServicePage,
    CustomerServiceRating,
)
from amira_api.db import get_db_session
from amira_api.evidence_storage import EvidenceStorage, EvidenceStorageError, get_evidence_storage_resolver
from amira_api.provider_service_schemas import DeliveryPhotoUrl, ServiceDetail
from amira_api.service_views import (
    CLAIM_OPEN,
    DELIVERY_PHOTO_LINK_MESSAGE,
    load_assignments,
    provider_display_name,
    service_rows,
    shape_detail,
    signed_delivery_photo,
)
from amira_api.settings import Settings, get_settings
from amira_api.models import (
    Desembolso,
    FormularioServicio,
    Perfil,
    Reclamo,
    RolUsuario,
    Servicio,
    TipoServicio,
    Usuario,
    Valoracion,
)

router = APIRouter(prefix="/api/customer", tags=["customer"])
MAX_PAGE_SIZE = 50
MAX_OFFSET = 5000
RATING_CONSTRAINT = "uq_rating_service"
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
ResolveStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_evidence_storage_resolver)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _customer_account_id(session: Session, current_user: AuthenticatedUser) -> UUID:
    account = session.execute(
        select(Usuario.id, RolUsuario.code)
        .join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .where(Usuario.auth_user_id == current_user.id)
    ).one_or_none()
    if account is None:
        raise HTTPException(status_code=403, detail="A provisioned customer account is required.")
    account_id, role_code = account
    if role_code != "client":
        raise HTTPException(status_code=403, detail="Only customer accounts can access service history.")
    return account_id


def _constraint_name(error: IntegrityError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def _customer_services_relation(statement: Select, account_id: UUID) -> Select:
    """Apply the one join path that defines a customer's reachable services.

    Both the page total and the page items use this relation, so the total never
    counts a service that the item query cannot return.
    """
    return (
        statement.select_from(Servicio)
        .join(Perfil, Perfil.id == Servicio.profile_id)
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
        .join(FormularioServicio, FormularioServicio.id == Servicio.form_id)
        .join(TipoServicio, TipoServicio.id == FormularioServicio.service_type_id)
        .where(Servicio.customer_id == account_id)
    )


@router.get("/services", response_model=CustomerServicePage)
def list_customer_services(
    current_user: CurrentUser,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> CustomerServicePage:
    account_id = _customer_account_id(session, current_user)
    total = session.execute(
        _customer_services_relation(select(func.count(Servicio.id)), account_id)
    ).scalar_one()
    rows = session.execute(
        _customer_services_relation(
            select(
                Servicio.id.label("service_id"),
                Servicio.status.label("status"),
                Perfil.id.label("provider_profile_id"),
                Perfil.kind.label("provider_kind"),
                Perfil.name.label("profile_name"),
                Usuario.first_name.label("owner_first_name"),
                Usuario.last_name.label("owner_last_name"),
                TipoServicio.name.label("service_type_name"),
                Servicio.completed_at.label("completed_at"),
                Valoracion.rating.label("rating_value"),
                Valoracion.comment.label("rating_comment"),
                Valoracion.created_at.label("rating_created_at"),
            ),
            account_id,
        )
        .outerjoin(Valoracion, Valoracion.service_id == Servicio.id)
        .order_by(Servicio.created_at.desc(), Servicio.id.desc())
        .limit(limit)
        .offset(offset)
    ).mappings().all()

    items = [
        CustomerServiceItem(
            service_id=row["service_id"],
            status=row["status"],
            provider_profile_id=row["provider_profile_id"],
            provider_name=provider_display_name(
                row["provider_kind"],
                row["profile_name"],
                row["owner_first_name"],
                row["owner_last_name"],
            ),
            service_type_name=row["service_type_name"],
            completed_at=row["completed_at"],
            rating=(
                CustomerServiceRating(
                    rating=row["rating_value"],
                    comment=row["rating_comment"],
                    created_at=row["rating_created_at"],
                )
                if row["rating_value"] is not None
                else None
            ),
        )
        for row in rows
    ]
    return CustomerServicePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/services/{service_id}", response_model=ServiceDetail)
def get_customer_service(service_id: UUID, current_user: CurrentUser, session: Database) -> ServiceDetail:
    account_id = _customer_account_id(session, current_user)
    row = session.execute(
        service_rows(Servicio.id == service_id, Servicio.customer_id == account_id)
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Service not found.")
    return shape_detail(
        row, "customer", can_manage=False, viewer_assigned=False, assignments=load_assignments(session, service_id)
    )


@router.get("/services/{service_id}/delivery-photo", response_model=DeliveryPhotoUrl)
def get_customer_delivery_photo(
    service_id: UUID,
    current_user: CurrentUser,
    session: Database,
    resolve_storage: ResolveStorage,
    settings: AppSettings,
) -> DeliveryPhotoUrl:
    account_id = _customer_account_id(session, current_user)
    row = session.execute(
        select(Servicio.delivery_evidence_key).where(Servicio.id == service_id, Servicio.customer_id == account_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Service not found.")
    if row[0] is None:
        raise HTTPException(status_code=404, detail="Delivery photo not found.")
    # Storage is resolved only now, so a customer who cannot see the photo gets 404 even when storage is unconfigured.
    storage = resolve_storage()
    try:
        return signed_delivery_photo(storage, row[0], settings.service_evidence_url_ttl_seconds)
    except EvidenceStorageError as error:
        raise HTTPException(status_code=502, detail=DELIVERY_PHOTO_LINK_MESSAGE) from error


@router.post(
    "/services/{service_id}/rating",
    response_model=CustomerServiceRating,
    status_code=201,
)
def create_customer_service_rating(
    service_id: UUID,
    payload: CustomerRatingCreate,
    current_user: CurrentUser,
    session: Database,
) -> CustomerServiceRating:
    account_id = _customer_account_id(session, current_user)
    service = session.execute(
        select(Servicio)
        .where(Servicio.id == service_id, Servicio.customer_id == account_id)
        .with_for_update()
    ).scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found.")
    if service.completed_at is None:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["path", "service_id"],
                    "msg": "Solo puedes valorar servicios completados.",
                    "type": "service_not_completed",
                }
            ],
        )

    rating = Valoracion(
        id=uuid4(),
        service_id=service.id,
        user_id=account_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    session.add(rating)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        if _constraint_name(error) != RATING_CONSTRAINT:
            raise
        raise HTTPException(
            status_code=409,
            detail=[
                {
                    "loc": ["path", "service_id"],
                    "msg": "Este servicio ya tiene una valoración.",
                    "type": "already_rated",
                }
            ],
        ) from None
    session.refresh(rating)
    stored = CustomerServiceRating(rating=rating.rating, comment=rating.comment, created_at=rating.created_at)
    session.commit()
    return stored


def _lock_customer_service(session: Session, account_id: UUID, service_id: UUID) -> Servicio:
    """Lock the customer's own service row; a service the customer does not own is a 404."""
    service = session.execute(
        select(Servicio).where(Servicio.id == service_id, Servicio.customer_id == account_id).with_for_update()
    ).scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found.")
    return service


def _has_open_claim(session: Session, service_id: UUID) -> bool:
    return (
        session.execute(
            select(Reclamo.id).where(Reclamo.service_id == service_id, Reclamo.status == CLAIM_OPEN).limit(1)
        ).first()
        is not None
    )


def _payout_released(session: Session, service_id: UUID) -> bool:
    """True once a payout exists for the service. Checked under the service lock, like the release job does."""
    return session.execute(select(Desembolso.id).where(Desembolso.service_id == service_id).limit(1)).first() is not None


def _customer_service_detail(session: Session, account_id: UUID, service_id: UUID) -> ServiceDetail:
    row = session.execute(
        service_rows(Servicio.id == service_id, Servicio.customer_id == account_id)
    ).mappings().one()
    return shape_detail(
        row, "customer", can_manage=False, viewer_assigned=False, assignments=load_assignments(session, service_id)
    )


@router.post("/services/{service_id}/claims", response_model=ServiceDetail)
def create_customer_service_claim(
    service_id: UUID,
    payload: CustomerClaimCreate,
    current_user: CurrentUser,
    session: Database,
) -> ServiceDetail:
    account_id = _customer_account_id(session, current_user)
    service = _lock_customer_service(session, account_id, service_id)
    if _has_open_claim(session, service.id):
        raise HTTPException(status_code=409, detail="This service already has an open claim.")
    if service.status != "completed":
        raise HTTPException(status_code=409, detail="Only completed services can be claimed.")
    if service.customer_consent_at is not None:
        raise HTTPException(status_code=409, detail="Consent was already given for this service.")
    now = utc_now()
    if service.payout_deadline_at is None or now >= as_utc(service.payout_deadline_at):
        raise HTTPException(status_code=409, detail="The claim window for this service has closed.")

    # The claim holds the payout: the service leaves completed until the claim is resolved outside this scope.
    session.add(
        Reclamo(
            id=uuid4(),
            service_id=service.id,
            user_id=account_id,
            reason=payload.reason,
            status=CLAIM_OPEN,
            created_at=now,
        )
    )
    service.status = "disputed"
    session.commit()
    return _customer_service_detail(session, account_id, service_id)


@router.post("/services/{service_id}/consent", response_model=ServiceDetail)
def give_customer_service_consent(
    service_id: UUID,
    current_user: CurrentUser,
    session: Database,
) -> ServiceDetail:
    account_id = _customer_account_id(session, current_user)
    service = _lock_customer_service(session, account_id, service_id)
    if _has_open_claim(session, service.id):
        raise HTTPException(status_code=409, detail="A service with an open claim cannot receive consent.")
    if service.status != "completed":
        raise HTTPException(status_code=409, detail="Only completed services can receive consent.")
    if _payout_released(session, service.id):
        raise HTTPException(status_code=409, detail="The payout for this service has already been released.")
    if service.customer_consent_at is not None:
        raise HTTPException(status_code=409, detail="Consent was already given for this service.")
    # Consent makes the payout due immediately; the release job picks it up on its next run.
    service.customer_consent_at = utc_now()
    session.commit()
    return _customer_service_detail(session, account_id, service_id)
