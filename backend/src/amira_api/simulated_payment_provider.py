"""Simulated payment adapter for development. It implements the PaymentProvider port with HMAC signatures.

The adapter refuses to run outside the development allowlist, so it cannot take real money in production.
Confirmations and checkout tokens are signed with a server-side secret that the browser never sees.
"""

import hashlib
import hmac
from urllib.parse import urlencode
from uuid import UUID, uuid4

SIMULATOR_APP_ENVS = frozenset({"development", "local", "test"})


class SimulatedPaymentProvider:
    name = "simulated"

    def __init__(self, *, secret: str, frontend_base_url: str, app_env: str) -> None:
        if app_env.strip().lower() not in SIMULATOR_APP_ENVS:
            allowed = ", ".join(sorted(SIMULATOR_APP_ENVS))
            raise RuntimeError(f"The simulated payment provider requires APP_ENV to be one of: {allowed}.")
        if not secret:
            raise RuntimeError("The simulated payment provider requires a signing secret.")
        self._secret = secret.encode("utf-8")
        self._frontend_base_url = frontend_base_url.rstrip("/")

    def new_provider_payment_id(self) -> str:
        return f"sim_{uuid4().hex}"

    def checkout_url(self, payment_id: UUID, provider_payment_id: str) -> str:
        token = self.checkout_token(payment_id, provider_payment_id)
        query = urlencode({"paymentId": str(payment_id), "token": token})
        return f"{self._frontend_base_url}/pagos/simulado?{query}"

    def checkout_token(self, payment_id: UUID, provider_payment_id: str) -> str:
        return self._sign("checkout", str(payment_id), provider_payment_id)

    def verify_checkout_token(self, payment_id: UUID, provider_payment_id: str, token: str) -> bool:
        return _same(self.checkout_token(payment_id, provider_payment_id), token)

    def sign_confirmation(self, payment_id: UUID, provider_payment_id: str, status: str) -> str:
        return self._sign("confirm", str(payment_id), provider_payment_id, status)

    def verify_confirmation(self, payment_id: UUID, provider_payment_id: str, status: str, signature: str) -> bool:
        return _same(self.sign_confirmation(payment_id, provider_payment_id, status), signature)

    def _sign(self, purpose: str, *parts: str) -> str:
        message = "|".join((purpose, *parts)).encode("utf-8")
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()


def _same(expected: str, received: str) -> bool:
    # Compared as bytes: a non-ASCII value would make hmac.compare_digest raise on str input.
    return hmac.compare_digest(expected.encode("utf-8"), received.encode("utf-8"))
