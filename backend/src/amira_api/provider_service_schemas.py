"""Response models for contracted-service queries shared by the provider and customer routes.

Responses never carry contact details (phone, email, RUT): the counterpart is named only.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amira_api.public_schemas import PublicResponse, _to_camel

ServiceStatus = Literal["confirmed", "in_progress", "completed", "disputed"]


class ServiceListItem(PublicResponse):
    service_id: UUID
    status: ServiceStatus
    service_type_name: str
    service_at: datetime | None
    amount: int | None
    currency: Literal["CLP"]
    origin_commune: str | None
    destination_commune: str | None
    is_exclusive: bool
    counterpart_name: str
    assignment_count: int


class ServicePage(PublicResponse):
    items: list[ServiceListItem]
    total: int
    limit: int
    offset: int


class ServiceAssignment(PublicResponse):
    driver_id: UUID
    driver_first_name: str
    vehicle_id: UUID
    vehicle_label: str
    plate: str


class ServiceDetail(ServiceListItem):
    chat_id: UUID
    description: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    payout_deadline_at: datetime | None
    viewer_role: Literal["customer", "provider"]
    can_manage: bool
    assignments: list[ServiceAssignment]


class ServiceAssignmentPair(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=_to_camel, populate_by_name=True)

    driver_id: UUID
    vehicle_id: UUID


class ServiceAssignmentsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=_to_camel, populate_by_name=True)

    assignments: list[ServiceAssignmentPair] = Field(min_length=1)
    confirm_same_day_conflicts: bool = False

    @model_validator(mode="after")
    def drivers_and_vehicles_are_unique(self) -> "ServiceAssignmentsUpdate":
        drivers = [pair.driver_id for pair in self.assignments]
        vehicles = [pair.vehicle_id for pair in self.assignments]
        if len(set(drivers)) != len(drivers):
            raise ValueError("Each driver can be assigned only once per service.")
        if len(set(vehicles)) != len(vehicles):
            raise ValueError("Each vehicle can be assigned only once per service.")
        return self


class SameDayConflict(PublicResponse):
    driver_id: UUID
    service_id: UUID
    service_at: datetime | None


class SameDayConflictResponse(PublicResponse):
    detail: str
    conflicts: list[SameDayConflict]
