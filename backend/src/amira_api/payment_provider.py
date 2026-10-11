"""Port for payment providers. The payment domain depends on this protocol; each provider is an adapter.

Adapters are chosen by the composition root (payment_routes), never by the domain. A real provider is added as
another adapter that implements this protocol.
"""

from typing import Protocol
from uuid import UUID


class PaymentProvider(Protocol):
    name: str

    def new_provider_payment_id(self) -> str:
        """A new identifier for a payment attempt, issued by the provider side."""
        ...

    def checkout_url(self, payment_id: UUID, provider_payment_id: str) -> str:
        """Where the customer completes the payment. Must be reproducible for the same payment."""
        ...

    def verify_confirmation(self, payment_id: UUID, provider_payment_id: str, status: str, signature: str) -> bool:
        """True only when the confirmation was signed by this provider for exactly these values."""
        ...
