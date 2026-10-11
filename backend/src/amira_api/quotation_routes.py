"""Quotation routes: provider quotations inside a chat, and customer rejection."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.chat_access import caller_account, caller_chats
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.models import Chat, Cotizacion, Pago
from amira_api.quotation_schemas import Quotation, QuotationCreate
from amira_api.quotation_service import PENDING, chat_is_settled, effective_status, quotation_view

router = APIRouter(prefix="/api", tags=["quotations"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
CHAT_SETTLED_DETAIL = "Este chat ya tiene una cotización pagada."


@router.post("/chats/{chat_id}/quotations", response_model=Quotation, status_code=201)
def create_quotation(
    chat_id: UUID,
    payload: QuotationCreate,
    current_user: CurrentUser,
    session: Database,
) -> Quotation:
    account = caller_account(session, current_user)
    if account is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    caller_id = account.id
    row = session.execute(caller_chats(caller_id).where(Chat.id == chat_id)).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if row["customer_id"] == caller_id:
        raise HTTPException(status_code=403, detail="Solo el prestador puede enviar cotizaciones.")

    # Locking the chat serializes concurrent quotations, so exactly one pending quotation survives.
    session.execute(select(Chat.id).where(Chat.id == chat_id).with_for_update()).one()
    if chat_is_settled(session, chat_id):
        raise HTTPException(status_code=409, detail=CHAT_SETTLED_DETAIL)

    now = utc_now()
    session.execute(
        update(Cotizacion)
        .where(Cotizacion.chat_id == chat_id, Cotizacion.status == PENDING)
        .values(status="superseded")
    )
    quotation = Cotizacion(
        id=uuid4(),
        chat_id=chat_id,
        status=PENDING,
        amount=payload.amount,
        currency="CLP",
        origin=row["origin_commune_name"] or row["origin_text"] or "",
        destination=row["destination_commune_name"] or row["destination_text"] or "",
        service_type_id=row["service_type_id"],
        service_at=payload.service_at,
        description=payload.description,
        created_at=now,
        expires_at=now + timedelta(hours=payload.validity_hours),
        is_exclusive=False,
    )
    session.add(quotation)
    session.commit()
    session.refresh(quotation)
    return quotation_view(quotation, now)


@router.post("/quotations/{quotation_id}/reject", response_model=Quotation)
def reject_quotation(
    quotation_id: UUID,
    current_user: CurrentUser,
    session: Database,
) -> Quotation:
    account = caller_account(session, current_user)
    if account is None:
        raise HTTPException(status_code=404, detail="Quotation not found.")
    caller_id = account.id
    quotation = session.execute(
        select(Cotizacion).where(Cotizacion.id == quotation_id).with_for_update()
    ).scalar_one_or_none()
    if quotation is None:
        raise HTTPException(status_code=404, detail="Quotation not found.")
    row = session.execute(caller_chats(caller_id).where(Chat.id == quotation.chat_id)).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Quotation not found.")
    if row["customer_id"] != caller_id:
        raise HTTPException(status_code=403, detail="Solo el cliente puede rechazar una cotización.")

    now = utc_now()
    if effective_status(quotation, now) != PENDING:
        raise HTTPException(status_code=409, detail="La cotización ya no está pendiente.")
    payment_in_progress = session.execute(
        select(Pago.id).where(Pago.quotation_id == quotation.id, Pago.status == "pending").limit(1)
    ).first()
    if payment_in_progress is not None:
        raise HTTPException(status_code=409, detail="Hay un pago en curso para esta cotización.")
    quotation.status = "rejected"
    session.commit()
    session.refresh(quotation)
    return quotation_view(quotation, now)
