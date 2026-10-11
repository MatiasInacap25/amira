"""Explicit response models for marketplace browsing and quote requests."""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class PublicResponse(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class PublicProviderService(PublicResponse):
    service_type_id: UUID
    name: str


class PublicServiceItem(PublicResponse):
    profile_id: UUID
    provider_name: str
    category: str
    description: str | None
    location: str | None
    commune_code: str | None = None
    commune_name: str | None = None
    region_name: str | None = None
    logo_url: str | None = None
    services: list[PublicProviderService]


class PublicServiceType(PublicResponse):
    id: UUID
    slug: str
    name: str


class PublicServiceTypePage(PublicResponse):
    items: list[PublicServiceType]


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
    origin_commune_code: str | None = None
    destination_commune_code: str | None = None
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
    is_owner: bool


class PublicProviderVehicle(PublicResponse):
    brand: str
    model: str
    year: int | None
    maximum_weight: Decimal | None


class PublicProviderRating(PublicResponse):
    rating: int
    comment: str | None
    created_at: datetime


class PublicProviderRatingSummary(PublicResponse):
    average_rating: float | None
    rating_count: int
    recent: list[PublicProviderRating]


class PublicProviderProfile(PublicResponse):
    profile_id: UUID
    provider_name: str
    kind: Literal["company", "independent_driver"]
    description: str | None
    location: str | None
    commune_code: str | None = None
    commune_name: str | None = None
    region_name: str | None = None
    owner_name: str
    drivers: list[PublicProviderDriver]
    services: list[PublicProviderService]
    vehicles: list[PublicProviderVehicle]
    ratings: PublicProviderRatingSummary


class ServiceRequestCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    profile_id: UUID
    service_type_id: UUID
    origin_commune_code: str = Field(pattern=r"^\d{5}$")
    destination_commune_code: str = Field(pattern=r"^\d{5}$")
    origin: str | None = Field(default=None, max_length=300)
    destination: str | None = Field(default=None, max_length=300)
    requested_at: datetime | None = None
    estimated_weight: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    estimated_volume: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    description: str | None = Field(default=None, max_length=4000)
    cargo_measurements: str | None = Field(default=None, max_length=2000)

    @field_validator("origin", "destination")
    @classmethod
    def blank_street_address_is_absent(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("requested_at")
    @classmethod
    def requested_at_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise PydanticCustomError("requested_at_timezone", "La fecha solicitada debe incluir zona horaria.")
        if value is not None and value < datetime.now(UTC):
            raise PydanticCustomError("requested_at_past", "La fecha solicitada no puede estar en el pasado.")
        return value


class ServiceRequestCreated(PublicResponse):
    request_id: UUID
    status: str


class ProviderRequestItem(PublicResponse):
    request_id: UUID
    status: str
    origin: str
    destination: str
    requested_at: datetime | None
    created_at: datetime
    estimated_weight: Decimal | None
    estimated_volume: Decimal | None
    description: str | None
    cargo_measurements: str | None
    service_name: str
    chat_id: UUID | None


class ProviderRequestPage(PublicResponse):
    items: list[ProviderRequestItem]
    total: int
    limit: int
    offset: int


class ProviderRequestDecision(PublicResponse):
    request_id: UUID
    status: str
    chat_id: UUID | None


class ProviderServiceDriverAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=_to_camel, populate_by_name=True)
    driver_id: UUID


class ProviderServiceDriverAssignment(PublicResponse):
    service_id: UUID
    driver_id: UUID
