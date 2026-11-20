from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from amira_api.mercado_pago_provider import MercadoPagoProvider, MercadoPagoError


def provider(handler):
    return MercadoPagoProvider(access_token="secret", frontend_base_url="https://example.com", test_seller_id="1234", transport=httpx.MockTransport(handler))


def test_creates_checkout_with_bound_reference_and_amount():
    payment_id = uuid4()
    def handler(request):
        import json
        body = json.loads(request.content)
        assert request.url.path == "/checkout/preferences"
        assert request.headers["authorization"] == "Bearer secret"
        assert body["external_reference"] == str(payment_id)
        assert body["items"][0]["unit_price"] == 150000
        assert body["items"][0]["currency_id"] == "CLP"
        return httpx.Response(201, json={"id": "pref-1", "collector_id": 1234, "sandbox_init_point": "https://sandbox.mercadopago.com/checkout?pref_id=1"})
    pref, url = provider(handler).create_checkout(payment_id, Decimal("150000"))
    assert pref == "pref-1"
    assert url.startswith("https://sandbox.mercadopago.com/")


@pytest.mark.parametrize("change", [
    {"live_mode": True}, {"live_mode": None}, {"transaction_amount": 1},
    {"currency_id": "USD"}, {"external_reference": "different"},
])
def test_payment_lookup_rejects_unbound_or_live_evidence(change):
    payment_id = uuid4()
    item = {"id": 123, "collector_id": 1234, "live_mode": False, "status": "approved", "transaction_amount": 150000,
            "currency_id": "CLP", "external_reference": str(payment_id)}
    item.update(change)
    def handler(request):
        return httpx.Response(200, json={"results": [item]})
    assert provider(handler).lookup(payment_id, Decimal("150000"), "CLP") == []


def test_payment_lookup_accepts_matching_approved_sandbox_payment():
    payment_id = uuid4()
    item = {"id": 123, "collector_id": 1234, "live_mode": False, "status": "approved", "transaction_amount": 150000,
            "currency_id": "CLP", "external_reference": str(payment_id)}
    def handler(request):
        assert request.url.path == "/v1/payments/search"
        assert request.url.params["external_reference"] == str(payment_id)
        return httpx.Response(200, json={"results": [item]})
    assert provider(handler).lookup(payment_id, Decimal("150000"), "CLP") == [("123", "approved")]


def test_webhook_signature_binds_resource_and_request_id():
    import hashlib
    import hmac
    from amira_api.mercado_pago_provider import verify_webhook_signature
    digest = hmac.new(b"secret", b"id:123;request-id:request;ts:100;", hashlib.sha256).hexdigest()
    assert verify_webhook_signature("secret", "123", "request", f"ts=100,v1={digest}")
    assert not verify_webhook_signature("secret", "124", "request", f"ts=100,v1={digest}")
    assert not verify_webhook_signature("secret", "123", "request", "ts=100,v1=invalid")
