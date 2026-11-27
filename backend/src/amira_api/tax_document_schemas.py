"""Response model for simulated tax documents. Every document is marked simulated; nothing here is a tax validity claim."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from amira_api.public_schemas import PublicResponse

TaxDocumentType = Literal["boleta", "factura_comision"]


class TaxDocumentView(PublicResponse):
    id: UUID
    type: TaxDocumentType
    folio: int
    issued_at: datetime
    issuer_name: str
    issuer_tax_id: str | None
    recipient_name: str
    recipient_tax_id: str | None
    net: int
    iva: int
    total: int
    currency: Literal["CLP"]
    simulated: Literal[True]
    service_id: UUID
