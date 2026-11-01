"""Provider profile settings: read, edit, and publish or unpublish the caller's own provider profile.

Only the owner of a provider ``Perfil`` may use these routes (see ``invitation_routes._owned_provider``). Every other
account gets 403. Publishing makes the profile visible in public provider search; unpublishing hides it again.
"""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.invitation_routes import _owned_provider
from amira_api.models import Commune, Perfil, ServicioDisponible, TipoServicio
from amira_api.provider_profile_schemas import ProviderProfileUpdate, ProviderProfileView

router = APIRouter(prefix="/api/provider/profile", tags=["provider-profile"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]


def _missing_items(profile: Perfil, service_type_ids: list[UUID]) -> list[str]:
    missing: list[str] = []
    if not (profile.description or "").strip():
        missing.append("description")
    if profile.commune_code is None:
        missing.append("commune")
    if not service_type_ids:
        missing.append("service_types")
    return missing


def _profile_view(session: Session, profile: Perfil) -> ProviderProfileView:
    service_type_ids = list(session.execute(
        select(ServicioDisponible.service_type_id)
        .where(ServicioDisponible.profile_id == profile.id)
        .order_by(ServicioDisponible.service_type_id)
    ).scalars())
    return ProviderProfileView(
        name=profile.name,
        kind=profile.kind,
        description=profile.description,
        commune_code=profile.commune_code,
        service_type_ids=service_type_ids,
        published=profile.public_activated_at is not None,
        missing=_missing_items(profile, service_type_ids),
    )


@router.get("", response_model=ProviderProfileView)
def get_provider_profile(current_user: CurrentUser, session: Database) -> ProviderProfileView:
    _, profile, _, _ = _owned_provider(session, current_user.id)
    return _profile_view(session, profile)


@router.put("", response_model=ProviderProfileView)
def update_provider_profile(
    payload: ProviderProfileUpdate,
    current_user: CurrentUser,
    session: Database,
) -> ProviderProfileView:
    _, profile, _, _ = _owned_provider(session, current_user.id, lock=True)

    if payload.name is not None and profile.kind != "company":
        raise HTTPException(status_code=422, detail="Only company profiles have a name.")
    # name is optional in the schema because independent drivers never send it; a company must send a real name,
    # so both an omitted key and an explicit null are rejected before anything is written.
    if profile.kind == "company" and payload.name is None:
        raise HTTPException(status_code=422, detail="Company profiles require a name.")
    if payload.commune_code is not None and session.get(Commune, payload.commune_code) is None:
        raise HTTPException(status_code=422, detail="Unknown commune.")

    service_type_ids = list(dict.fromkeys(payload.service_type_ids))
    if service_type_ids:
        known = set(session.execute(
            select(TipoServicio.id).where(TipoServicio.id.in_(service_type_ids))
        ).scalars())
        if known != set(service_type_ids):
            raise HTTPException(status_code=422, detail="Unknown service type.")

    if payload.name is not None:
        profile.name = payload.name
    profile.description = payload.description
    profile.commune_code = payload.commune_code
    session.execute(delete(ServicioDisponible).where(ServicioDisponible.profile_id == profile.id))
    session.add_all(
        ServicioDisponible(id=uuid4(), profile_id=profile.id, service_type_id=service_type_id)
        for service_type_id in service_type_ids
    )
    if profile.public_activated_at is not None and _missing_items(profile, service_type_ids):
        profile.public_activated_at = None
    session.commit()
    return _profile_view(session, profile)


@router.post("/publish", response_model=ProviderProfileView)
def publish_provider_profile(current_user: CurrentUser, session: Database) -> ProviderProfileView:
    _, profile, _, _ = _owned_provider(session, current_user.id, lock=True)
    service_type_ids = list(session.execute(
        select(ServicioDisponible.service_type_id).where(ServicioDisponible.profile_id == profile.id)
    ).scalars())
    missing = _missing_items(profile, service_type_ids)
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Profile is incomplete.", "missing": missing})

    if profile.public_activated_at is None:
        profile.public_activated_at = utc_now()
    session.commit()
    return _profile_view(session, profile)


@router.post("/unpublish", response_model=ProviderProfileView)
def unpublish_provider_profile(current_user: CurrentUser, session: Database) -> ProviderProfileView:
    _, profile, _, _ = _owned_provider(session, current_user.id, lock=True)
    profile.public_activated_at = None
    session.commit()
    return _profile_view(session, profile)
