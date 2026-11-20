"""Checkout Pro test adapter; provider responses are untrusted until fully validated."""

import hashlib
import hmac
import logging
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

# Checkout Pro returns a country-specific sandbox host (for example sandbox.mercadopago.cl for Chile).
SANDBOX_HOST = re.compile(r"sandbox\.mercadopago\.(?:com|cl|com\.(?:ar|br|mx|co|pe|uy))")
PROVIDER_BODY_LOG_LIMIT = 300


def verify_webhook_signature(secret: str, resource_id: str, request_id: str, signature: str) -> bool:
    if not secret or not resource_id.isascii() or not resource_id.isdigit() or not request_id or not signature:
        return False
    parts = [part.strip().partition("=") for part in signature.split(",")]
    values = {key: value for key, sep, value in parts if sep}
    if len(parts) != 2 or set(values) != {"ts", "v1"} or not values["ts"].isascii() or not values["ts"].isdigit():
        return False
    manifest = f"id:{resource_id};request-id:{request_id};ts:{values['ts']};"
    digest = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest.encode(), values["v1"].encode())


class MercadoPagoError(Exception):
    pass


class MercadoPagoProvider:
    name = "mercado_pago"

    def __init__(self, *, access_token: str, frontend_base_url: str, test_seller_id: str, transport=None):
        self._token = access_token
        self._frontend = frontend_base_url.rstrip("/")
        self._transport = transport
        self._seller_id = test_seller_id

    def _request(self, method, path, **kwargs):
        try:
            with httpx.Client(base_url="https://api.mercadopago.com", transport=self._transport,
                              timeout=10, follow_redirects=False, headers={"Authorization": f"Bearer {self._token}"}) as client:
                response = client.request(method, path, **kwargs)
                if response.is_error:
                    # The provider body explains the rejection; it never contains our access token.
                    logger.warning("Mercado Pago %s %s answered %s: %s", method, path, response.status_code,
                                   response.text[:PROVIDER_BODY_LOG_LIMIT])
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Invalid provider response")
                return data
        except (httpx.HTTPError, ValueError) as exc:
            if not isinstance(exc, httpx.HTTPStatusError):
                logger.warning("Mercado Pago %s %s failed: %s", method, path, type(exc).__name__)
            raise MercadoPagoError("Mercado Pago is unavailable.") from exc

    @staticmethod
    def _sandbox_url(data):
        url = data.get("sandbox_init_point")
        if not isinstance(url, str):
            raise MercadoPagoError("Missing sandbox checkout URL.")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not SANDBOX_HOST.fullmatch(parsed.hostname or "") or parsed.username or parsed.password or parsed.port not in (None, 443):
            logger.warning("Mercado Pago returned an unexpected sandbox checkout host: %s", parsed.hostname)
            raise MercadoPagoError("Invalid sandbox checkout URL.")
        return url

    def create_checkout(self, payment_id: UUID, amount: Decimal):
        if amount <= 0 or amount != amount.to_integral_value():
            raise MercadoPagoError("Invalid CLP amount.")
        result_url = f"{self._frontend}/pagos/resultado?{urlencode({'paymentId': str(payment_id)})}"
        data = self._request("POST", "/checkout/preferences", json={
            "items": [{"title": "Cotización de servicio", "quantity": 1, "unit_price": int(amount), "currency_id": "CLP"}],
            "external_reference": str(payment_id),
            "back_urls": {"success": result_url, "failure": result_url, "pending": result_url},
        })
        if str(data.get("collector_id")) != self._seller_id:
            logger.warning("Mercado Pago preference seller mismatch: collector_id=%s, configured test seller=%s",
                           data.get("collector_id"), self._seller_id)
            raise MercadoPagoError("Preference seller mismatch.")
        if not isinstance(data.get("id"), str) or not data["id"]:
            raise MercadoPagoError("Missing preference ID.")
        return data["id"], self._sandbox_url(data)

    def checkout_url(self, payment_id, provider_payment_id, customer_id):
        from urllib.parse import quote
        data = self._request("GET", f"/checkout/preferences/{quote(provider_payment_id, safe='')}")
        if data.get("id") != provider_payment_id or data.get("external_reference") != str(payment_id) or str(data.get("collector_id")) != self._seller_id:
            raise MercadoPagoError("Preference mismatch.")
        return self._sandbox_url(data)

    def lookup(self, payment_id: UUID, amount: Decimal, currency: str, resource_id: str | None = None):
        if resource_id is not None:
            data = self._request("GET", f"/v1/payments/{resource_id}")
            if str(data.get("id")) != resource_id:
                return []
            results = [data]
        else:
            data = self._request("GET", "/v1/payments/search", params={"external_reference": str(payment_id), "limit": 50})
            results = data.get("results")
        if not isinstance(results, list):
            raise MercadoPagoError("Invalid payment search response.")
        evidence = []
        for item in results:
            if not isinstance(item, dict) or item.get("live_mode") is not False:
                continue
            if item.get("external_reference") != str(payment_id) or item.get("currency_id") != currency or str(item.get("collector_id")) != self._seller_id:
                continue
            try:
                matching_amount = Decimal(str(item.get("transaction_amount"))) == amount
            except InvalidOperation:
                matching_amount = False
            if matching_amount and item.get("id") and item.get("status") in {"approved", "rejected"}:
                evidence.append((str(item["id"]), item["status"]))
        # Process approvals first when one checkout contains multiple payment attempts.
        return sorted(evidence, key=lambda item: item[1] != "approved")
