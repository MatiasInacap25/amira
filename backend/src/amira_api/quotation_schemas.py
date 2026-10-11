"""Request and response models for quotations sent by providers inside a chat."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field

from amira_api.public_schemas import PublicResponse

QuotationStatus = Literal["pending", "paid", "rejected", "expired", "superseded"]
DEFAULT_VALIDITY_HOURS = 48
MAX_VALIDITY_HOURS = 168
DESCRIPTION_MAX_LENGTH = 1000


class QuotationCreate(PublicResponse):
    model_config = ConfigDict(str_strip_whitespace=True)

    amount: int = Field(gt=0, description="Amount in CLP, a whole number.")
    service_at: AwareDatetime
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
    validity_hours: int = Field(default=DEFAULT_VALIDITY_HOURS, ge=1, le=MAX_VALIDITY_HOURS)


class Quotation(PublicResponse):
    quotation_id: UUID
    status: QuotationStatus
    amount: int
    currency: Literal["CLP"]
    service_at: datetime | None
    description: str | None
    expires_at: datetime | None
    created_at: datetime
    paid_at: datetime | None
