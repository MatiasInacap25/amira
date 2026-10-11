"""Simulated payout adapter for development. It implements the PayoutProvider port and never moves money.

Like the simulated payment adapter, it runs only when APP_ENV is set to an allowlisted development value, so it cannot
release anything in production. Payout ids are derived from the idempotency key, so a repeated request returns the
same payout.
"""

import hashlib

from amira_api.payout_provider import PayoutRequest, PayoutResult
from amira_api.simulated_payment_provider import SIMULATOR_APP_ENVS

SIMULATED_PAYOUT_PROVIDER_NAME = "simulated"


class SimulatedPayoutProvider:
    name = SIMULATED_PAYOUT_PROVIDER_NAME

    def __init__(self, *, app_env: str) -> None:
        if app_env.strip().lower() not in SIMULATOR_APP_ENVS:
            allowed = ", ".join(sorted(SIMULATOR_APP_ENVS))
            raise RuntimeError(f"The simulated payout provider requires APP_ENV to be one of: {allowed}.")

    def create_payout(self, request: PayoutRequest) -> PayoutResult:
        digest = hashlib.sha256(request.idempotency_key.encode("utf-8")).hexdigest()[:32]
        return PayoutResult(provider_payout_id=f"simpayout_{digest}", status="released")
