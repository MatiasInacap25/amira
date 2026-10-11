"""Automatic payout release for completed services.

A service is due when it is completed, has no open claim and no payout yet, and either the customer consented or the
claim window closed. Each due service is released in its own transaction: the row is locked with SKIP LOCKED so a
concurrent run skips it, and the due conditions are checked again under that lock. A release needs an approved payment
for the service and an enabled payout account on the provider profile.

Releasing is idempotent: one payout row per service, and the provider receives a stable idempotency key per service,
so a retry after a lost commit returns the same provider payout instead of paying twice.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from amira_api.models import CuentaDesembolso, Desembolso, Pago, Servicio
from amira_api.payment_service import APPROVED
from amira_api.payout_provider import PayoutProvider, PayoutRequest
from amira_api.service_views import open_claim_exists

logger = logging.getLogger(__name__)

CURRENCY = "CLP"
COMPLETED = "completed"
RELEASED = "released"


@dataclass
class PayoutSummary:
    due: int = 0
    released: int = 0
    missing_account: int = 0
    missing_payment: int = 0
    skipped: int = 0
    failed: int = 0


def _payout_exists():
    return exists().where(Desembolso.service_id == Servicio.id)


def _due_conditions(now: datetime) -> tuple:
    return (
        Servicio.status == COMPLETED,
        ~open_claim_exists(),
        ~_payout_exists(),
        or_(Servicio.customer_consent_at.is_not(None), Servicio.payout_deadline_at <= now),
    )


def _due_service_ids(session: Session, now: datetime) -> list[UUID]:
    return list(
        session.execute(
            select(Servicio.id).where(*_due_conditions(now)).order_by(Servicio.completed_at, Servicio.id)
        ).scalars()
    )


def _release_one(session: Session, provider: PayoutProvider, service_id: UUID, now: datetime) -> str:
    """Release one service inside the caller's transaction. Returns the outcome name for the summary."""
    service = session.execute(
        select(Servicio)
        .where(Servicio.id == service_id, *_due_conditions(now))
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if service is None:
        return "skipped"

    account = session.execute(
        select(CuentaDesembolso)
        .where(CuentaDesembolso.profile_id == service.profile_id, CuentaDesembolso.payouts_enabled.is_(True))
        .order_by(CuentaDesembolso.created_at, CuentaDesembolso.id)
        .limit(1)
    ).scalar_one_or_none()
    if account is None:
        return "missing_account"

    payment = session.execute(
        select(Pago)
        .where(Pago.quotation_id == service.accepted_quotation_id, Pago.status == APPROVED)
        .order_by(Pago.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if payment is None:
        return "missing_payment"

    idempotency_key = f"service:{service.id}:payout"
    result = provider.create_payout(
        PayoutRequest(
            idempotency_key=idempotency_key,
            amount=payment.amount,
            currency=CURRENCY,
            destination_account_id=account.provider_account_id,
        )
    )
    session.add(
        Desembolso(
            id=uuid4(),
            payment_id=payment.id,
            service_id=service.id,
            beneficiary_profile_id=service.profile_id,
            payout_account_id=account.id,
            provider=provider.name,
            provider_payout_id=result.provider_payout_id,
            idempotency_key=idempotency_key,
            net_amount=payment.amount,
            currency=CURRENCY,
            status=RELEASED,
            requested_at=now,
            confirmed_at=now,
        )
    )
    return RELEASED


def release_due_payouts(session: Session, now: datetime, provider: PayoutProvider) -> PayoutSummary:
    """Release every due service. A failing service is rolled back and counted; the others still run."""
    summary = PayoutSummary()
    service_ids = _due_service_ids(session, now)
    summary.due = len(service_ids)
    for service_id in service_ids:
        try:
            outcome = _release_one(session, provider, service_id, now)
            session.commit()
        except Exception:
            session.rollback()
            summary.failed += 1
            logger.exception("Payout release failed for service %s; it stays due for the next run.", service_id)
            continue

        if outcome == RELEASED:
            summary.released += 1
        elif outcome == "missing_account":
            summary.missing_account += 1
        elif outcome == "missing_payment":
            summary.missing_payment += 1
        else:
            summary.skipped += 1
    return summary
