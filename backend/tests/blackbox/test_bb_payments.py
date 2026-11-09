"""Simulated payment lifecycle, single-use checkout and webhook boundary."""

import pytest


def test_payment_creates_exactly_one_service(api, headers, paid_service, db):
    """README.md#payments-simulated-provider; caja-negra.md S3: approval reserves once, pay twice refused."""
    service_id = paid_service['service']
    detail = api.get(f'/api/customer/services/{service_id}', headers=headers())
    assert detail.status_code == 200, detail.text
    assert detail.json()['status'] == 'confirmed'
    assert detail.json()['amount'] == 10001
    assert db.execute('SELECT count(*) FROM "Servicio"').fetchone()[0] == 1
    assert db.execute('SELECT "Estado" FROM "Cotizacion" WHERE "ID"=%s', (paid_service['quotation'],)).fetchone()[0] == 'paid'
    assert api.post(f"/api/quotations/{paid_service['quotation']}/payments", headers=headers()).status_code == 409
    assert db.execute('SELECT count(*) FROM "Servicio"').fetchone()[0] == 1


@pytest.mark.parametrize('actor', ['other', 'owner'])
def test_checkout_is_bound_to_paying_customer(api, headers, checkout, db, actor):
    """README.md#payments-simulated-provider: only the paying customer may consume a checkout link."""
    response = api.post(f"/api/payments/simulated/{checkout['payment']}/complete", headers=headers(actor), json={'token': checkout['checkout_token'], 'approve': True})
    assert response.status_code in (403, 404), response.text
    assert db.execute('SELECT count(*) FROM "Servicio"').fetchone()[0] == 0
    valid = api.post(f"/api/payments/simulated/{checkout['payment']}/complete", headers=headers(), json={'token': checkout['checkout_token'], 'approve': True})
    assert valid.status_code == 200
    assert valid.json()['status'] == 'approved'


def test_tampered_checkout_does_not_consume_link(api, headers, checkout, db):
    """README.md#payments-simulated-provider: signed checkout, refused confirmation releases consumption."""
    path = f"/api/payments/simulated/{checkout['payment']}/complete"
    invalid = api.post(path, headers=headers(), json={'token': 'tampered', 'approve': True})
    assert invalid.status_code in (400, 403), invalid.text
    assert db.execute('SELECT count(*) FROM "Servicio"').fetchone()[0] == 0
    assert api.post(path, headers=headers(), json={'token': checkout['checkout_token'], 'approve': False}).status_code == 200
    assert db.execute('SELECT count(*) FROM "Servicio"').fetchone()[0] == 0
    assert api.get(f"/api/payments/{checkout['payment']}", headers=headers()).json()['status'] == 'rejected'


@pytest.mark.parametrize('secret,status', [(None, 401), ('wrong', 401), ('blackbox-local-webhook-only', 403)])
def test_webhook_cannot_approve_simulated_payment(api, checkout, db, secret, status):
    """README.md#payments-simulated-provider: webhook requires secret (401); simulated provider refused (403)."""
    response = api.post('/api/payments/confirm', headers={} if secret is None else {'X-Amira-Payment-Webhook-Secret': secret}, json={'paymentId': checkout['payment'], 'providerPaymentId': 'forged', 'status': 'approved', 'signature': 'forged'})
    assert response.status_code == status, response.text
    assert db.execute('SELECT count(*) FROM "Servicio"').fetchone()[0] == 0


@pytest.mark.xfail(strict=True, reason="BUG: README.md#payments-simulated-provider: expected single-use checkout replay rejection, got 200 approved")
def test_consumed_checkout_link_is_rejected(api, headers, paid_service, db):
    """README.md#payments-simulated-provider: checkout link is single-use; caja-negra.md S3 pay twice."""
    response = api.post(f"/api/payments/simulated/{paid_service['payment']}/complete", headers=headers(),
                        json={'token': paid_service['checkout_token'], 'approve': True})
    assert db.execute('SELECT count(*) FROM "Servicio"').fetchone()[0] == 1
    assert response.status_code == 409, response.text
