from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.models import Perfil, Vehiculo


def require_unsuspended_provider(session: Session, profile_id: UUID) -> None:
    suspended = session.scalar(select(Perfil.suspended_at).where(Perfil.id == profile_id).with_for_update())
    if suspended is not None:
        raise HTTPException(409, "El perfil está suspendido.")


def require_enabled_vehicles(session: Session, vehicle_ids: list[UUID]) -> None:
    rows = session.execute(select(Vehiculo.id, Vehiculo.disabled_at).where(
        Vehiculo.id.in_(vehicle_ids),
    ).order_by(Vehiculo.id).with_for_update())
    if any(disabled is not None for _, disabled in rows):
        raise HTTPException(409, "El vehículo está deshabilitado.")
