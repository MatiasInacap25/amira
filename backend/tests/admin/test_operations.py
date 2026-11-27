from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from claim_support import add_approved_payment, db  # noqa: F401
from fastapi import HTTPException
from sqlalchemy import select
from test_auth import USER_ID
from test_provider_service_actions import fleet  # noqa: F401

from amira_api.models import AdminAuditLog, Chat, ChatParticipante, Mensaje, Reclamo, Reembolso
from amira_api.settings import Settings


def test_admin_cancels_confirmed_service_with_full_refund_and_audit(db, fleet):
    from amira_api.admin.operations import cancel_admin_service

    for model in (AdminAuditLog, Reembolso):
        model.__table__.create(db.get_bind())
    service = fleet.service_a
    payment = add_approved_payment(db, service, Decimal("80000"))
    cancel_admin_service(db, service.id, UUID(USER_ID), "Authorized administrative cancellation.", Settings(app_env="test"))
    assert service.status == "cancelled"
    assert service.cancelled_by == "admin"
    assert service.cancellation_retained_amount == 0
    assert db.scalar(select(Reembolso).where(Reembolso.payment_id == payment.id)).amount == 80000
    assert db.scalar(select(AdminAuditLog.action)) == "service.cancel"
    with pytest.raises(HTTPException) as raised:
        cancel_admin_service(db, service.id, UUID(USER_ID), "Authorized administrative cancellation.", Settings(app_env="test"))
    assert raised.value.status_code == 409


def test_chat_transcript_requires_claim_or_audited_reason(db, fleet):
    from amira_api.admin.listing import ListFilters, listed
    from amira_api.admin.operations import chats, transcript

    for model in (AdminAuditLog, ChatParticipante, Mensaje):
        model.__table__.create(db.get_bind())
    service = fleet.service_a
    chat = service.accepted_quotation.chat
    db.add(Mensaje(id=uuid4(), chat_id=chat.id, user_id=service.customer_id, content="Confidential message"))
    db.commit()
    params = ListFilters()
    assert "Confidential message" not in repr(listed(db, chats(db, params), params))
    with pytest.raises(HTTPException) as raised:
        transcript(db, chat.id, UUID(USER_ID), None, None, lambda: None, Settings())
    assert raised.value.status_code == 403
    assert db.scalar(select(AdminAuditLog.id)) is None
    data = transcript(db, chat.id, UUID(USER_ID), "Investigating a support report.", None, lambda: None, Settings())
    assert data["items"][0]["text"] == "Confidential message"
    assert db.scalar(select(AdminAuditLog.action)) == "chat.access"
    db.add(Reclamo(id=uuid4(), service_id=service.id, user_id=service.customer_id, reason="Support", status="open"))
    db.commit()
    assert transcript(db, chat.id, UUID(USER_ID), None, None, lambda: None, Settings())["items"][0]["text"] == "Confidential message"


def test_claim_does_not_authorize_a_different_chat_on_same_request(db, fleet):
    from amira_api.admin.operations import transcript

    for model in (AdminAuditLog, ChatParticipante, Mensaje):
        model.__table__.create(db.get_bind())
    service = fleet.service_a
    unrelated = Chat(id=uuid4(), form_id=service.form_id)
    db.add(unrelated)
    db.add(Reclamo(id=uuid4(), service_id=service.id, user_id=service.customer_id, reason="Support", status="open"))
    db.commit()
    with pytest.raises(HTTPException) as denied:
        transcript(db, unrelated.id, UUID(USER_ID), None, None, lambda: None, Settings())
    assert denied.value.status_code == 403


def test_operational_rows_include_links_and_reuse_tax_rules(db, fleet):
    from amira_api.admin.listing import ListFilters, listed
    from amira_api.admin.operations import breakdown, quotations, requests, services

    service = fleet.service_a
    service.accepted_quotation.amount = Decimal("80000")
    db.commit()
    query = ListFilters(request=service.form_id)
    quotation = listed(db, quotations(db, query), query)["items"][0]
    assert quotation["request_id"] == service.form_id
    amounts = breakdown(quotation, Settings())
    assert (amounts["net"], amounts["iva"], amounts["commission"]) == (67227, 12773, 8000)
    records = listed(db, requests(db, ListFilters()), ListFilters())["items"]
    assert any(row["id"] == service.form_id for row in records)
    records = listed(db, services(db, ListFilters()), ListFilters())["items"]
    assert any(row["chat_id"] == service.accepted_quotation.chat_id for row in records)
