"""Simulated payment adapter for development. It implements the PaymentProvider port with HMAC signatures.

The adapter refuses to run outside the development allowlist, so it cannot take real money in production.
Checkout tokens are bound to the payment, its provider id and the customer, carry their issue time and expire after
CHECKOUT_TOKEN_TTL. Confirmations are signed with a server-side secret that the browser never sees.
"""

import hashlib
import hmac
from collections.abc import Callable
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4

from amira_api.clock import utc_now
from amira_api.payment_provider import SIMULATED_PROVIDER_NAME

SIMULATOR_APP_ENVS = frozenset({"development", "local", "test"})
CHECKOUT_TOKEN_TTL = timedelta(minutes=15)


class SimulatedPaymentProvider:
    name = SIMULATED_PROVIDER_NAME

    def __init__(
        self,
        *,
        secret: str,
        frontend_base_url: str,
        app_env: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if app_env.strip().lower() not in SIMULATOR_APP_ENVS:
            allowed = ", ".join(sorted(SIMULATOR_APP_ENVS))
            raise RuntimeError(f"The simulated payment provider requires APP_ENV to be one of: {allowed}.")
        if not secret:
            raise RuntimeError("The simulated payment provider requires a signing secret.")
        self._secret = secret.encode("utf-8")
        self._frontend_base_url = frontend_base_url.rstrip("/")
        self._clock = clock

    def new_provider_payment_id(self) -> str:
        return f"sim_{uuid4().hex}"

    def checkout_url(self, payment_id: UUID, provider_payment_id: str, customer_id: UUID) -> str:
        issued_at = int(self._clock().timestamp())
        token = f"{issued_at}.{self._checkout_mac(payment_id, provider_payment_id, customer_id, issued_at)}"
        query = urlencode({"paymentId": str(payment_id), "token": token})
        return f"{self._frontend_base_url}/pagos/simulado?{query}"

    def verify_checkout_token(self, payment_id: UUID, provider_payment_id: str, customer_id: UUID, token: str) -> bool:
        """True only for an untampered token of this payment and customer, issued within CHECKOUT_TOKEN_TTL."""
        issued_text, separator, mac = token.partition(".")
        if not separator or not issued_text.isdigit():
            return False
        issued_at = int(issued_text)
        now = int(self._clock().timestamp())
        if issued_at > now or now - issued_at > CHECKOUT_TOKEN_TTL.total_seconds():
            return False
        return _same(self._checkout_mac(payment_id, provider_payment_id, customer_id, issued_at), mac)

    def sign_confirmation(self, payment_id: UUID, provider_payment_id: str, status: str) -> str:
        return self._sign("confirm", str(payment_id), provider_payment_id, status)

    def verify_confirmation(self, payment_id: UUID, provider_payment_id: str, status: str, signature: str) -> bool:
        return _same(self.sign_confirmation(payment_id, provider_payment_id, status), signature)

    def _checkout_mac(self, payment_id: UUID, provider_payment_id: str, customer_id: UUID, issued_at: int) -> str:
        return self._sign("checkout", str(payment_id), provider_payment_id, str(customer_id), str(issued_at))

    def _sign(self, purpose: str, *parts: str) -> str:
        message = "|".join((purpose, *parts)).encode("utf-8")
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()


def _same(expected: str, received: str) -> bool:
    # Compared as bytes: a non-ASCII value would make hmac.compare_digest raise on str input.
    return hmac.compare_digest(expected.encode("utf-8"), received.encode("utf-8"))
