from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from claim_support import add_approved_payment, db  # noqa: F401
from fastapi import HTTPException
from sqlalchemy import select
from test_auth import USER_ID
from test_provider_service_actions import fleet  # noqa: F401

from amira_api.models import AdminAuditLog, Reclamo, Reembolso
from amira_api.settings import Settings


def test_customer_claim_refunds_and_prevents_replay(db, fleet):
    from amira_api.admin.claim_service import resolve_claim

    for model in (AdminAuditLog, Reembolso):
        model.__table__.create(db.get_bind())
    service = fleet.service_a
    payment = add_approved_payment(db, service, Decimal("80000"))
    service.status = "disputed"
    claim = Reclamo(id=uuid4(), service_id=service.id, user_id=service.customer_id, reason="Customer report", status="open")
    db.add(claim)
    db.commit()
    resolve_claim(db, claim.id, UUID(USER_ID), "customer", "Resolved after review.", Settings(app_env="test"))
    refund = db.scalar(select(Reembolso).where(Reembolso.payment_id == payment.id))
    assert service.status == "cancelled"
    assert refund.amount == 80000
    assert refund.claim_id == claim.id
    assert claim.resolution == "customer"
    assert db.scalar(select(AdminAuditLog.action)) == "claim.resolve_customer"
    with pytest.raises(HTTPException) as repeated:
        resolve_claim(db, claim.id, UUID(USER_ID), "customer", "Repeated resolution.", Settings(app_env="test"))
    assert repeated.value.status_code == 409


def test_bank_approval_requires_same_holder_identity(db, fleet):
    from amira_api.admin.review import review_action
    from claim_support import add_payout_account

    AdminAuditLog.__table__.create(db.get_bind())
    account = add_payout_account(db, fleet.service_a.provider_profile, enabled=False)
    account.registration_status = "pending"
    db.commit()
    with pytest.raises(HTTPException) as mismatch:
        review_action(db, "bank-accounts", account.id, UUID(USER_ID), "approve", None)
    assert mismatch.value.status_code == 409
    assert account.payouts_enabled is False
    assert db.scalar(select(AdminAuditLog.id)) is None


def test_document_rejection_reuses_cli_and_audits_once(db, fleet):
    from amira_api.admin.review import review_action
    from amira_api.models import VerificacionIdentidad

    AdminAuditLog.__table__.create(db.get_bind())
    document = VerificacionIdentidad(
        id=uuid4(), user_id=fleet.service_a.customer_id, provider="verifik", provider_verification_id="folio",
        status="in_review", document_type="driver_record",
    )
    db.add(document)
    db.commit()
    with pytest.raises(HTTPException) as invalid:
        review_action(db, "documents", document.id, UUID(USER_ID), "reject", "corto")
    assert invalid.value.status_code == 422
    review_action(db, "documents", document.id, UUID(USER_ID), "reject", "El certificado está incompleto.")
    assert document.status == "rejected"
    assert document.reviewed_by == UUID(USER_ID)
    assert db.scalar(select(AdminAuditLog.action)) == "verification.reject"
    with pytest.raises(HTTPException) as repeated:
        review_action(db, "documents", document.id, UUID(USER_ID), "approve", None)
    assert repeated.value.status_code == 409


def test_provider_claim_reenters_normal_due_rules_without_refund(db, fleet):
    from datetime import timedelta

    from amira_api.admin.claim_service import resolve_claim
    from amira_api.clock import utc_now
    from amira_api.payout_service import _due_service_ids

    for model in (AdminAuditLog, Reembolso):
        model.__table__.create(db.get_bind())
    now = utc_now()
    service = fleet.service_a
    service.status, service.completed_at, service.payout_deadline_at = "disputed", now, now - timedelta(hours=1)
    claim = Reclamo(id=uuid4(), service_id=service.id, user_id=service.customer_id, reason="Customer report", status="open")
    db.add(claim)
    db.commit()
    resolve_claim(db, claim.id, UUID(USER_ID), "provider", "Resolved after review.", Settings())
    assert claim.resolution == "provider"
    assert service.id in _due_service_ids(db, now)
    assert db.scalar(select(Reembolso.id)) is None


def test_bank_listing_never_returns_raw_account_number(db, fleet):
    from amira_api.admin.listing import ListFilters, listed
    from amira_api.admin.review import bank_accounts
    from claim_support import add_payout_account

    account = add_payout_account(db, fleet.service_a.provider_profile, enabled=False)
    account.account_number = "1234569876"
    db.commit()
    params = ListFilters()
    rows = listed(db, bank_accounts(db, params), params)["items"]
    assert rows[0]["masked_number"] == "****9876"
    assert "1234569876" not in repr(rows)
