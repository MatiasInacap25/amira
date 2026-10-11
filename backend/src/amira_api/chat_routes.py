"""Chat list and chat message endpoints shared by customers and providers."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, aliased

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.chat_schemas import (
    ChatCounterpart,
    ChatHeader,
    ChatLastMessage,
    ChatListItem,
    ChatMessage,
    ChatMessagesPage,
    ChatPage,
)
from amira_api.db import get_db_session
from amira_api.models import Chat, ChatParticipante, Commune, FormularioServicio, Mensaje, Perfil, TipoServicio, Usuario
from amira_api.public_routes import MAX_OFFSET, MAX_PAGE_SIZE

router = APIRouter(prefix="/api/chats", tags=["chats"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
LAST_MESSAGE_PREVIEW_LENGTH = 140
MAX_MESSAGE_PAGE_SIZE = 100


def _caller_account(session: Session, current_user: AuthenticatedUser):
    """The caller's Usuario id and display name, or None when the auth identity has no account."""
    return session.execute(
        select(Usuario.id, Usuario.first_name, Usuario.last_name).where(Usuario.auth_user_id == current_user.id)
    ).one_or_none()


def _caller_chats(caller_id: UUID) -> Select:
    """Chats the caller participates in, one row per chat.

    Every chat in this relation has an accepted request with a provider profile (the accept route
    always creates both), so the profile join is inner. Counts and items both build from this relation.
    """
    origin_commune = aliased(Commune)
    destination_commune = aliased(Commune)
    customer = aliased(Usuario)
    return (
        select(
            Chat.id.label("chat_id"),
            Chat.created_at.label("created_at"),
            FormularioServicio.id.label("request_id"),
            FormularioServicio.customer_id.label("customer_id"),
            TipoServicio.name.label("service_name"),
            origin_commune.name.label("origin_commune_name"),
            destination_commune.name.label("destination_commune_name"),
            Perfil.id.label("provider_profile_id"),
            Perfil.name.label("provider_name"),
            Perfil.kind.label("provider_kind"),
            customer.first_name.label("customer_first_name"),
            customer.last_name.label("customer_last_name"),
        )
        .select_from(Chat)
        .join(ChatParticipante, ChatParticipante.chat_id == Chat.id)
        .join(FormularioServicio, FormularioServicio.id == Chat.form_id)
        .join(TipoServicio, TipoServicio.id == FormularioServicio.service_type_id)
        .join(Perfil, Perfil.id == FormularioServicio.profile_id)
        .join(customer, customer.id == FormularioServicio.customer_id)
        .outerjoin(origin_commune, origin_commune.code == FormularioServicio.origin_commune_code)
        .outerjoin(destination_commune, destination_commune.code == FormularioServicio.destination_commune_code)
        .where(ChatParticipante.user_id == caller_id)
    )


def _last_message_per_chat():
    """The newest message of every chat, chosen by one window function so ties are deterministic."""
    ranked = select(
        Mensaje.chat_id.label("chat_id"),
        Mensaje.content.label("content"),
        Mensaje.created_at.label("sent_at"),
        Mensaje.user_id.label("sender_id"),
        func.row_number()
        .over(partition_by=Mensaje.chat_id, order_by=(Mensaje.created_at.desc(), Mensaje.id.desc()))
        .label("position"),
    ).subquery()
    return select(ranked).where(ranked.c.position == 1).subquery("last_message")


def _counterpart(row, caller_id: UUID) -> ChatCounterpart:
    if row["customer_id"] == caller_id:
        return ChatCounterpart(
            name=row["provider_name"],
            kind=row["provider_kind"],
            provider_profile_id=row["provider_profile_id"],
        )
    return ChatCounterpart(
        name=f"{row['customer_first_name']} {row['customer_last_name']}",
        kind="customer",
        provider_profile_id=None,
    )


def _list_item(row, caller_id: UUID) -> ChatListItem:
    last_message = None
    if row["last_content"] is not None:
        last_message = ChatLastMessage(
            content=row["last_content"][:LAST_MESSAGE_PREVIEW_LENGTH],
            sent_at=row["last_sent_at"],
            from_me=row["last_sender_id"] == caller_id,
        )
    return ChatListItem(
        chat_id=row["chat_id"],
        request_id=row["request_id"],
        created_at=row["created_at"],
        service_name=row["service_name"],
        origin_commune_name=row["origin_commune_name"],
        destination_commune_name=row["destination_commune_name"],
        counterpart=_counterpart(row, caller_id),
        last_message=last_message,
    )


@router.get("", response_model=ChatPage)
def list_chats(
    current_user: CurrentUser,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> ChatPage:
    account = _caller_account(session, current_user)
    if account is None:
        return ChatPage(items=[], total=0, limit=limit, offset=offset)
    caller_id = account.id

    relation = _caller_chats(caller_id)
    total = session.execute(select(func.count()).select_from(relation.subquery())).scalar_one()

    last = _last_message_per_chat()
    rows = session.execute(
        relation.add_columns(
            last.c.content.label("last_content"),
            last.c.sent_at.label("last_sent_at"),
            last.c.sender_id.label("last_sender_id"),
        )
        .outerjoin(last, last.c.chat_id == Chat.id)
        .order_by(func.coalesce(last.c.sent_at, Chat.created_at).desc(), Chat.id.desc())
        .limit(limit)
        .offset(offset)
    ).mappings().all()
    return ChatPage(
        items=[_list_item(row, caller_id) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _header(row, caller_id: UUID) -> ChatHeader:
    return ChatHeader(
        chat_id=row["chat_id"],
        request_id=row["request_id"],
        created_at=row["created_at"],
        service_name=row["service_name"],
        origin_commune_name=row["origin_commune_name"],
        destination_commune_name=row["destination_commune_name"],
        counterpart=_counterpart(row, caller_id),
    )


@router.get("/{chat_id}/messages", response_model=ChatMessagesPage)
def list_chat_messages(
    chat_id: UUID,
    current_user: CurrentUser,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=MAX_MESSAGE_PAGE_SIZE)] = 50,
    before: datetime | None = None,
) -> ChatMessagesPage:
    account = _caller_account(session, current_user)
    # A missing chat and a chat the caller does not participate in get the same response, so existence is not leaked.
    if account is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    caller_id, caller_first_name, caller_last_name = account.id, account.first_name, account.last_name
    row = session.execute(_caller_chats(caller_id).where(Chat.id == chat_id)).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if before is not None and before.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["query", "before"], "msg": "Indica la fecha con zona horaria.", "type": "value_error"}],
        )

    statement = select(Mensaje.id, Mensaje.content, Mensaje.created_at, Mensaje.user_id).where(Mensaje.chat_id == chat_id)
    if before is not None:
        statement = statement.where(Mensaje.created_at < before)
    # One extra row tells the client whether older messages exist without a second query.
    newest_first = session.execute(
        statement.order_by(Mensaje.created_at.desc(), Mensaje.id.desc()).limit(limit + 1)
    ).mappings().all()
    has_more = len(newest_first) > limit
    page = list(reversed(newest_first[:limit]))
    counterpart_name = _counterpart(row, caller_id).name
    messages = [
        ChatMessage(
            message_id=message["id"],
            content=message["content"],
            sent_at=message["created_at"],
            from_me=message["user_id"] == caller_id,
            sender_name=(
                f"{caller_first_name} {caller_last_name}" if message["user_id"] == caller_id else counterpart_name
            ),
        )
        for message in page
    ]
    return ChatMessagesPage(**_header(row, caller_id).model_dump(), messages=messages, has_more=has_more)
