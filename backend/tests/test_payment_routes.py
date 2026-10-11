"""Payments through the PaymentProvider port, using the simulated adapter: start, confirm, replay and conflicts."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from amira_api import payment_service
from amira_api.main import app
from amira_api.models import Cotizacion, Pago, Servicio
from amira_api.payment_routes import get_payment_provider, get_simulated_provider
from amira_api.settings import Settings, get_settings
from amira_api.simulated_payment_provider import SimulatedPaymentProvider
from chat_support import CUSTOMER_AUTH, DRIVER_AUTH, OTHER_CUSTOMER_AUTH, PROVIDER_AUTH, Scenario, api, db, scenario

SECRET = "test-simulator-secret"
FRONTEND = "http://frontend.test"
QUOTATION_BODY = {"amount": 150000, "serviceAt": "2026-10-20T09:00:00-03:00", "description": "Mudanza", "validityHours": 48}


@pytest.fixture
def provider() -> SimulatedPaymentProvider:
    return SimulatedPaymentProvider(secret=SECRET, frontend_base_url=FRONTEND, app_env="test")


@pytest.fixture
def pay(api, provider):
    app.dependency_overrides[get_payment_provider] = lambda: provider
    app.dependency_overrides[get_simulated_provider] = lambda: provider
    yield api
    app.dependency_overrides.pop(get_payment_provider, None)
    app.dependency_overrides.pop(get_simulated_provider, None)


def _quote(pay, scenario: Scenario, body: dict | None = None, chat=None) -> str:
    response = pay(
        f"/api/chats/{(chat or scenario.chat_a).id}/quotations",
        as_auth_id=PROVIDER_AUTH,
        method="POST",
        json=body or QUOTATION_BODY,
    )
    assert response.status_code == 201, response.text
    return response.json()["quotationId"]


def _start(pay, quotation_id, *, auth=CUSTOMER_AUTH):
    return pay(f"/api/quotations/{quotation_id}/payments", as_auth_id=auth, method="POST")


def _token(checkout_url: str) -> str:
    return parse_qs(urlparse(checkout_url).query)["token"][0]


def _complete(pay, payment_id, token: str, approve: bool, *, auth=CUSTOMER_AUTH):
    return pay(
        f"/api/payments/simulated/{payment_id}/complete",
        as_auth_id=auth,
        method="POST",
        json={"token": token, "approve": approve},
    )


def _confirm(pay, provider: SimulatedPaymentProvider, payment: Pago, status: str, *, signature: str | None = None):
    body = {
        "paymentId": str(payment.id),
        "providerPaymentId": payment.provider_payment_id,
        "status": status,
        "signature": signature or provider.sign_confirmation(payment.id, payment.provider_payment_id, status),
    }
    return pay("/api/payments/confirm", as_auth_id=CUSTOMER_AUTH, method="POST", json=body)


# Starting a payment


def test_customer_starts_a_payment_with_a_checkout_url_from_the_port(pay, scenario, db: Session, provider):
    quotation_id = _quote(pay, scenario)

    response = _start(pay, quotation_id)

    assert response.status_code == 201
    body = response.json()
    payment = db.query(Pago).one()
    assert body["paymentId"] == str(payment.id)
    assert body["checkoutUrl"] == provider.checkout_url(payment.id, payment.provider_payment_id)
    assert body["checkoutUrl"].startswith(f"{FRONTEND}/pagos/simulado?paymentId={payment.id}&token=")
    assert (payment.status, payment.amount, payment.currency, payment.provider) == ("pending", 150000, "CLP", "simulated")
    assert payment.quotation_id == UUID(quotation_id)


def test_starting_again_while_a_payment_is_in_progress_returns_the_same_payment(pay, scenario, db: Session):
    quotation_id = _quote(pay, scenario)

    first = _start(pay, quotation_id).json()
    second = _start(pay, quotation_id)

    assert second.status_code == 201
    assert second.json() == first
    assert db.query(Pago).count() == 1


def test_only_the_customer_can_start_a_payment(pay, scenario, db: Session):
    quotation_id = _quote(pay, scenario)

    assert _start(pay, quotation_id, auth=PROVIDER_AUTH).status_code == 403
    assert _start(pay, quotation_id, auth=OTHER_CUSTOMER_AUTH).status_code == 404
    assert _start(pay, uuid4(), auth=CUSTOMER_AUTH).status_code == 404
    assert db.query(Pago).count() == 0


def test_expired_quotation_cannot_be_paid(pay, scenario, db: Session):
    quotation_id = _quote(pay, scenario)
    quotation = db.get(Cotizacion, UUID(quotation_id))
    quotation.created_at = datetime.now(timezone.utc) - timedelta(days=3)
    quotation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    assert _start(pay, quotation_id).status_code == 409
    assert db.query(Pago).count() == 0


def test_superseded_quotation_cannot_be_paid(pay, scenario):
    first = _quote(pay, scenario)
    _quote(pay, scenario, body={**QUOTATION_BODY, "amount": 99000})

    assert _start(pay, first).status_code == 409


def test_quotation_cannot_be_rejected_while_its_payment_is_in_progress(pay, scenario):
    quotation_id = _quote(pay, scenario)
    _start(pay, quotation_id)

    response = pay(f"/api/quotations/{quotation_id}/reject", as_auth_id=CUSTOMER_AUTH, method="POST")

    assert response.status_code == 409


# Completing and confirming


def test_simulated_approval_marks_the_quotation_paid_and_creates_the_service(pay, scenario, db: Session, provider):
    quotation_id = _quote(pay, scenario)
    started = _start(pay, quotation_id).json()
    token = _token(started["checkoutUrl"])

    response = _complete(pay, started["paymentId"], token, approve=True)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["quotationId"] == quotation_id
    assert body["quotationStatus"] == "paid"
    assert body["serviceId"] is not None
    quotation = db.get(Cotizacion, UUID(quotation_id))
    service = db.query(Servicio).one()
    assert quotation.status == "paid"
    assert quotation.accepted_at is not None
    assert str(service.id) == body["serviceId"]
    assert service.accepted_quotation_id == quotation.id
    assert service.form_id == scenario.chat_a.form_id
    assert service.profile_id == scenario.provider_profile.id
    assert service.customer_id == scenario.customer.id
    assert (service.status, service.amount) == ("confirmed", 150000)
    assert db.query(Pago).one().status == "approved"


def test_signed_confirmation_is_accepted_and_replays_return_the_same_result(pay, scenario, db: Session, provider):
    quotation_id = _quote(pay, scenario)
    payment = db.get(Pago, UUID(_start(pay, quotation_id).json()["paymentId"]))

    first = _confirm(pay, provider, payment, "approved")
    replay = _confirm(pay, provider, payment, "approved")

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert db.query(Servicio).count() == 1


def test_a_bad_signature_is_refused_and_changes_nothing(pay, scenario, db: Session, provider):
    quotation_id = _quote(pay, scenario)
    payment = db.get(Pago, UUID(_start(pay, quotation_id).json()["paymentId"]))

    response = _confirm(pay, provider, payment, "approved", signature="0" * 64)

    assert response.status_code == 400
    db.refresh(payment)
    assert payment.status == "pending"
    assert db.get(Cotizacion, UUID(quotation_id)).status == "pending"
    assert db.query(Servicio).count() == 0


def test_signature_for_a_different_status_is_refused(pay, scenario, db: Session, provider):
    quotation_id = _quote(pay, scenario)
    payment = db.get(Pago, UUID(_start(pay, quotation_id).json()["paymentId"]))
    signature_for_rejection = provider.sign_confirmation(payment.id, payment.provider_payment_id, "rejected")

    response = _confirm(pay, provider, payment, "approved", signature=signature_for_rejection)

    assert response.status_code == 400


def test_rejected_payment_leaves_the_quotation_pending_and_allows_a_new_attempt(pay, scenario, db: Session, provider):
    quotation_id = _quote(pay, scenario)
    first = _start(pay, quotation_id).json()

    result = _complete(pay, first["paymentId"], _token(first["checkoutUrl"]), approve=False)

    assert result.status_code == 200
    assert result.json()["status"] == "rejected"
    assert result.json()["quotationStatus"] == "pending"
    assert result.json()["serviceId"] is None
    assert db.get(Cotizacion, UUID(quotation_id)).status == "pending"

    second = _start(pay, quotation_id)
    assert second.status_code == 201
    assert second.json()["paymentId"] != first["paymentId"]
    assert db.query(Pago).count() == 2


def test_a_payment_cannot_flip_from_approved_to_rejected(pay, scenario, db: Session, provider):
    quotation_id = _quote(pay, scenario)
    payment = db.get(Pago, UUID(_start(pay, quotation_id).json()["paymentId"]))
    assert _confirm(pay, provider, payment, "approved").status_code == 200

    response = _confirm(pay, provider, payment, "rejected")

    assert response.status_code == 409
    db.refresh(payment)
    assert payment.status == "approved"


def test_unknown_payment_confirmation_is_not_found(pay, provider, db: Session):
    # A genuinely signed confirmation for a payment that does not exist must be 404, not a signature failure.
    unknown_id = uuid4()
    body = {
        "paymentId": str(unknown_id),
        "providerPaymentId": "sim_missing",
        "status": "approved",
        "signature": provider.sign_confirmation(unknown_id, "sim_missing", "approved"),
    }

    assert pay("/api/payments/confirm", as_auth_id=CUSTOMER_AUTH, method="POST", json=body).status_code == 404


def test_only_one_service_exists_when_the_chat_already_has_one(pay, scenario, db: Session, provider):
    first_quote = _quote(pay, scenario)
    first_payment = db.get(Pago, UUID(_start(pay, first_quote).json()["paymentId"]))
    assert _confirm(pay, provider, first_payment, "approved").status_code == 200

    # A second, still pending quotation cannot be created once the chat is settled.
    chat_quote = pay(
        f"/api/chats/{scenario.chat_a.id}/quotations",
        as_auth_id=PROVIDER_AUTH,
        method="POST",
        json={**QUOTATION_BODY, "amount": 99000},
    )
    assert chat_quote.status_code == 409
    assert db.query(Servicio).count() == 1


# Simulated endpoint guards


def test_simulated_completion_rejects_a_wrong_token(pay, scenario, db: Session):
    started = _start(pay, _quote(pay, scenario)).json()

    response = _complete(pay, started["paymentId"], "not-the-token", approve=True)

    assert response.status_code == 400
    assert db.query(Servicio).count() == 0


def test_simulated_completion_is_only_for_the_paying_customer(pay, scenario):
    started = _start(pay, _quote(pay, scenario)).json()

    response = _complete(pay, started["paymentId"], _token(started["checkoutUrl"]), approve=True, auth=DRIVER_AUTH)

    assert response.status_code == 404


# Reading a payment


def test_customer_reads_the_payment_for_the_result_page(pay, scenario):
    quotation_id = _quote(pay, scenario)
    started = _start(pay, quotation_id).json()
    _complete(pay, started["paymentId"], _token(started["checkoutUrl"]), approve=True)

    response = pay(f"/api/payments/{started['paymentId']}", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "paymentId": started["paymentId"],
        "status": "approved",
        "quotationId": quotation_id,
        "quotationStatus": "paid",
        "chatId": str(scenario.chat_a.id),
    }


def test_provider_cannot_read_a_payment_and_outsiders_get_not_found(pay, scenario):
    started = _start(pay, _quote(pay, scenario)).json()

    assert pay(f"/api/payments/{started['paymentId']}", as_auth_id=PROVIDER_AUTH).status_code == 403
    assert pay(f"/api/payments/{started['paymentId']}", as_auth_id=OTHER_CUSTOMER_AUTH).status_code == 404


# Production gate and architecture


def test_simulated_adapter_refuses_to_run_in_production():
    with pytest.raises(RuntimeError):
        SimulatedPaymentProvider(secret=SECRET, frontend_base_url=FRONTEND, app_env="production")


def test_simulator_routes_are_not_found_in_production(api):
    production = Settings.model_construct(app_env="production", payment_simulator_secret=None, frontend_base_url=FRONTEND)
    app.dependency_overrides[get_settings] = lambda: production
    try:
        response = api(
            f"/api/payments/simulated/{uuid4()}/complete",
            as_auth_id=CUSTOMER_AUTH,
            method="POST",
            json={"token": "x", "approve": True},
        )
        start = api(f"/api/quotations/{uuid4()}/payments", as_auth_id=CUSTOMER_AUTH, method="POST")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 404
    assert start.status_code == 503


def test_domain_service_depends_on_the_port_not_the_simulated_adapter():
    source = Path(payment_service.__file__).read_text(encoding="utf-8")

    assert "simulated_payment_provider" not in source
    assert "payment_provider" in source
