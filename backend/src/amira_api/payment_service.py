"""Payment rules: starting a payment for a quotation and applying a provider confirmation.

This module depends only on the PaymentProvider port. Adapters are chosen by the composition root (payment_routes).
Every state change runs in one transaction under row locks, and a confirmation is idempotent on the provider
payment: a replay with the same status returns the stored result, and a conflicting status is refused.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amira_api.models import Chat, Cotizacion, Pago, Servicio
from amira_api.payment_provider import PaymentProvider
from amira_api.quotation_service import PENDING, chat_is_settled, effective_status

APPROVED = "approved"
REJECTED = "rejected"
IN_PROGRESS = "pending"


class PaymentConflict(Exception):
    """The quotation or payment is not in a state that allows the operation. The message is user-facing Spanish."""


class PaymentNotFound(Exception):
    pass


class ConfirmationRefused(Exception):
    """The provider signature does not match the confirmation."""


def start_payment(session: Session, provider: PaymentProvider, quotation_id: UUID, now: datetime) -> tuple[Pago, str]:
    """Create the payment attempt for a pending quotation, or return the one already in progress."""
    quotation = session.execute(
        select(Cotizacion).where(Cotizacion.id == quotation_id).with_for_update()
    ).scalar_one()
    if effective_status(quotation, now) != PENDING:
        raise PaymentConflict("La cotización ya no está pendiente.")
    if chat_is_settled(session, quotation.chat_id):
        raise PaymentConflict("Este chat ya tiene una cotización pagada.")

    in_progress = session.execute(
        select(Pago)
        .where(Pago.quotation_id == quotation.id, Pago.status == IN_PROGRESS)
        .order_by(Pago.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if in_progress is not None:
        return in_progress, provider.checkout_url(in_progress.id, in_progress.provider_payment_id)

    # Attempts are numbered per quotation, so a new attempt after a rejection gets a new idempotency key.
    attempts = session.execute(
        select(func.count()).select_from(Pago).where(Pago.quotation_id == quotation.id)
    ).scalar_one()
    payment = Pago(
        id=uuid4(),
        quotation_id=quotation.id,
        provider=provider.name,
        provider_payment_id=provider.new_provider_payment_id(),
        idempotency_key=f"quotation:{quotation.id}:attempt:{attempts + 1}",
        amount=quotation.amount,
        currency="CLP",
        status=IN_PROGRESS,
        created_at=now,
        updated_at=now,
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment, provider.checkout_url(payment.id, payment.provider_payment_id)


def confirm_payment(
    session: Session,
    provider: PaymentProvider,
    *,
    payment_id: UUID,
    provider_payment_id: str,
    status: str,
    signature: str,
    now: datetime,
) -> Pago:
    """Apply a signed provider result. An approval marks the quotation paid and creates the service atomically."""
    if not provider.verify_confirmation(payment_id, provider_payment_id, status, signature):
        raise ConfirmationRefused()

    payment = session.execute(select(Pago).where(Pago.id == payment_id).with_for_update()).scalar_one_or_none()
    if payment is None or payment.provider_payment_id != provider_payment_id:
        raise PaymentNotFound()
    if payment.status != IN_PROGRESS:
        if payment.status == status:
            return payment
        raise PaymentConflict("El pago ya tiene un resultado distinto.")

    payment.confirmed_at = now
    payment.updated_at = now
    if status == REJECTED:
        payment.status = REJECTED
        session.commit()
        session.refresh(payment)
        return payment

    quotation = session.execute(
        select(Cotizacion).where(Cotizacion.id == payment.quotation_id).with_for_update()
    ).scalar_one()
    if quotation.status not in (PENDING, "superseded"):
        raise PaymentConflict("La cotización ya no admite este pago.")
    chat = session.get(Chat, quotation.chat_id)
    form = chat.form
    if form.profile_id is None:
        raise PaymentConflict("La solicitud no tiene un prestador asignado.")

    payment.status = APPROVED
    quotation.status = "paid"
    quotation.accepted_at = now
    session.execute(
        update(Cotizacion)
        .where(Cotizacion.chat_id == quotation.chat_id, Cotizacion.status == PENDING, Cotizacion.id != quotation.id)
        .values(status="superseded")
    )
    session.add(
        Servicio(
            id=uuid4(),
            profile_id=form.profile_id,
            customer_id=form.customer_id,
            status="confirmed",
            is_exclusive=form.is_exclusive,
            service_at=quotation.service_at,
            description=quotation.description,
            created_at=now,
            amount=quotation.amount,
            payment_confirmed_at=now,
            form_id=form.id,
            accepted_quotation_id=quotation.id,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        # A concurrent confirmation for the same request won the unique service constraint.
        session.rollback()
        raise PaymentConflict("La solicitud ya tiene un servicio confirmado.") from None
    session.refresh(payment)
    return payment
