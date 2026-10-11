"""Authenticated customer service history and one-time service ratings."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.customer_schemas import (
    CustomerRatingCreate,
    CustomerServiceItem,
    CustomerServicePage,
    CustomerServiceRating,
)
from amira_api.db import get_db_session
from amira_api.models import (
    FormularioServicio,
    Perfil,
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


@router.get("/services", response_model=CustomerServicePage)
def list_customer_services(
    current_user: CurrentUser,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> CustomerServicePage:
    account_id = _customer_account_id(session, current_user)
    total = session.execute(
        select(func.count()).select_from(Servicio).where(Servicio.customer_id == account_id)
    ).scalar_one()
    rows = session.execute(
        select(
            Servicio.id.label("service_id"),
            Perfil.id.label("provider_profile_id"),
            case(
                (Perfil.kind == "independent_driver", Usuario.first_name + " " + Usuario.last_name),
                else_=Perfil.name,
            ).label("provider_name"),
            TipoServicio.name.label("service_type_name"),
            Servicio.completed_at.label("completed_at"),
            Valoracion.rating.label("rating_value"),
            Valoracion.comment.label("rating_comment"),
            Valoracion.created_at.label("rating_created_at"),
        )
        .join(Perfil, Perfil.id == Servicio.profile_id)
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
        .join(FormularioServicio, FormularioServicio.id == Servicio.form_id)
        .join(TipoServicio, TipoServicio.id == FormularioServicio.service_type_id)
        .outerjoin(Valoracion, Valoracion.service_id == Servicio.id)
        .where(Servicio.customer_id == account_id)
        .order_by(Servicio.created_at.desc(), Servicio.id.desc())
        .limit(limit)
        .offset(offset)
    ).mappings().all()

    items = [
        CustomerServiceItem(
            service_id=row["service_id"],
            provider_profile_id=row["provider_profile_id"],
            provider_name=row["provider_name"],
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
