"""Authenticated provider queries over contracted services.

A provider viewer is either the owner of a provider ``Perfil`` (company owner or independent driver), who sees
every service of that profile, or a company-employed driver (``Conductor.employer_profile_id`` set) who does not
own a profile, who sees only services they are assigned to through ``Servicio_Asignacion``. Any other account
gets 403. A service the viewer cannot see answers 404, never 403.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.models import Conductor, Perfil, Servicio, ServicioAsignacion, Usuario
from amira_api.provider_service_schemas import ServiceDetail, ServicePage, ServiceStatus
from amira_api.service_views import load_assignments, service_count, service_rows, shape_detail, shape_list_item

router = APIRouter(prefix="/api/provider", tags=["provider-services"])
MAX_PAGE_SIZE = 50
MAX_OFFSET = 5000
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]


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
    account = session.execute(
        select(Usuario.id, Perfil.id, Conductor.id, Conductor.employer_profile_id)
        .outerjoin(Perfil, Perfil.owner_user_id == Usuario.id)
        .outerjoin(Conductor, Conductor.user_id == Usuario.id)
        .where(Usuario.auth_user_id == current_user.id)
    ).one_or_none()
    if account is None:
        raise HTTPException(status_code=403, detail="A provisioned provider account is required.")
    viewer = ProviderViewer(*account)
    if not viewer.is_owner and viewer.employer_profile_id is None:
        raise HTTPException(status_code=403, detail="Only provider accounts can access provider services.")
    return viewer


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
    row = session.execute(service_rows(Servicio.id == service_id, *viewer.visibility())).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Service not found.")
    return shape_detail(
        row, "provider", can_manage=viewer.is_owner, assignments=load_assignments(session, service_id)
    )
