"""Chat list and chat message endpoints shared by customers and providers."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import and_, func, literal_column, or_, select, union_all
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.chat_access import caller_account, caller_chats
from amira_api.clock import as_utc, utc_now
from amira_api.chat_schemas import (
    ChatAttachment,
    ChatAttachmentUrl,
    ChatCounterpart,
    ChatHeader,
    ChatLastMessage,
    ChatListItem,
    ChatMessage,
    ChatMessageCreate,
    ChatMessagesPage,
    ChatPage,
    ChatTimelineMessage,
    ChatTimelineQuotation,
    MESSAGE_MAX_LENGTH,
)
from amira_api.contact_filter import CONTACT_KIND_LABELS, find_contact_detail
from amira_api.db import get_db_session
from amira_api.evidence_storage import (
    EvidenceStorage,
    EvidenceStorageError,
    detect_photo_type,
    get_chat_attachment_storage_resolver,
    read_capped,
)
from amira_api.realtime import ChatEventKind, publish_chat_event
from amira_api.models import Chat, Cotizacion, Mensaje
from amira_api.public_routes import MAX_OFFSET, MAX_PAGE_SIZE
from amira_api.quotation_service import quotation_view
from amira_api.settings import Settings, get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chats", tags=["chats"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
ResolveChatStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_chat_attachment_storage_resolver)]
LAST_MESSAGE_PREVIEW_LENGTH = 140
IMAGE_PREVIEW_TEXT = "Foto"
MAX_MESSAGE_PAGE_SIZE = 100
ATTACHMENT_MAX_SIZE_MESSAGE = "The chat photo is larger than the allowed size."
ATTACHMENT_TYPE_MESSAGE = "The chat photo must be a JPEG, PNG or WebP image."
ATTACHMENT_STORAGE_MESSAGE = "The chat photo could not be stored. Try again."
ATTACHMENT_LINK_MESSAGE = "The chat photo link could not be created. Try again."


def _last_message_per_chat():
    """The newest message of every chat, chosen by one window function so ties are deterministic."""
    ranked = select(
        Mensaje.chat_id.label("chat_id"),
        Mensaje.content.label("content"),
        Mensaje.attachment_key.label("attachment_key"),
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
        # An image-only message has empty text, so the list shows a short label instead of a blank line.
        preview = row["last_content"] or (IMAGE_PREVIEW_TEXT if row["last_attachment_key"] is not None else "")
        last_message = ChatLastMessage(
            content=preview[:LAST_MESSAGE_PREVIEW_LENGTH],
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
    account = caller_account(session, current_user)
    if account is None:
        return ChatPage(items=[], total=0, limit=limit, offset=offset)
    caller_id = account.id

    relation = caller_chats(caller_id)
    total = session.execute(select(func.count()).select_from(relation.subquery())).scalar_one()

    last = _last_message_per_chat()
    rows = session.execute(
        relation.add_columns(
            last.c.content.label("last_content"),
            last.c.attachment_key.label("last_attachment_key"),
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


CURSOR_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _encode_cursor(sent_at: datetime, message_id: UUID) -> str:
    """Opaque cursor for the page that starts just before this message. Clients must not parse it."""
    return f"{as_utc(sent_at).strftime(CURSOR_TIME_FORMAT)}|{message_id}"


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        stamp, raw_id = cursor.split("|", 1)
        return as_utc(datetime.strptime(stamp, CURSOR_TIME_FORMAT)), UUID(raw_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["query", "before"], "msg": "Cursor de mensajes no válido.", "type": "value_error"}],
        ) from None


def _timeline_index(chat_id: UUID):
    """Messages and quotations of one chat as (kind, entry_id, entry_at) rows, so one cursor pages both kinds."""
    messages = select(
        literal_column("'message'").label("kind"), Mensaje.id.label("entry_id"), Mensaje.created_at.label("entry_at")
    ).where(Mensaje.chat_id == chat_id)
    quotations = select(
        literal_column("'quotation'").label("kind"), Cotizacion.id.label("entry_id"), Cotizacion.created_at.label("entry_at")
    ).where(Cotizacion.chat_id == chat_id)
    return union_all(messages, quotations).subquery("timeline_index")


def _sender_name(sender_id: UUID, caller_id: UUID, caller_name: str, counterpart_name: str) -> str:
    return caller_name if sender_id == caller_id else counterpart_name


def _attachment_view(message: Mensaje) -> ChatAttachment | None:
    # The storage key never leaves the server; the client reads the photo through the signed URL endpoint.
    if message.attachment_key is None:
        return None
    return ChatAttachment(content_type=message.attachment_content_type, size_bytes=message.attachment_size_bytes)


def _reject_contact_details(content: str) -> None:
    blocked_kind = find_contact_detail(content)
    if blocked_kind is not None:
        # The message text is not echoed back or logged, because it is the content that was blocked.
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "contact_details_blocked",
                    "loc": ["body", "content"],
                    "msg": f"No se permite compartir {CONTACT_KIND_LABELS[blocked_kind]} en el chat.",
                }
            ],
        )


@router.get("/{chat_id}/messages", response_model=ChatMessagesPage)
def list_chat_messages(
    chat_id: UUID,
    current_user: CurrentUser,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=MAX_MESSAGE_PAGE_SIZE)] = 50,
    before: Annotated[str | None, Query(max_length=200)] = None,
) -> ChatMessagesPage:
    account = caller_account(session, current_user)
    # A missing chat and a chat the caller does not participate in get the same response, so existence is not leaked.
    if account is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    caller_id = account.id
    caller_name = f"{account.first_name} {account.last_name}"
    row = session.execute(caller_chats(caller_id).where(Chat.id == chat_id)).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Chat not found.")

    index = _timeline_index(chat_id)
    statement = select(index.c.kind, index.c.entry_id, index.c.entry_at)
    if before is not None:
        before_at, before_id = _decode_cursor(before)
        # Ties on the timestamp are broken by id, so entries sharing a timestamp are never skipped or repeated.
        statement = statement.where(
            or_(index.c.entry_at < before_at, and_(index.c.entry_at == before_at, index.c.entry_id < before_id))
        )
    # One extra row tells the client whether older entries exist without a second query.
    newest_first = session.execute(
        statement.order_by(index.c.entry_at.desc(), index.c.entry_id.desc()).limit(limit + 1)
    ).all()
    has_more = len(newest_first) > limit
    page = list(reversed(newest_first[:limit]))
    next_before = _encode_cursor(page[0].entry_at, page[0].entry_id) if has_more else None

    message_ids = [entry.entry_id for entry in page if entry.kind == "message"]
    quotation_ids = [entry.entry_id for entry in page if entry.kind == "quotation"]
    messages = (
        {message.id: message for message in session.execute(select(Mensaje).where(Mensaje.id.in_(message_ids))).scalars()}
        if message_ids
        else {}
    )
    quotations = (
        {quotation.id: quotation for quotation in session.execute(select(Cotizacion).where(Cotizacion.id.in_(quotation_ids))).scalars()}
        if quotation_ids
        else {}
    )

    now = utc_now()
    counterpart_name = _counterpart(row, caller_id).name
    timeline: list[ChatTimelineMessage | ChatTimelineQuotation] = []
    for entry in page:
        if entry.kind == "message":
            message = messages[entry.entry_id]
            timeline.append(
                ChatTimelineMessage(
                    message_id=message.id,
                    content=message.content,
                    sent_at=message.created_at,
                    from_me=message.user_id == caller_id,
                    sender_name=_sender_name(message.user_id, caller_id, caller_name, counterpart_name),
                    attachment=_attachment_view(message),
                )
            )
        else:
            timeline.append(ChatTimelineQuotation(quotation=quotation_view(quotations[entry.entry_id], now)))

    viewer_role = "customer" if row["customer_id"] == caller_id else "provider"
    return ChatMessagesPage(
        **_header(row, caller_id).model_dump(),
        viewer_role=viewer_role,
        timeline=timeline,
        next_before=next_before,
    )


@router.post("/{chat_id}/messages", response_model=ChatMessage, status_code=201)
def send_chat_message(
    chat_id: UUID,
    payload: ChatMessageCreate,
    current_user: CurrentUser,
    session: Database,
) -> ChatMessage:
    account = caller_account(session, current_user)
    if account is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    caller_id = account.id
    if session.execute(caller_chats(caller_id).where(Chat.id == chat_id)).one_or_none() is None:
        raise HTTPException(status_code=404, detail="Chat not found.")

    _reject_contact_details(payload.content)

    message = Mensaje(id=uuid4(), chat_id=chat_id, user_id=caller_id, content=payload.content)
    session.add(message)
    publish_chat_event(session, chat_id=chat_id, kind=ChatEventKind.MESSAGE_CREATED, ref_id=message.id)
    session.commit()
    session.refresh(message)
    return ChatMessage(
        message_id=message.id,
        content=message.content,
        sent_at=message.created_at,
        from_me=True,
        sender_name=f"{account.first_name} {account.last_name}",
    )


def _discard_attachment(storage: EvidenceStorage, key: str) -> None:
    """Best effort: a failed delete leaves a stored but unreferenced photo, so it is logged and never raised."""
    try:
        storage.delete(key)
    except EvidenceStorageError:
        logger.warning("Could not delete the unreferenced chat photo %s.", key, exc_info=True)


@router.post("/{chat_id}/messages/attachments", response_model=ChatTimelineMessage, status_code=201)
def send_chat_attachment(
    chat_id: UUID,
    current_user: CurrentUser,
    session: Database,
    resolve_storage: ResolveChatStorage,
    settings: AppSettings,
    photo: Annotated[UploadFile, File()],
    content: Annotated[str, Form(max_length=MESSAGE_MAX_LENGTH)] = "",
) -> ChatTimelineMessage:
    account = caller_account(session, current_user)
    if account is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    caller_id = account.id
    if session.execute(caller_chats(caller_id).where(Chat.id == chat_id)).one_or_none() is None:
        raise HTTPException(status_code=404, detail="Chat not found.")

    # Storage is resolved first, so an unconfigured deployment answers 503 before any upload is attempted.
    storage = resolve_storage()
    text = content.strip()
    if text:
        _reject_contact_details(text)

    data = read_capped(photo, settings.chat_attachment_max_bytes)
    if data is None:
        raise HTTPException(status_code=413, detail=ATTACHMENT_MAX_SIZE_MESSAGE)
    photo_type = detect_photo_type(data[:12])
    if photo_type is None:
        raise HTTPException(status_code=415, detail=ATTACHMENT_TYPE_MESSAGE)

    # The upload happens before the row is written. If the row cannot be written, the uploaded object is removed.
    message_id = uuid4()
    key = f"chats/{chat_id}/{message_id}.{photo_type.extension}"
    try:
        storage.upload(key, data, photo_type.content_type)
    except EvidenceStorageError as error:
        raise HTTPException(status_code=502, detail=ATTACHMENT_STORAGE_MESSAGE) from error

    try:
        message = Mensaje(
            id=message_id,
            chat_id=chat_id,
            user_id=caller_id,
            content=text,
            attachment_key=key,
            attachment_content_type=photo_type.content_type,
            attachment_size_bytes=len(data),
        )
        session.add(message)
        publish_chat_event(session, chat_id=chat_id, kind=ChatEventKind.MESSAGE_CREATED, ref_id=message.id)
        session.commit()
    except Exception:
        session.rollback()
        _discard_attachment(storage, key)
        raise
    session.refresh(message)
    return ChatTimelineMessage(
        message_id=message.id,
        content=message.content,
        sent_at=message.created_at,
        from_me=True,
        sender_name=f"{account.first_name} {account.last_name}",
        attachment=_attachment_view(message),
    )


@router.get("/{chat_id}/messages/{message_id}/attachment", response_model=ChatAttachmentUrl)
def get_chat_attachment_url(
    chat_id: UUID,
    message_id: UUID,
    current_user: CurrentUser,
    session: Database,
    resolve_storage: ResolveChatStorage,
    settings: AppSettings,
) -> ChatAttachmentUrl:
    account = caller_account(session, current_user)
    if account is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if session.execute(caller_chats(account.id).where(Chat.id == chat_id)).one_or_none() is None:
        raise HTTPException(status_code=404, detail="Chat not found.")

    key = session.execute(
        select(Mensaje.attachment_key).where(Mensaje.id == message_id, Mensaje.chat_id == chat_id)
    ).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    storage = resolve_storage()
    ttl_seconds = settings.chat_attachment_url_ttl_seconds
    try:
        url = storage.create_signed_url(key, ttl_seconds)
    except EvidenceStorageError as error:
        raise HTTPException(status_code=502, detail=ATTACHMENT_LINK_MESSAGE) from error
    return ChatAttachmentUrl(url=url, expires_at=utc_now() + timedelta(seconds=ttl_seconds))
