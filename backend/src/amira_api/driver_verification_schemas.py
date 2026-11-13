from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from amira_api.driver_certificates import CertificateType


class CertificateSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: CertificateType
    # Verifik accepts folios of 10 to 15 characters; both values are printed on the Registro Civil certificate.
    folio: str = Field(pattern=r"^[0-9A-Za-z]{10,15}$")
    verification_code: str = Field(min_length=1, max_length=64, pattern=r"^[0-9A-Za-z_-]+$")


class CertificateStatusItem(BaseModel):
    type: CertificateType
    status: Literal["missing", "verified", "in_review", "rejected"]
    reason: str | None
    submitted_at: datetime | None
    verified_at: datetime | None


class DriverVerificationView(BaseModel):
    verified: bool
    certificates: list[CertificateStatusItem]
