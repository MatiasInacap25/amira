"""Payment transaction failure paths through the public service functions."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from amira_api import payment_service
from amira_api.clock import utc_now
from amira_api.models import Chat, Cotizacion, FormularioServicio, Pago, Servicio
from chat_support import CUSTOMER_AUTH, PROVIDER_AUTH, Scenario, api, db, scenario
from test_payment_routes import (
    FakeClock, _complete, _pending_payment, _quote, _settings, _start, _token,
    clock, pay, simulator,
)


def test_start_payment_rejects_a_chat_already_settled(pay, scenario, db, monkeypatch, simulator):
    quotation_id = _quote(pay, scenario)
    from uuid import UUID
    monkeypatch.setattr(payment_service, "chat_is_settled", lambda session, chat_id: True)
    with pytest.raises(payment_service.PaymentConflict, match="pagada"):
        payment_service.start_payment(db, simulator, UUID(quotation_id), utc_now())
    assert db.query(Pago).count() == 0


def test_confirmation_without_assigned_provider_creates_no_service(pay, scenario, db, simulator):
    payment = _pending_payment(pay, scenario, db)
    form = db.get(Cotizacion, payment.quotation_id).chat.form
    form.profile_id = None
    db.commit()
    signature = simulator.sign_confirmation(payment.id, payment.provider_payment_id, "approved")
    with pytest.raises(payment_service.PaymentConflict, match="prestador asignado"):
        payment_service.confirm_payment(db, simulator, payment_id=payment.id,
            provider_payment_id=payment.provider_payment_id, status="approved", signature=signature, now=utc_now())
    db.rollback()
    assert db.query(Servicio).count() == 0
    assert db.get(Pago, payment.id).status == "pending"


def test_confirmation_integrity_failure_rolls_back_and_translates_conflict(pay, scenario, db, simulator, monkeypatch):
    payment = _pending_payment(pay, scenario, db)
    identifier, provider_id = payment.id, payment.provider_payment_id
    original_commit = db.commit
    monkeypatch.setattr(db, "commit", Mock(side_effect=IntegrityError("duplicate", {}, Exception("unique"))))
    with pytest.raises(payment_service.PaymentConflict, match="servicio confirmado"):
        payment_service.confirm_payment(db, simulator, payment_id=identifier, provider_payment_id=provider_id,
            status="approved", signature=simulator.sign_confirmation(identifier, provider_id, "approved"), now=utc_now())
    monkeypatch.setattr(db, "commit", original_commit)
    assert db.query(Servicio).count() == 0
    assert db.get(Pago, identifier).status == "pending"


def test_unknown_account_cannot_reject_or_read_a_payment(pay):
    from uuid import uuid4
    for path in (f"/api/quotations/{uuid4()}/reject", f"/api/payments/{uuid4()}"):
        response = pay(path, as_auth_id=uuid4(), method="POST" if path.endswith("reject") else "GET")
        assert response.status_code == 404


def test_join_conflict_records_payment_rejection_without_service(pay, scenario, db, simulator, monkeypatch):
    from amira_api.shared_trip_service import SharedTripConflict
    payment = _pending_payment(pay, scenario, db)
    form = db.get(Cotizacion, payment.quotation_id).chat.form
    form.requested_trip_id = uuid4()
    form.is_exclusive = False
    db.commit()
    monkeypatch.setattr(payment_service, "link_join_request_stops", Mock(side_effect=SharedTripConflict("trip unavailable")))
    with pytest.raises(payment_service.PaymentConflict, match="trip unavailable"):
        payment_service.confirm_payment(db, simulator, payment_id=payment.id, provider_payment_id=payment.provider_payment_id,
            status="approved", signature=simulator.sign_confirmation(payment.id, payment.provider_payment_id, "approved"), now=utc_now())
    assert db.get(Pago, payment.id).status == "rejected"
    assert db.query(Servicio).count() == 0
