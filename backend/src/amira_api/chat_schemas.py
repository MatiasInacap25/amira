"""Response models for the customer and provider chat list and chat message views."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from amira_api.public_schemas import PublicResponse
from amira_api.quotation_schemas import Quotation

MESSAGE_MAX_LENGTH = 2000


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


class ChatMessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)


class ChatMessage(PublicResponse):
    message_id: UUID
    content: str
    sent_at: datetime
    from_me: bool
    sender_name: str


class ChatTimelineMessage(ChatMessage):
    kind: Literal["message"] = "message"


class ChatTimelineQuotation(PublicResponse):
    kind: Literal["quotation"] = "quotation"
    quotation: Quotation


ChatTimelineEntry = Annotated[ChatTimelineMessage | ChatTimelineQuotation, Field(discriminator="kind")]


class ChatMessagesPage(ChatHeader):
    viewer_role: Literal["customer", "provider"]
    timeline: list[ChatTimelineEntry]
    next_before: str | None
