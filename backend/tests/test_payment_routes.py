"""Payments through the PaymentProvider port: simulated checkout, server-to-server webhook confirmation, and gates."""

from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from amira_api import payment_service
from amira_api.auth import get_current_user
from amira_api.clock import utc_now
from amira_api.main import app
from amira_api.models import Cotizacion, Pago, Servicio
from amira_api.payment_provider import SIMULATED_PROVIDER_NAME
from amira_api.payment_routes import get_payment_provider, get_simulated_provider
from amira_api.settings import Settings, get_settings
from amira_api.simulated_payment_provider import SimulatedPaymentProvider
from chat_support import (
    CUSTOMER_AUTH,
    DRIVER_AUTH,
    OTHER_CUSTOMER_AUTH,
    PROVIDER_AUTH,
    Scenario,
    api,
    db,
    scenario,
)

SECRET = "test-simulator-secret"
WEBHOOK = "test-webhook-secret"
FRONTEND = "http://frontend.test"
WEBHOOK_HEADER = "X-Amira-Payment-Webhook-Secret"
QUOTATION_BODY = {"amount": 150000, "serviceAt": "2026-10-20T09:00:00-03:00", "description": "Mudanza", "validityHours": 48}


class FakeClock:
    def __init__(self, start) -> None:
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now = self.now + delta


class ExternalTestProvider(SimulatedPaymentProvider):
    """Stands in for a real provider adapter: same signing scheme, another name, so the webhook may confirm it."""

    name = "external-test"


def _settings(omit: tuple[str, ...] = (), **overrides) -> Settings:
    values = {
        "app_env": "test",
        "payment_simulator_secret": SecretStr(SECRET),
        "frontend_base_url": FRONTEND,
        "payment_webhook_secret": SecretStr(WEBHOOK),
    }
    values.update(overrides)
    for name in omit:
        values.pop(name, None)
    # model_construct leaves omitted fields unset, which is how the explicit-APP_ENV gate is exercised.
    return Settings.model_construct(**values)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(utc_now())


@pytest.fixture
def simulator(clock: FakeClock) -> SimulatedPaymentProvider:
    return SimulatedPaymentProvider(secret=SECRET, frontend_base_url=FRONTEND, app_env="test", clock=clock)


@pytest.fixture
def external(clock: FakeClock) -> ExternalTestProvider:
    return ExternalTestProvider(secret=SECRET, frontend_base_url=FRONTEND, app_env="test", clock=clock)


@pytest.fixture
def pay(api, simulator):
    """Development wiring: the simulated adapter is both the payment provider and the checkout provider."""
    app.dependency_overrides[get_payment_provider] = lambda: simulator
    app.dependency_overrides[get_simulated_provider] = lambda: simulator
    app.dependency_overrides[get_settings] = lambda: _settings()
    yield api
    for dependency in (get_payment_provider, get_simulated_provider, get_settings):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture
def webhook_pay(pay, external):
    """Same client, but payments are started with the external provider so the webhook route may confirm them."""
    app.dependency_overrides[get_payment_provider] = lambda: external
    return pay


def _quote(pay, scenario: Scenario) -> str:
    response = pay(
        f"/api/chats/{scenario.chat_a.id}/quotations",
        as_auth_id=PROVIDER_AUTH,
        method="POST",
        json=QUOTATION_BODY,
    )
    assert response.status_code == 201, response.text
    return response.json()["quotationId"]


def _start(pay, quotation_id, *, auth=CUSTOMER_AUTH):
    return pay(f"/api/quotations/{quotation_id}/payments", as_auth_id=auth, method="POST")


def _pending_payment(pay, scenario: Scenario, db: Session) -> Pago:
    _start(pay, _quote(pay, scenario))
    return db.query(Pago).one()


def _token(checkout_url: str) -> str:
    return parse_qs(urlparse(checkout_url).query)["token"][0]


def _complete(pay, payment_id, token: str, approve: bool, *, auth=CUSTOMER_AUTH):
    return pay(
        f"/api/payments/simulated/{payment_id}/complete",
        as_auth_id=auth,
        method="POST",
        json={"token": token, "approve": approve},
    )


def _confirm(pay, provider, payment: Pago, status: str, *, signature: str | None = None, secret: str | None = WEBHOOK):
    body = {
        "paymentId": str(payment.id),
        "providerPaymentId": payment.provider_payment_id,
        "status": status,
        "signature": signature or provider.sign_confirmation(payment.id, payment.provider_payment_id, status),
    }
    headers = {} if secret is None else {WEBHOOK_HEADER: secret}
    return pay("/api/payments/confirm", as_auth_id=CUSTOMER_AUTH, method="POST", json=body, headers=headers)


# Starting a payment


def test_customer_starts_a_payment_with_a_token_bound_to_the_payment_and_customer(pay, scenario, db: Session, simulator):
    body = _start(pay, _quote(pay, scenario)).json()

    payment = db.query(Pago).one()
    assert body["paymentId"] == str(payment.id)
    assert body["checkoutUrl"].startswith(f"{FRONTEND}/pagos/simulado?paymentId={payment.id}&token=")
    assert (payment.status, payment.amount, payment.currency, payment.provider) == ("pending", 150000, "CLP", "simulated")
    assert simulator.verify_checkout_token(
        payment.id, payment.provider_payment_id, scenario.customer.id, _token(body["checkoutUrl"])
    )


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
    quotation.created_at = utc_now() - timedelta(days=3)
    quotation.expires_at = utc_now() - timedelta(days=1)
    db.commit()

    assert _start(pay, quotation_id).status_code == 409
    assert db.query(Pago).count() == 0


def test_superseded_quotation_cannot_be_paid(pay, scenario):
    first = _quote(pay, scenario)
    pay(
        f"/api/chats/{scenario.chat_a.id}/quotations",
        as_auth_id=PROVIDER_AUTH,
        method="POST",
        json={**QUOTATION_BODY, "amount": 99000},
    )

    assert _start(pay, first).status_code == 409


def test_quotation_cannot_be_rejected_while_its_payment_is_in_progress(pay, scenario):
    quotation_id = _quote(pay, scenario)
    _start(pay, quotation_id)

    response = pay(f"/api/quotations/{quotation_id}/reject", as_auth_id=CUSTOMER_AUTH, method="POST")

    assert response.status_code == 409


# Simulated checkout: token rules (R1-001 part 2)


def test_simulated_approval_marks_the_quotation_paid_and_creates_the_service(pay, scenario, db: Session):
    quotation_id = _quote(pay, scenario)
    started = _start(pay, quotation_id).json()

    response = _complete(pay, started["paymentId"], _token(started["checkoutUrl"]), approve=True)

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["quotationStatus"]) == ("approved", "paid")
    assert body["quotationId"] == quotation_id
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


def test_checkout_token_is_bound_to_the_payment_id(pay, scenario, db: Session, simulator):
    started = _start(pay, _quote(pay, scenario)).json()
    payment = db.query(Pago).one()
    foreign_token = _token(simulator.checkout_url(uuid4(), payment.provider_payment_id, scenario.customer.id))

    response = _complete(pay, payment.id, foreign_token, approve=True)

    assert response.status_code == 400
    assert db.query(Servicio).count() == 0
    assert started["paymentId"] == str(payment.id)


def test_checkout_token_is_bound_to_the_customer(pay, scenario, db: Session, simulator):
    started = _start(pay, _quote(pay, scenario)).json()
    payment = db.query(Pago).one()
    token_for_someone_else = _token(simulator.checkout_url(payment.id, payment.provider_payment_id, uuid4()))

    response = _complete(pay, payment.id, token_for_someone_else, approve=True)

    assert response.status_code == 400
    assert db.query(Pago).one().status == "pending"


def test_checkout_token_is_single_use_across_decisions(pay, scenario, db: Session):
    started = _start(pay, _quote(pay, scenario)).json()
    token = _token(started["checkoutUrl"])

    assert _complete(pay, started["paymentId"], token, approve=False).status_code == 200
    assert _complete(pay, started["paymentId"], token, approve=True).status_code == 400
    assert db.query(Pago).one().checkout_used_at is not None
    assert db.query(Servicio).count() == 0


def test_retrying_the_same_approval_returns_the_existing_result(pay, scenario, db: Session):
    started = _start(pay, _quote(pay, scenario)).json()
    token = _token(started["checkoutUrl"])

    assert _complete(pay, started["paymentId"], token, approve=True).status_code == 200
    assert db.query(Servicio).count() == 1


def test_checkout_token_is_valid_until_fifteen_minutes(pay, scenario, clock: FakeClock):
    started = _start(pay, _quote(pay, scenario)).json()
    clock.advance(timedelta(minutes=14))

    assert _complete(pay, started["paymentId"], _token(started["checkoutUrl"]), approve=True).status_code == 200


def test_expired_checkout_token_is_rejected_and_changes_nothing(pay, scenario, db: Session, clock: FakeClock):
    started = _start(pay, _quote(pay, scenario)).json()
    clock.advance(timedelta(minutes=15, seconds=1))

    response = _complete(pay, started["paymentId"], _token(started["checkoutUrl"]), approve=True)

    assert response.status_code == 400
    assert db.query(Pago).one().status == "pending"
    assert db.query(Pago).one().checkout_used_at is None
    assert db.query(Servicio).count() == 0


def test_only_the_payment_customer_can_complete_the_checkout(pay, scenario, db: Session):
    started = _start(pay, _quote(pay, scenario)).json()
    token = _token(started["checkoutUrl"])

    for auth in (OTHER_CUSTOMER_AUTH, PROVIDER_AUTH, DRIVER_AUTH):
        assert _complete(pay, started["paymentId"], token, approve=True, auth=auth).status_code == 404
    assert db.query(Pago).one().status == "pending"
    assert db.query(Pago).one().checkout_used_at is None


def test_simulated_completion_only_applies_to_simulated_payments(webhook_pay, pay, scenario, db: Session, external):
    started = _start(webhook_pay, _quote(webhook_pay, scenario)).json()
    token = _token(external.checkout_url(UUID(started["paymentId"]), db.query(Pago).one().provider_payment_id, scenario.customer.id))

    assert _complete(pay, started["paymentId"], token, approve=True).status_code == 404


def test_checkout_token_from_another_secret_is_rejected(simulator, clock: FakeClock):
    other = SimulatedPaymentProvider(secret="another-secret", frontend_base_url=FRONTEND, app_env="test", clock=clock)
    payment_id, provider_payment_id, customer_id = uuid4(), "sim_x", uuid4()
    token = _token(other.checkout_url(payment_id, provider_payment_id, customer_id))

    assert not simulator.verify_checkout_token(payment_id, provider_payment_id, customer_id, token)


def test_malformed_checkout_token_is_rejected(simulator):
    assert not simulator.verify_checkout_token(uuid4(), "sim_x", uuid4(), "not-a-token")
    assert not simulator.verify_checkout_token(uuid4(), "sim_x", uuid4(), "")


# Webhook confirmation: server-to-server only (R1-001 part 1)


def test_webhook_confirmation_needs_the_webhook_secret(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)

    assert _confirm(webhook_pay, external, payment, "approved", secret=None).status_code == 401
    assert _confirm(webhook_pay, external, payment, "approved", secret="wrong").status_code == 401
    assert db.query(Pago).one().status == "pending"
    assert db.query(Servicio).count() == 0


def test_webhook_confirmation_is_refused_when_the_secret_is_not_configured(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)
    app.dependency_overrides[get_settings] = lambda: _settings(omit=("payment_webhook_secret",))

    assert _confirm(webhook_pay, external, payment, "approved").status_code == 503


def test_webhook_confirmation_approves_and_replays_idempotently(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)

    first = _confirm(webhook_pay, external, payment, "approved")
    replay = _confirm(webhook_pay, external, payment, "approved")

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert first.json()["serviceId"] is not None
    assert db.query(Servicio).count() == 1


def test_webhook_confirmation_needs_no_user_session(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)
    app.dependency_overrides.pop(get_current_user, None)
    body = {
        "paymentId": str(payment.id),
        "providerPaymentId": payment.provider_payment_id,
        "status": "approved",
        "signature": external.sign_confirmation(payment.id, payment.provider_payment_id, "approved"),
    }

    response = TestClient(app).post("/api/payments/confirm", json=body, headers={WEBHOOK_HEADER: WEBHOOK})

    assert response.status_code == 200
    assert db.query(Pago).one().status == "approved"


def test_simulated_confirmation_is_refused_on_the_webhook_route(pay, scenario, db: Session, simulator):
    payment = _pending_payment(pay, scenario, db)

    response = _confirm(pay, simulator, payment, "approved")

    assert response.status_code == 403
    assert db.query(Pago).one().status == "pending"
    assert db.query(Servicio).count() == 0


def test_bad_webhook_signature_is_refused_and_changes_nothing(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)

    response = _confirm(webhook_pay, external, payment, "approved", signature="0" * 64)

    assert response.status_code == 400
    assert db.query(Pago).one().status == "pending"
    assert db.query(Servicio).count() == 0


def test_signature_for_a_different_status_is_refused(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)
    rejection_signature = external.sign_confirmation(payment.id, payment.provider_payment_id, "rejected")

    response = _confirm(webhook_pay, external, payment, "approved", signature=rejection_signature)

    assert response.status_code == 400


def test_rejected_webhook_payment_leaves_the_quotation_pending(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)

    response = _confirm(webhook_pay, external, payment, "rejected")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["quotationStatus"] == "pending"
    assert response.json()["serviceId"] is None


def test_approved_payment_cannot_flip_to_rejected(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)
    assert _confirm(webhook_pay, external, payment, "approved").status_code == 200

    response = _confirm(webhook_pay, external, payment, "rejected")

    assert response.status_code == 409
    db.refresh(payment)
    assert payment.status == "approved"


def test_unknown_payment_confirmation_is_not_found(webhook_pay, external):
    unknown_id = uuid4()
    body = {
        "paymentId": str(unknown_id),
        "providerPaymentId": "sim_missing",
        "status": "approved",
        "signature": external.sign_confirmation(unknown_id, "sim_missing", "approved"),
    }

    response = webhook_pay("/api/payments/confirm", as_auth_id=CUSTOMER_AUTH, method="POST", json=body, headers={WEBHOOK_HEADER: WEBHOOK})

    assert response.status_code == 404


def test_only_one_service_exists_when_the_chat_already_has_one(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)
    assert _confirm(webhook_pay, external, payment, "approved").status_code == 200

    response = webhook_pay(
        f"/api/chats/{scenario.chat_a.id}/quotations",
        as_auth_id=PROVIDER_AUTH,
        method="POST",
        json={**QUOTATION_BODY, "amount": 99000},
    )

    assert response.status_code == 409
    assert db.query(Servicio).count() == 1


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


# Gates: the simulator is enabled only by an explicit allowlisted APP_ENV (fail closed)


@pytest.mark.parametrize("app_env", ["production", "staging", "preview", ""])
def test_adapter_refuses_environments_outside_the_allowlist(app_env):
    with pytest.raises(RuntimeError):
        SimulatedPaymentProvider(secret=SECRET, frontend_base_url=FRONTEND, app_env=app_env)


@pytest.mark.parametrize("app_env", ["development", "local", "test", " Development "])
def test_factory_selects_the_simulator_for_allowlisted_environments(app_env):
    assert isinstance(get_payment_provider(_settings(app_env=app_env)), SimulatedPaymentProvider)


def test_factory_does_not_select_the_simulator_when_app_env_is_unset():
    with pytest.raises(HTTPException) as refused:
        get_payment_provider(_settings(omit=("app_env",)))

    assert refused.value.status_code == 503


def test_simulator_is_disabled_when_app_env_is_not_explicitly_set(api, scenario):
    app.dependency_overrides[get_settings] = lambda: _settings(omit=("app_env",))
    quotation_id = _quote(api, scenario)

    start = _start(api, quotation_id)
    complete = _complete(api, uuid4(), "token", approve=True)

    assert start.status_code == 503
    assert complete.status_code == 404


def test_simulator_routes_are_not_found_in_production(api):
    app.dependency_overrides[get_settings] = lambda: _settings(app_env="production")

    complete = _complete(api, uuid4(), "token", approve=True)
    start = _start(api, uuid4())

    assert complete.status_code == 404
    assert start.status_code == 503


def test_domain_service_depends_on_the_port_not_the_simulated_adapter():
    source = Path(payment_service.__file__).read_text(encoding="utf-8")

    assert "simulated_payment_provider" not in source
    assert "payment_provider" in source


def test_simulated_provider_name_matches_the_port_constant():
    assert SIMULATED_PROVIDER_NAME == "simulated"


# Follow-up: payment review warnings (R4-001, R1-002, R3-001, R4-002)


def _supersede(pay, scenario) -> None:
    response = pay(
        f"/api/chats/{scenario.chat_a.id}/quotations",
        as_auth_id=PROVIDER_AUTH,
        method="POST",
        json={**QUOTATION_BODY, "amount": 99000},
    )
    assert response.status_code == 201


def test_confirmation_refuses_a_superseded_quotation_and_marks_the_payment_rejected(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)
    _supersede(webhook_pay, scenario)

    response = _confirm(webhook_pay, external, payment, "approved")

    assert response.status_code == 409
    assert "reemplazada" in response.json()["detail"]
    assert db.query(Pago).one().status == "rejected"
    assert db.query(Servicio).count() == 0
    assert db.query(Cotizacion).filter(Cotizacion.status == "pending").count() == 1


def test_confirmation_refuses_an_expired_quotation_and_marks_the_payment_rejected(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)
    quotation = db.query(Cotizacion).one()
    quotation.created_at = utc_now() - timedelta(days=3)
    quotation.expires_at = utc_now() - timedelta(days=1)
    db.commit()

    response = _confirm(webhook_pay, external, payment, "approved")

    assert response.status_code == 409
    assert "venció" in response.json()["detail"]
    assert db.query(Pago).one().status == "rejected"
    assert db.query(Cotizacion).one().status == "pending"
    assert db.query(Servicio).count() == 0


def test_confirmation_refuses_a_quotation_already_paid_by_another_payment(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)
    db.query(Cotizacion).one().status = "paid"
    db.commit()

    response = _confirm(webhook_pay, external, payment, "approved")

    assert response.status_code == 409
    assert db.query(Pago).one().status == "rejected"
    assert db.query(Servicio).count() == 0


def test_simulated_completion_of_a_superseded_quotation_is_refused(pay, scenario, db: Session):
    started = _start(pay, _quote(pay, scenario)).json()
    _supersede(pay, scenario)

    response = _complete(pay, started["paymentId"], _token(started["checkoutUrl"]), approve=True)

    assert response.status_code == 409
    assert db.query(Pago).one().status == "rejected"
    assert db.query(Servicio).count() == 0


def test_confirmation_refuses_a_payment_owned_by_another_provider(pay, scenario, db: Session, external):
    payment = _pending_payment(pay, scenario, db)  # started by the simulated adapter
    app.dependency_overrides[get_payment_provider] = lambda: external

    response = _confirm(pay, external, payment, "approved")

    assert response.status_code == 404
    assert db.query(Pago).one().status == "pending"
    assert db.query(Servicio).count() == 0


@pytest.mark.parametrize("issued", ["\u00b2", "1\u00b2", "\u0661\u0667"])
def test_checkout_token_with_non_ascii_digits_is_a_bad_request(pay, scenario, db: Session, simulator, issued):
    started = _start(pay, _quote(pay, scenario)).json()
    payment = db.query(Pago).one()

    response = _complete(pay, started["paymentId"], f"{issued}.{'0' * 64}", approve=True)

    assert response.status_code == 400
    assert not simulator.verify_checkout_token(payment.id, payment.provider_payment_id, scenario.customer.id, f"{issued}.{'0' * 64}")
    assert db.query(Pago).one().status == "pending"


def test_retrying_the_same_rejection_returns_the_existing_result(pay, scenario, db: Session):
    started = _start(pay, _quote(pay, scenario)).json()
    token = _token(started["checkoutUrl"])

    first = _complete(pay, started["paymentId"], token, approve=False)
    second = _complete(pay, started["paymentId"], token, approve=False)

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert second.json()["status"] == "rejected"


def test_retrying_the_same_approval_returns_the_same_body(pay, scenario, db: Session):
    started = _start(pay, _quote(pay, scenario)).json()
    token = _token(started["checkoutUrl"])

    first = _complete(pay, started["paymentId"], token, approve=True)
    second = _complete(pay, started["paymentId"], token, approve=True)

    assert second.status_code == 200
    assert second.json() == first.json()
    assert db.query(Servicio).count() == 1
