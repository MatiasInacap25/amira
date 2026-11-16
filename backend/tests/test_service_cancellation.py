"""Cancellation through public HTTP with persisted financial effects."""
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
import pytest
from sqlalchemy import select, text
from amira_api.clock import utc_now
from amira_api.models import Reembolso
from claim_support import add_approved_payment, add_payout_account, db  # noqa: F401
from test_provider_service_actions import (CUSTOMER_AUTH, EMPLOYED_DRIVER_AUTH, OWNER_AUTH, OUTSIDER_AUTH, call, fleet)  # noqa: F401

@pytest.fixture(autouse=True)
def refunds_table(db):
    Reembolso.__table__.create(db.get_bind(), checkfirst=True)

def database_hash(db):
    """Digest every persisted row, including tables unrelated to the requested command."""
    names = db.scalars(text("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")).all()
    quote = db.get_bind().dialect.identifier_preparer.quote
    rows = [
        (name, sorted(repr(tuple(row)) for row in db.execute(text(f"SELECT * FROM {quote(name)}"))))
        for name in names
    ]
    return sha256(repr(rows).encode()).hexdigest()


def cancel(call, service, role="customer", auth=None):
    return call("POST", f"/api/{role}/services/{service.id}/cancel", as_auth_id=auth or (CUSTOMER_AUTH if role == "customer" else OWNER_AUTH))

@pytest.mark.parametrize("role,refund,retained", [("customer", "135000", "15000"), ("provider", "150000", "0")])
def test_cancel_and_cross_role_replay(call, db, fleet, role, refund, retained):
    payment = add_approved_payment(db, fleet.service_a)
    response = cancel(call, fleet.service_a, role)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled" and body["canCancel"] is False
    summary = body["cancellation"]
    assert summary["cancelledBy"] == role and summary["cancelledAt"]
    assert summary["refundedAmount"] == float(refund) and summary["retainedAmount"] == float(retained)
    assert summary["currency"] == "CLP" and summary["simulated"] is True
    rows = db.scalars(select(Reembolso).where(Reembolso.payment_id == payment.id)).all()
    assert len(rows) == 1 and rows[0].amount == Decimal(refund)
    assert rows[0].status == "approved" and rows[0].confirmed_at is not None
    other = "provider" if role == "customer" else "customer"
    assert cancel(call, fleet.service_a, other).json()["cancellation"] == summary
    assert len(db.scalars(select(Reembolso)).all()) == 1
    db.refresh(fleet.service_a)
    assert fleet.service_a.status == "cancelled" and fleet.service_a.starts_at is None

@pytest.mark.parametrize("status", ["in_progress", "completed", "disputed"])
def test_reject_started_without_mutation(call, db, fleet, status):
    payment = add_approved_payment(db, fleet.service_a)
    fleet.service_a.status = status
    fleet.service_a.starts_at = utc_now()
    db.commit()
    before = database_hash(db)
    assert cancel(call, fleet.service_a).status_code == 409
    assert database_hash(db) == before
    db.refresh(fleet.service_a)
    db.refresh(payment)
    assert fleet.service_a.status == status and payment.status == "approved"
    assert db.scalars(select(Reembolso)).all() == []

@pytest.mark.parametrize("auth,expected", [(EMPLOYED_DRIVER_AUTH, 403), (OUTSIDER_AUTH, 404)])
def test_provider_owner_authorization(call, db, fleet, auth, expected):
    add_approved_payment(db, fleet.service_a)
    before = database_hash(db)
    assert cancel(call, fleet.service_a, "provider", auth).status_code == expected
    assert database_hash(db) == before
    db.refresh(fleet.service_a)
    assert fleet.service_a.status == "confirmed" and db.scalars(select(Reembolso)).all() == []

def test_customer_ownership(call, db, fleet):
    add_approved_payment(db, fleet.service_a)
    fleet.service_a.customer_id = fleet.eli_user.id
    db.commit()
    before = database_hash(db)
    assert cancel(call, fleet.service_a).status_code == 404
    assert database_hash(db) == before
    assert db.scalars(select(Reembolso)).all() == []

@pytest.mark.parametrize("provider", ["real-bank", None])
def test_refund_unavailable_is_unchanged(call, db, fleet, provider):
    if provider:
        payment = add_approved_payment(db, fleet.service_a)
        payment.provider = provider
        db.commit()
    before = database_hash(db)
    assert cancel(call, fleet.service_a).status_code in (409, 503)
    assert database_hash(db) == before
    db.refresh(fleet.service_a)
    assert fleet.service_a.status == "confirmed" and db.scalars(select(Reembolso)).all() == []

def test_decimal_and_zero_amounts(call, db, fleet):
    add_approved_payment(db, fleet.service_a, Decimal("123.4567"))
    response = cancel(call, fleet.service_a)
    assert response.status_code == 200
    assert response.json()["cancellation"]["retainedAmount"] == 12.3457
    assert response.json()["cancellation"]["refundedAmount"] == 111.111
    add_approved_payment(db, fleet.service_next_day, Decimal("0"))
    zero = cancel(call, fleet.service_next_day)
    assert zero.status_code == 200 and zero.json()["cancellation"]["refundedAmount"] == 0
    assert len(db.scalars(select(Reembolso)).all()) == 1

def test_cancelled_cannot_start_or_assign(call, db, fleet):
    add_approved_payment(db, fleet.service_a)
    assert cancel(call, fleet.service_a).status_code == 200
    path = f"/api/provider/services/{fleet.service_a.id}"
    before = database_hash(db)
    assert call("POST", path + "/start", as_auth_id=OWNER_AUTH, json={"latitude": -33.4, "longitude": -70.6}).status_code == 409
    assert call("PUT", path + "/assignments", as_auth_id=OWNER_AUTH, json={"assignments": [{"driverId": str(fleet.eli.id), "vehicleId": str(fleet.van.id)}]}).status_code == 409

    assert database_hash(db) == before


def test_cancelled_service_is_excluded_from_due_payouts(call, db, fleet):
    from amira_api.payout_service import _due_service_ids

    add_approved_payment(db, fleet.service_a)
    add_payout_account(db, fleet.company)
    assert cancel(call, fleet.service_a).status_code == 200
    # Make the other release predicates eligible; the cancelled status must still exclude it.
    fleet.service_a.completed_at = utc_now() - timedelta(days=2)
    fleet.service_a.payout_deadline_at = utc_now() - timedelta(days=1)
    fleet.service_a.customer_consent_at = utc_now()
    db.commit()

    assert fleet.service_a.id not in _due_service_ids(db, utc_now())
