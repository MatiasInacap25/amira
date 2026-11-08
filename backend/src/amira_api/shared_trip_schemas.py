from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from amira_api.public_schemas import PublicResponse, _to_camel


class SharedTripPublishRequest(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True, extra="forbid")

    vehicle_id: UUID
    driver_id: UUID


class SharedTripPublished(PublicResponse):
    trip_id: UUID


class SharedTripClosed(PublicResponse):
    trip_id: UUID
    accepts_requests: bool


class ProviderSharedTripItem(PublicResponse):
    trip_id: UUID
    status: Literal["open", "closed"]
    origin: str
    destination: str
    departure_at: datetime | None
    joined_services: int


class ProviderSharedTripPage(PublicResponse):
    items: list[ProviderSharedTripItem]
    total: int
    limit: int
    offset: int


class ProviderDriverItem(PublicResponse):
    driver_id: UUID
    name: str


class ProviderDriverPage(PublicResponse):
    items: list[ProviderDriverItem]
