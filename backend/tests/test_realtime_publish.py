"""Chat change announcements: the payload builder, the pg_notify publisher, and one publish per committed chat write."""

import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from amira_api import chat_routes, payment_service, quotation_routes
from amira_api.clock import utc_now
from amira_api.models import Cotizacion, Pago
from amira_api.payment_service import PaymentConflict, confirm_payment
from amira_api.realtime import CHAT_EVENTS_CHANNEL, MAX_PAYLOAD_BYTES, ChatEvent, ChatEventKind, publish_chat_event
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

VALID_QUOTATION = {
    "amount": 150000,
    "serviceAt": "2026-10-20T09:00:00-03:00",
    "description": "Mudanza de 2 dormitorios",
    "validityHours": 72,
}


@pytest.fixture
def announcements(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def spy(session, *, chat_id, kind, ref_id):
        calls.append({"chat_id": chat_id, "kind": kind, "ref_id": ref_id})

    for module in (chat_routes, quotation_routes, payment_service):
        monkeypatch.setattr(module, "publish_chat_event", spy)
    return calls


# Payload builder


def test_message_payload_names_the_message_chat_and_recipients_without_content():
    chat_id, message_id, customer, provider = uuid4(), uuid4(), uuid4(), uuid4()

    payload = json.loads(ChatEvent(ChatEventKind.MESSAGE_CREATED, chat_id, message_id, (customer, provider)).to_payload())

    assert payload == {
        "kind": "message.created",
        "chatId": str(chat_id),
        "messageId": str(message_id),
        "recipients": [str(customer), str(provider)],
    }


def test_quotation_payload_names_the_quotation_and_never_carries_message_text():
    chat_id, quotation_id = uuid4(), uuid4()

    payload = json.loads(
        ChatEvent(ChatEventKind.QUOTATION_CHANGED, chat_id, quotation_id, (uuid4(), uuid4())).to_payload()
    )

    assert payload["kind"] == "quotation.changed"
    assert payload["quotationId"] == str(quotation_id)
    assert "messageId" not in payload
    assert set(payload) == {"kind", "chatId", "quotationId", "recipients"}


def test_payload_stays_well_under_the_pg_notify_limit():
    event = ChatEvent(ChatEventKind.QUOTATION_CHANGED, uuid4(), uuid4(), (uuid4(), uuid4()))

    assert len(event.to_payload().encode()) < MAX_PAYLOAD_BYTES
    assert MAX_PAYLOAD_BYTES == 8000


# Publisher


def test_publish_notifies_the_channel_with_both_participants_on_the_same_session(db: Session, scenario: Scenario):
    message_id = uuid4()

    publish_chat_event(db, chat_id=scenario.chat_a.id, kind="message.created", ref_id=message_id)

    [(channel, raw_payload)] = db.info["notifications"]
    payload = json.loads(raw_payload)
    assert channel == CHAT_EVENTS_CHANNEL == "amira_chat_events"
    assert payload["messageId"] == str(message_id)
    assert set(payload["recipients"]) == {str(scenario.customer.id), str(scenario.provider_owner.id)}


def test_publish_never_targets_users_outside_the_chat(db: Session, scenario: Scenario):
    publish_chat_event(db, chat_id=scenario.chat_c.id, kind="quotation.changed", ref_id=uuid4())

    [(_, raw_payload)] = db.info["notifications"]
    recipients = set(json.loads(raw_payload)["recipients"])
    assert recipients == {str(scenario.customer.id), str(scenario.driver_owner.id)}
    assert str(scenario.other_customer.id) not in recipients


def test_publish_for_a_chat_without_participants_announces_nothing(db: Session):
    publish_chat_event(db, chat_id=uuid4(), kind="message.created", ref_id=uuid4())

    assert db.info["notifications"] == []


def test_publish_rejects_an_unknown_kind(db: Session, scenario: Scenario):
    with pytest.raises(ValueError):
        publish_chat_event(db, chat_id=scenario.chat_a.id, kind="message.deleted", ref_id=uuid4())


# Message write


def test_sending_a_message_publishes_message_created_for_the_new_message(api, scenario, announcements):
    response = api(f"/api/chats/{scenario.chat_a.id}/messages", as_auth_id=CUSTOMER_AUTH, method="POST", json={"content": "Hola"})

    assert response.status_code == 201
    assert announcements == [
        {"chat_id": scenario.chat_a.id, "kind": "message.created", "ref_id": UUID(response.json()["messageId"])}
    ]


def test_blocked_contact_details_publish_nothing(api, scenario, announcements):
    response = api(
        f"/api/chats/{scenario.chat_a.id}/messages",
        as_auth_id=CUSTOMER_AUTH,
        method="POST",
        json={"content": "escríbeme a casey.customer@example.test"},
    )

    assert response.status_code == 422
    assert announcements == []


def test_non_participant_message_publishes_nothing(api, scenario, announcements):
    response = api(f"/api/chats/{scenario.chat_c.id}/messages", as_auth_id=OTHER_CUSTOMER_AUTH, method="POST", json={"content": "Hola"})

    assert response.status_code == 404
    assert announcements == []


# Quotation writes


def _create_quotation(api, scenario: Scenario, *, auth=PROVIDER_AUTH, body=None):
    return api(
        f"/api/chats/{scenario.chat_a.id}/quotations",
        as_auth_id=auth,
        method="POST",
        json=body if body is not None else VALID_QUOTATION,
    )


def test_new_quotation_publishes_quotation_changed(api, scenario, announcements):
    response = _create_quotation(api, scenario)

    assert response.status_code == 201
    assert announcements == [
        {"chat_id": scenario.chat_a.id, "kind": "quotation.changed", "ref_id": UUID(response.json()["quotationId"])}
    ]


def test_superseding_a_pending_quotation_announces_both_quotations(api, scenario, announcements):
    first = _create_quotation(api, scenario).json()["quotationId"]
    announcements.clear()

    second = _create_quotation(api, scenario, body={**VALID_QUOTATION, "amount": 99000}).json()["quotationId"]

    assert {call["ref_id"] for call in announcements} == {UUID(first), UUID(second)}
    assert all(call["kind"] == "quotation.changed" for call in announcements)


def test_customer_cannot_create_a_quotation_and_publishes_nothing(api, scenario, announcements):
    response = _create_quotation(api, scenario, auth=CUSTOMER_AUTH)

    assert response.status_code == 403
    assert announcements == []


def test_quotation_on_a_settled_chat_is_a_conflict_and_publishes_nothing(api, scenario, db: Session, announcements):
    created = _create_quotation(api, scenario).json()
    db.get(Cotizacion, UUID(created["quotationId"])).status = "paid"
    db.commit()
    announcements.clear()

    response = _create_quotation(api, scenario, body={**VALID_QUOTATION, "amount": 99000})

    assert response.status_code == 409
    assert announcements == []


def test_customer_rejection_publishes_quotation_changed(api, scenario, announcements):
    quotation_id = _create_quotation(api, scenario).json()["quotationId"]
    announcements.clear()

    response = api(f"/api/quotations/{quotation_id}/reject", as_auth_id=CUSTOMER_AUTH, method="POST")

    assert response.status_code == 200
    assert announcements == [{"chat_id": scenario.chat_a.id, "kind": "quotation.changed", "ref_id": UUID(quotation_id)}]


def test_provider_cannot_reject_and_publishes_nothing(api, scenario, announcements):
    quotation_id = _create_quotation(api, scenario).json()["quotationId"]
    announcements.clear()

    response = api(f"/api/quotations/{quotation_id}/reject", as_auth_id=PROVIDER_AUTH, method="POST")

    assert response.status_code == 403
    assert announcements == []


def test_rejecting_twice_is_a_conflict_and_publishes_nothing(api, scenario, announcements):
    quotation_id = _create_quotation(api, scenario).json()["quotationId"]
    api(f"/api/quotations/{quotation_id}/reject", as_auth_id=CUSTOMER_AUTH, method="POST")
    announcements.clear()

    response = api(f"/api/quotations/{quotation_id}/reject", as_auth_id=CUSTOMER_AUTH, method="POST")

    assert response.status_code == 409
    assert announcements == []


# Payment confirmation


class _Provider:
    name = "external"

    def verify_confirmation(self, *_args) -> bool:
        return True


def _pending_payment(db: Session, scenario: Scenario, *, validity: timedelta = timedelta(days=7)) -> tuple[Cotizacion, Pago]:
    now = utc_now()
    created = now - timedelta(days=4)
    quotation = Cotizacion(
        id=uuid4(),
        chat_id=scenario.chat_a.id,
        status="pending",
        amount=150000,
        currency="CLP",
        origin="Santiago",
        destination="Valparaíso",
        service_type_id=scenario.chat_a.form.service_type_id,
        service_at=now + timedelta(days=5),
        description="Mudanza",
        created_at=created,
        expires_at=created + validity,
        is_exclusive=False,
    )
    payment = Pago(
        id=uuid4(),
        quotation_id=quotation.id,
        provider="external",
        provider_payment_id=f"ext_{uuid4().hex}",
        idempotency_key=f"quotation:{quotation.id}:attempt:1",
        amount=quotation.amount,
        currency="CLP",
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add_all([quotation, payment])
    db.commit()
    return quotation, payment


def _confirm(db: Session, payment: Pago, status: str):
    return confirm_payment(
        db,
        _Provider(),
        payment_id=payment.id,
        provider_payment_id=payment.provider_payment_id,
        status=status,
        signature="signed",
        now=utc_now(),
    )


def test_approved_payment_publishes_the_paid_quotation(db: Session, scenario: Scenario, announcements):
    quotation, payment = _pending_payment(db, scenario)

    _confirm(db, payment, "approved")

    assert announcements == [{"chat_id": scenario.chat_a.id, "kind": "quotation.changed", "ref_id": quotation.id}]


def test_rejected_payment_publishes_nothing_because_the_quotation_is_unchanged(db: Session, scenario: Scenario, announcements):
    _, payment = _pending_payment(db, scenario)

    _confirm(db, payment, "rejected")

    assert announcements == []


def test_payment_on_a_closed_quotation_is_a_conflict_and_publishes_nothing(db: Session, scenario: Scenario, announcements):
    _, payment = _pending_payment(db, scenario, validity=timedelta(days=1))

    with pytest.raises(PaymentConflict):
        _confirm(db, payment, "approved")

    assert announcements == []
