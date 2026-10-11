"""Port for payout providers. The payout release depends only on this protocol; each provider is an adapter.

Like the payment port, the composition root (release_payouts) chooses the adapter, never the domain. A real provider
is added as another adapter that implements this protocol.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class PayoutProviderError(Exception):
    """The provider did not accept the payout. Nothing is recorded locally; the service stays due for the next run."""


@dataclass(frozen=True)
class PayoutRequest:
    idempotency_key: str
    amount: Decimal
    currency: str
    destination_account_id: str


@dataclass(frozen=True)
class PayoutResult:
    provider_payout_id: str
    status: str


class PayoutProvider(Protocol):
    name: str

    def create_payout(self, request: PayoutRequest) -> PayoutResult:
        """Create the payout once per idempotency key: a repeated key must return the same payout."""
        ...
