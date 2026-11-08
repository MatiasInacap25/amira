from datetime import datetime
from uuid import UUID

from amira_api.public_schemas import PublicResponse


class VehicleCreated(PublicResponse):
    vehicle_id: UUID


class VehicleItem(PublicResponse):
    vehicle_id: UUID
    plate: str
    brand: str
    model: str
    year: int | None
    maximum_weight: float | None
    url: str
    expires_at: datetime


class VehiclePage(PublicResponse):
    items: list[VehicleItem]
