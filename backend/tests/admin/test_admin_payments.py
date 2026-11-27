from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from claim_support import add_approved_payment, add_payout_account, complete, db  # noqa: F401
from fastapi import HTTPException
from sqlalchemy import select
from test_auth import USER_ID
from test_provider_service_actions import fleet  # noqa: F401

from amira_api.models import AdminAuditLog, Desembolso, Reembolso
from amira_api.settings import Settings


def test_admin_refund_calls_canonical_cancellation_and_audits(db, fleet):
    from amira_api.admin.transactions import refund_payment

    for model in (AdminAuditLog, Reembolso):
        model.__table__.create(db.get_bind())
    service = fleet.service_a
    payment = add_approved_payment(db, service, Decimal("80000"))
    refund_payment(db, payment.id, UUID(USER_ID), "Refund approved after verification.", Settings(app_env="test"))
    assert db.scalar(select(Reembolso.amount)) == 80000
    assert service.cancellation_retained_amount == 0
    assert db.scalar(select(AdminAuditLog.action)) == "service.cancel"
    assert payment.status == "approved"


def test_admin_batch_release_audits_exactly_once_and_refuses_unsafe_environment(db, fleet):
    from amira_api.admin.transactions import release_admin_payouts

    AdminAuditLog.__table__.create(db.get_bind())
    service = fleet.service_a
    complete(db, service, deadline_in=timedelta(minutes=-1))
    add_approved_payment(db, service, Decimal("80000"))
    add_payout_account(db, service.provider_profile)
    with pytest.raises(HTTPException) as refused:
        release_admin_payouts(db, UUID(USER_ID), Settings())
    assert refused.value.status_code == 503
    first = release_admin_payouts(db, UUID(USER_ID), Settings(app_env="test"))
    assert first.released == 1
    assert db.scalar(select(Desembolso.net_amount)) == 72000
    assert db.scalar(select(AdminAuditLog.action)) == "payout.release"
    second = release_admin_payouts(db, UUID(USER_ID), Settings(app_env="test"))
    assert second.released == 0
    assert len(db.scalars(select(AdminAuditLog)).all()) == 1


def test_paid_breakdown_and_receipt_use_actual_payout_and_escape_names(db, fleet):
    from amira_api.admin.transactions import payout_receipt, release_admin_payouts

    AdminAuditLog.__table__.create(db.get_bind())
    service = fleet.service_a
    service.provider_profile.name = "<Transportista>"
    complete(db, service, deadline_in=timedelta(minutes=-1))
    add_approved_payment(db, service, Decimal("80000"))
    add_payout_account(db, service.provider_profile)
    settings = Settings(app_env="test")
    assert release_admin_payouts(db, UUID(USER_ID), settings).released == 1
    receipt = payout_receipt(db, db.scalar(select(Desembolso.id)), settings)
    assert "&lt;Transportista&gt;" in receipt
    assert "<Transportista>" not in receipt
    assert "72000" in receipt
    assert "1277" in receipt
