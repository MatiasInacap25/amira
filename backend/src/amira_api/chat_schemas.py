"""Response models for the customer and provider chat list and chat message views."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from amira_api.public_schemas import PublicResponse


class ChatCounterpart(PublicResponse):
    name: str
    kind: Literal["customer", "company", "independent_driver"]
    provider_profile_id: UUID | None


class ChatHeader(PublicResponse):
    chat_id: UUID
    request_id: UUID
    created_at: datetime
    service_name: str
    origin_commune_name: str | None
    destination_commune_name: str | None
    counterpart: ChatCounterpart


class ChatLastMessage(PublicResponse):
    content: str
    sent_at: datetime
    from_me: bool


class ChatListItem(ChatHeader):
    last_message: ChatLastMessage | None


class ChatPage(PublicResponse):
    items: list[ChatListItem]
    total: int
    limit: int
    offset: int


class ChatMessage(PublicResponse):
    message_id: UUID
    content: str
    sent_at: datetime
    from_me: bool
    sender_name: str


class ChatMessagesPage(ChatHeader):
    messages: list[ChatMessage]
    has_more: bool
