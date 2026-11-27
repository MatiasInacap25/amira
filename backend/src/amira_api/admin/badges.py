from sqlalchemy import func, select
from sqlalchemy.orm import Session

from amira_api.clock import utc_now
from amira_api.models import CuentaDesembolso, Reclamo, VerificacionIdentidad
from amira_api.payout_service import _due_service_ids
from amira_api.service_views import CLAIM_OPEN


def pending_badges(session: Session) -> dict[str, int]:
    def count(column, status: str) -> int:
        return session.scalar(select(func.count()).where(column == status)) or 0

    return {
        "documentos": count(VerificacionIdentidad.status, "in_review"),
        "cuentas-bancarias": count(CuentaDesembolso.registration_status, "pending"),
        "reclamos": count(Reclamo.status, CLAIM_OPEN),
        "desembolsos": len(_due_service_ids(session, utc_now())),
    }
