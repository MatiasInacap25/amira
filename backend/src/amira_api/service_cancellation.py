"""Atomic, idempotent simulated refunds for pre-start service cancellation.

The caller authenticates ownership and locks the service row, serializing with start and assignment.
Trip membership is intentionally preserved: cancelling a service never cancels its shared route.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.clock import utc_now
from amira_api.models import Pago, Reembolso, Servicio
from amira_api.payment_provider import SIMULATED_PROVIDER_NAME


def cancel_service(session: Session, service_id: UUID, actor: Literal["customer", "provider", "admin"]) -> None:
    service = session.execute(
        select(Servicio).where(Servicio.id == service_id).with_for_update().execution_options(populate_existing=True)
    ).scalar_one()
    if service.status == "cancelled":
        return
    if service.status != "confirmed" or service.starts_at is not None:
        raise HTTPException(status_code=409, detail="Only confirmed services that have not started can be cancelled.")
    payment = approved_refundable_payment(session, service)
    retained = (payment.amount * Decimal("0.10")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if actor == "customer" else Decimal("0")
    refunded = payment.amount - retained
    now = utc_now()
    record_simulated_refund(session, service, payment, refunded, now)
    mark_cancelled(service, actor, refunded, retained, now)
    session.flush()


def approved_refundable_payment(session: Session, service: Servicio) -> Pago:
    payments = session.scalars(
        select(Pago).where(Pago.quotation_id == service.accepted_quotation_id, Pago.status == "approved")
        .order_by(Pago.id).with_for_update()
    ).all()
    if len(payments) != 1:
        raise HTTPException(status_code=409, detail="A single approved payment is required for cancellation.")
    payment = payments[0]
    if payment.provider != SIMULATED_PROVIDER_NAME or payment.currency != "CLP":
        raise HTTPException(status_code=503, detail="Refunds are only available for simulated CLP payments.")
    if session.scalar(select(Reembolso.id).where(Reembolso.payment_id == payment.id).limit(1)) is not None:
        raise HTTPException(status_code=409, detail="This payment already has a refund.")
    return payment


def record_simulated_refund(session: Session, service: Servicio, payment: Pago, amount: Decimal, now, *, claim_id: UUID | None = None) -> None:
    if amount <= 0:
        return
    key = f"service:{service.id}:cancellation" if claim_id is None else f"claim:{claim_id}:refund"
    session.add(Reembolso(
        id=uuid4(), payment_id=payment.id, provider=SIMULATED_PROVIDER_NAME,
        provider_refund_id=f"sim_{key}", idempotency_key=key, claim_id=claim_id,
        amount=amount, currency="CLP", status="approved", confirmed_at=now,
    ))


def mark_cancelled(service: Servicio, actor: Literal["customer", "provider", "admin"], refunded: Decimal, retained: Decimal, now) -> None:
    service.status = "cancelled"
    service.cancelled_at = now
    service.cancelled_by = actor
    service.cancellation_refunded_amount = refunded
    service.cancellation_retained_amount = retained
