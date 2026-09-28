"""Explicit response models for unauthenticated marketplace browsing."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class PublicResponse(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class PublicServiceItem(PublicResponse):
    profile_id: UUID
    provider_name: str
    category: str
    description: str | None
    location: str | None
    logo_url: str | None = None


class PublicServicePage(PublicResponse):
    items: list[PublicServiceItem]
    total: int
    limit: int
    offset: int


class PublicRouteStop(PublicResponse):
    stop_number: int
    estimated_at: datetime | None


class PublicSharedRoute(PublicResponse):
    trip_id: UUID
    provider_name: str
    origin: str
    destination: str
    departure_at: datetime | None
    stops: list[PublicRouteStop]


class PublicSharedRoutePage(PublicResponse):
    items: list[PublicSharedRoute]
    total: int
    limit: int
    offset: int
