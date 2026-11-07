from datetime import datetime
from uuid import UUID

from amira_api.public_schemas import PublicResponse


class RequestImageCreated(PublicResponse):
    image_id: UUID


class RequestImageUrl(PublicResponse):
    image_id: UUID
    url: str
    expires_at: datetime


class RequestImagePage(PublicResponse):
    items: list[RequestImageUrl]
