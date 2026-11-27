from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.admin.audit import append_audit
from amira_api.clock import utc_now
from amira_api.models import Desembolso, Reclamo, Servicio
from amira_api.service_cancellation import approved_refundable_payment, mark_cancelled, record_simulated_refund
from amira_api.service_views import CLAIM_OPEN
from amira_api.settings import Settings
from amira_api.simulated_payment_provider import SIMULATOR_APP_ENVS


def require_reason(reason: str | None) -> str:
    reason = (reason or "").strip()
    if not 10 <= len(reason) <= 500:
        raise HTTPException(422, "Ingresa un motivo de 10 a 500 caracteres.")
    return reason


def resolve_claim(session: Session, claim_id: UUID, admin_id: UUID, resolution: Literal["customer", "provider"],
                  reason: str | None, settings: Settings):
    reason = require_reason(reason)
    service_id = session.scalar(select(Reclamo.service_id).where(Reclamo.id == claim_id))
    if service_id is None:
        raise HTTPException(404, "No se encontró el reclamo.")
    service = session.scalar(select(Servicio).where(Servicio.id == service_id).with_for_update())
    claim = session.scalar(select(Reclamo).where(Reclamo.id == claim_id).with_for_update())
    if service is None or claim is None or claim.status != CLAIM_OPEN or service.status != "disputed":
        raise HTTPException(409, "El reclamo no está abierto o su servicio no está en disputa.")
    if session.scalar(select(Desembolso.id).where(Desembolso.service_id == service_id).limit(1)) is not None:
        raise HTTPException(409, "El servicio ya tiene un desembolso.")
    if session.scalar(select(Reclamo.id).where(Reclamo.service_id == service_id, Reclamo.status == CLAIM_OPEN,
                                               Reclamo.id != claim_id).limit(1)) is not None:
        raise HTTPException(409, "El servicio tiene más de un reclamo abierto.")
    now = utc_now()
    if resolution == "customer":
        if "app_env" not in settings.model_fields_set or settings.app_env.strip().lower() not in SIMULATOR_APP_ENVS:
            raise HTTPException(503, "El reembolso simulado no está habilitado.")
        payment = approved_refundable_payment(session, service)
        record_simulated_refund(session, service, payment, payment.amount, now, claim_id=claim.id)
        mark_cancelled(service, "admin", payment.amount, Decimal(0), now)
    else:
        service.status = "completed"
    claim.status = "resolved"
    claim.resolution = resolution
    claim.resolved_at = now
    claim.resolved_by = admin_id
    claim.resolution_reason = reason
    append_audit(session, admin_user_id=admin_id, action=f"claim.resolve_{resolution}", entity_type="claim",
                 entity_id=claim.id, reason=reason, before={"status": CLAIM_OPEN, "service_status": "disputed"},
                 after={"status": claim.status, "service_status": service.status, "resolution": resolution, "resolved_at": now})
    session.commit()
