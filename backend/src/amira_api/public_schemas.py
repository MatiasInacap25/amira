"""Explicit response models for marketplace browsing and quote requests."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    profile_id: UUID
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


class PublicProviderDriver(PublicResponse):
    first_name: str
    last_name: str


class PublicProviderService(PublicResponse):
    service_type_id: UUID
    name: str


class PublicProviderVehicle(PublicResponse):
    brand: str
    model: str
    year: int | None
    maximum_weight: Decimal | None


class PublicProviderProfile(PublicResponse):
    profile_id: UUID
    provider_name: str
    kind: Literal["company", "independent_driver"]
    description: str | None
    location: str | None
    owner_name: str
    drivers: list[PublicProviderDriver]
    services: list[PublicProviderService]
    vehicles: list[PublicProviderVehicle]


class ServiceRequestCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    profile_id: UUID
    service_type_id: UUID
    origin: str = Field(min_length=1, max_length=300)
    destination: str = Field(min_length=1, max_length=300)
    requested_at: datetime | None = None
    estimated_weight: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    estimated_volume: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    description: str | None = Field(default=None, max_length=4000)
    cargo_measurements: str | None = Field(default=None, max_length=2000)

    @field_validator("requested_at")
    @classmethod
    def requested_at_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("requestedAt must include a timezone.")
        return value


class ServiceRequestCreated(PublicResponse):
    request_id: UUID
    status: str
