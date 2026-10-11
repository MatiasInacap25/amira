"""Response models for contracted-service queries shared by the provider and customer routes.

Responses never carry contact details (phone, email, RUT): the counterpart is named only.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from amira_api.public_schemas import PublicResponse

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
