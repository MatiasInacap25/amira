"""Quotation rules that do not depend on HTTP.

Expiry is not stored: a pending quotation whose validity has passed reads as "expired". Routes call these
helpers after the chat access check and inside the transaction that changes state.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.clock import as_utc
from amira_api.models import Chat, Cotizacion, Servicio
from amira_api.quotation_schemas import Quotation, QuotationStatus

PENDING = "pending"
PAID = "paid"


def effective_status(quotation: Cotizacion, now: datetime) -> QuotationStatus:
    if quotation.status == PENDING and quotation.expires_at is not None and as_utc(quotation.expires_at) <= now:
        return "expired"
    return quotation.status


def quotation_view(quotation: Cotizacion, now: datetime) -> Quotation:
    return Quotation(
        quotation_id=quotation.id,
        status=effective_status(quotation, now),
        amount=int(quotation.amount),
        currency="CLP",
        service_at=quotation.service_at,
        description=quotation.description,
        expires_at=quotation.expires_at,
        created_at=quotation.created_at,
        paid_at=quotation.accepted_at,
    )


def chat_is_settled(session: Session, chat_id: UUID) -> bool:
    """A chat is settled once one quotation is paid or its request has a confirmed service.

    A settled chat takes no new quotations and no new payments.
    """
    paid = session.execute(
        select(Cotizacion.id).where(Cotizacion.chat_id == chat_id, Cotizacion.status == PAID).limit(1)
    ).first()
    if paid is not None:
        return True
    form_id = select(Chat.form_id).where(Chat.id == chat_id).scalar_subquery()
    return session.execute(select(Servicio.id).where(Servicio.form_id == form_id).limit(1)).first() is not None
