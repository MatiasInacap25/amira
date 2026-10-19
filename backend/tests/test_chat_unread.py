"""Unread counts: per-chat counts on the list, the unread total, and marking a chat read."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.clock import utc_now
from amira_api.models import ChatParticipante, Mensaje
from chat_support import (
    CUSTOMER_AUTH,
    DRIVER_AUTH,
    OTHER_CUSTOMER_AUTH,
    PROVIDER_AUTH,
    UNKNOWN_AUTH,
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


def _items_by_chat(api, auth_id) -> dict[str, dict]:
    return {item["chatId"]: item for item in api("/api/chats", as_auth_id=auth_id).json()["items"]}


def _send(api, chat_id, auth_id, content: str = "Hola"):
    response = api(f"/api/chats/{chat_id}/messages", as_auth_id=auth_id, method="POST", json={"content": content})
    assert response.status_code == 201
    return response


def _last_read_at(db: Session, chat_id: UUID, user_id: UUID) -> datetime:
    row = db.execute(
        select(ChatParticipante.last_read_at).where(
            ChatParticipante.chat_id == chat_id, ChatParticipante.user_id == user_id
        )
    ).scalar_one()
    return row if row.tzinfo else row.replace(tzinfo=timezone.utc)


def test_list_items_carry_an_unread_count_for_every_chat(api, scenario):
    items = _items_by_chat(api, CUSTOMER_AUTH)

    assert set(items) == {str(scenario.chat_c.id), str(scenario.chat_a.id)}
    for item in items.values():
        assert isinstance(item["unreadCount"], int)


def test_unread_counts_only_the_other_participants_messages_after_last_read(api, scenario):
    # Seeded: Pat (provider) sent one message in chat_a after the fixed read time; Casey sent one too.
    assert _items_by_chat(api, CUSTOMER_AUTH)[str(scenario.chat_a.id)]["unreadCount"] == 1
    assert _items_by_chat(api, PROVIDER_AUTH)[str(scenario.chat_a.id)]["unreadCount"] == 1


def test_own_messages_never_count_as_unread(api, scenario):
    _send(api, scenario.chat_c.id, CUSTOMER_AUTH)
    _send(api, scenario.chat_c.id, CUSTOMER_AUTH)

    assert _items_by_chat(api, CUSTOMER_AUTH)[str(scenario.chat_c.id)]["unreadCount"] == 0
    assert _items_by_chat(api, DRIVER_AUTH)[str(scenario.chat_c.id)]["unreadCount"] == 2


def test_quotations_do_not_count_as_unread_messages(api, scenario):
    before = _items_by_chat(api, CUSTOMER_AUTH)[str(scenario.chat_a.id)]["unreadCount"]

    response = api(f"/api/chats/{scenario.chat_a.id}/quotations", as_auth_id=PROVIDER_AUTH, method="POST", json=VALID_QUOTATION)

    assert response.status_code == 201
    assert _items_by_chat(api, CUSTOMER_AUTH)[str(scenario.chat_a.id)]["unreadCount"] == before


def test_messages_sent_after_a_read_count_again(api, scenario, db: Session):
    api(f"/api/chats/{scenario.chat_c.id}/read", as_auth_id=CUSTOMER_AUTH, method="POST")
    # Stored a minute after the read: the SQLite fixture's clock has one-second resolution, so a message sent in
    # the same second as the read could not be told apart from it.
    db.add(Mensaje(id=uuid4(), chat_id=scenario.chat_c.id, user_id=scenario.driver_owner.id, content="Después",
                   created_at=utc_now() + timedelta(minutes=1)))
    db.commit()

    assert _items_by_chat(api, CUSTOMER_AUTH)[str(scenario.chat_c.id)]["unreadCount"] == 1


def test_marking_a_chat_read_sets_its_count_to_zero_for_the_reader_only(api, scenario):
    response = api(f"/api/chats/{scenario.chat_a.id}/read", as_auth_id=CUSTOMER_AUTH, method="POST")

    assert response.status_code == 204
    assert response.content == b""
    assert _items_by_chat(api, CUSTOMER_AUTH)[str(scenario.chat_a.id)]["unreadCount"] == 0
    assert _items_by_chat(api, PROVIDER_AUTH)[str(scenario.chat_a.id)]["unreadCount"] == 1


def test_marking_read_never_moves_the_last_read_time_backwards(api, scenario, db: Session):
    future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    participant = db.execute(
        select(ChatParticipante).where(
            ChatParticipante.chat_id == scenario.chat_a.id, ChatParticipante.user_id == scenario.customer.id
        )
    ).scalar_one()
    participant.last_read_at = future
    db.commit()

    response = api(f"/api/chats/{scenario.chat_a.id}/read", as_auth_id=CUSTOMER_AUTH, method="POST")

    assert response.status_code == 204
    assert _last_read_at(db, scenario.chat_a.id, scenario.customer.id) == future


def test_marking_read_moves_the_last_read_time_forward(api, scenario, db: Session):
    before = _last_read_at(db, scenario.chat_a.id, scenario.customer.id)

    api(f"/api/chats/{scenario.chat_a.id}/read", as_auth_id=CUSTOMER_AUTH, method="POST")

    assert _last_read_at(db, scenario.chat_a.id, scenario.customer.id) > before


def test_non_participant_cannot_mark_a_chat_read_and_gets_not_found(api, scenario, db: Session):
    response = api(f"/api/chats/{scenario.chat_a.id}/read", as_auth_id=OTHER_CUSTOMER_AUTH, method="POST")

    assert response.status_code == 404
    assert _last_read_at(db, scenario.chat_a.id, scenario.customer.id) == datetime(2026, 9, 30, tzinfo=timezone.utc)


def test_unknown_chat_and_unknown_account_get_the_same_not_found_when_marking_read(api, scenario):
    unknown_chat = api(f"/api/chats/{uuid4()}/read", as_auth_id=CUSTOMER_AUTH, method="POST")
    unknown_account = api(f"/api/chats/{scenario.chat_a.id}/read", as_auth_id=UNKNOWN_AUTH, method="POST")

    assert unknown_chat.status_code == 404
    assert unknown_account.status_code == 404
    assert unknown_chat.json() == unknown_account.json()


def test_unread_total_sums_the_counts_across_the_callers_chats(api, scenario):
    _send(api, scenario.chat_c.id, DRIVER_AUTH)
    _send(api, scenario.chat_c.id, DRIVER_AUTH)

    response = api("/api/chats/unread", as_auth_id=CUSTOMER_AUTH)

    # One from Pat in chat_a and two from Dana in chat_c.
    assert response.status_code == 200
    assert response.json() == {"total": 3}


def test_unread_total_excludes_chats_the_caller_is_not_in(api, scenario):
    _send(api, scenario.chat_d.id, DRIVER_AUTH)
    _send(api, scenario.chat_b.id, PROVIDER_AUTH)

    assert api("/api/chats/unread", as_auth_id=CUSTOMER_AUTH).json() == {"total": 1}


def test_unread_total_is_zero_for_an_account_without_chats(api, scenario):
    response = api("/api/chats/unread", as_auth_id=UNKNOWN_AUTH)

    assert response.status_code == 200
    assert response.json() == {"total": 0}


def test_unread_total_drops_to_zero_after_marking_every_chat_read(api, scenario):
    api(f"/api/chats/{scenario.chat_a.id}/read", as_auth_id=CUSTOMER_AUTH, method="POST")

    assert api("/api/chats/unread", as_auth_id=CUSTOMER_AUTH).json() == {"total": 0}


def test_unread_messages_are_counted_from_the_database_not_from_the_list_page(api, scenario, db: Session):
    # A message stored directly still counts, so the count is the stored state and not a cache of the list.
    db.add(Mensaje(id=uuid4(), chat_id=scenario.chat_c.id, user_id=scenario.driver_owner.id, content="Directo",
                   created_at=datetime(2026, 10, 5, tzinfo=timezone.utc)))
    db.commit()

    assert _items_by_chat(api, CUSTOMER_AUTH)[str(scenario.chat_c.id)]["unreadCount"] == 1
