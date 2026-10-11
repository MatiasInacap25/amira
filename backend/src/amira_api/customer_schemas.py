"""Response and request models for the authenticated customer service history."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from amira_api.provider_service_schemas import ServiceStatus
from amira_api.public_schemas import PublicResponse, _to_camel


class CustomerServiceRating(PublicResponse):
    rating: int
    comment: str | None
    created_at: datetime


class CustomerServiceItem(PublicResponse):
    service_id: UUID
    status: ServiceStatus
    provider_profile_id: UUID
    provider_name: str
    service_type_name: str
    completed_at: datetime | None
    rating: CustomerServiceRating | None


class CustomerServicePage(PublicResponse):
    items: list[CustomerServiceItem]
    total: int
    limit: int
    offset: int


class CustomerRatingCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def blank_comment_is_absent(cls, value: str | None) -> str | None:
        return value or None
