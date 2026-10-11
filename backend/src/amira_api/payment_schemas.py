"""Request and response models for payments."""

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from amira_api.public_schemas import PublicResponse
from amira_api.quotation_schemas import QuotationStatus

PaymentStatus = Literal["pending", "approved", "rejected"]


class PaymentCheckout(PublicResponse):
    payment_id: UUID
    checkout_url: str


class PaymentConfirmationRequest(PublicResponse):
    model_config = ConfigDict(str_strip_whitespace=True)

    payment_id: UUID
    provider_payment_id: str = Field(min_length=1, max_length=200)
    status: Literal["approved", "rejected"]
    signature: str = Field(min_length=1, max_length=256)


class SimulatedPaymentCompletion(PublicResponse):
    token: str = Field(min_length=1, max_length=256)
    approve: bool


class PaymentResult(PublicResponse):
    payment_id: UUID
    status: PaymentStatus
    quotation_id: UUID
    quotation_status: QuotationStatus
    service_id: UUID | None


class PaymentDetail(PublicResponse):
    payment_id: UUID
    status: PaymentStatus
    quotation_id: UUID
    quotation_status: QuotationStatus
    chat_id: UUID
