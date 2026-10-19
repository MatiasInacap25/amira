"""Chat change announcements over PostgreSQL LISTEN/NOTIFY.

Writers call publish_chat_event on the same session as their row change, before the commit. pg_notify is delivered
only when that transaction commits, so a rolled-back write announces nothing. Payloads carry ids and recipient user
ids only, never message content.
"""

import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from amira_api.models import ChatParticipante

CHAT_EVENTS_CHANNEL = "amira_chat_events"
# pg_notify rejects payloads of 8000 bytes or more; the builder stays far below that.
MAX_PAYLOAD_BYTES = 8000


class ChatEventKind(StrEnum):
    MESSAGE_CREATED = "message.created"
    QUOTATION_CHANGED = "quotation.changed"


@dataclass(frozen=True)
class ChatEvent:
    kind: ChatEventKind
    chat_id: UUID
    ref_id: UUID
    recipients: tuple[UUID, ...]

    def to_payload(self) -> str:
        ref_key = "messageId" if self.kind is ChatEventKind.MESSAGE_CREATED else "quotationId"
        payload = json.dumps(
            {
                "kind": self.kind.value,
                "chatId": str(self.chat_id),
                ref_key: str(self.ref_id),
                "recipients": [str(user_id) for user_id in self.recipients],
            },
            separators=(",", ":"),
        )
        if len(payload.encode()) >= MAX_PAYLOAD_BYTES:
            raise ValueError("Chat event payload exceeds the pg_notify size limit.")
        return payload


def publish_chat_event(session: Session, *, chat_id: UUID, kind: ChatEventKind | str, ref_id: UUID) -> None:
    """Announce a chat change to both participants, inside the caller's transaction."""
    event_kind = ChatEventKind(kind)
    recipients = tuple(
        session.execute(
            select(ChatParticipante.user_id)
            .where(ChatParticipante.chat_id == chat_id)
            .order_by(ChatParticipante.user_id)
        ).scalars()
    )
    if not recipients:
        return
    event = ChatEvent(kind=event_kind, chat_id=chat_id, ref_id=ref_id, recipients=recipients)
    session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHAT_EVENTS_CHANNEL, "payload": event.to_payload()},
    )
