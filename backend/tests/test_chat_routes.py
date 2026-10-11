"""Chat list and chat message routes, exercised against in-memory SQLite with the real ORM queries.

Postgres-only CHECK constraints (regex `~`) are not emitted for the two lookup tables, which are created
with plain DDL. Everything else comes from the ORM metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from amira_api.models import Mensaje
from chat_support import (
    CUSTOMER_AUTH,
    DRIVER_AUTH,
    OTHER_CUSTOMER_AUTH,
    PROVIDER_AUTH,
    SECRET_CONTACT_VALUES,
    UNKNOWN_AUTH,
    Scenario,
    api,
    db,
    scenario,
)


def test_chat_list_contains_only_caller_chats_ordered_by_last_activity(api, scenario):
    response = api("/api/chats", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    body = response.json()
    # chat_c was created on 10-03; chat_a's last activity is the provider's 10-01 11:00 message.
    assert [item["chatId"] for item in body["items"]] == [str(scenario.chat_c.id), str(scenario.chat_a.id)]
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_customer_counterpart_is_provider_public_name_and_kind(api, scenario):
    items = {item["chatId"]: item for item in api("/api/chats", as_auth_id=CUSTOMER_AUTH).json()["items"]}

    company_chat = items[str(scenario.chat_a.id)]
    assert company_chat["counterpart"] == {
        "name": "Transportes Norte",
        "kind": "company",
        "providerProfileId": str(scenario.provider_profile.id),
    }
    assert company_chat["serviceName"] == "Mudanzas"
    assert company_chat["originCommuneName"] == "Santiago"
    assert company_chat["destinationCommuneName"] == "Valparaíso"
    assert company_chat["requestId"] is not None
    assert company_chat["createdAt"].startswith("2026-10-01")

    driver_chat = items[str(scenario.chat_c.id)]
    assert driver_chat["counterpart"] == {
        "name": "Dana Driver Fletes",
        "kind": "independent_driver",
        "providerProfileId": str(scenario.driver_profile.id),
    }
    assert driver_chat["destinationCommuneName"] is None


def test_provider_counterpart_is_customer_full_name_without_profile_id(api, scenario):
    items = {item["chatId"]: item for item in api("/api/chats", as_auth_id=PROVIDER_AUTH).json()["items"]}

    assert set(items) == {str(scenario.chat_b.id), str(scenario.chat_a.id)}
    assert items[str(scenario.chat_a.id)]["counterpart"] == {
        "name": "Casey Customer",
        "kind": "customer",
        "providerProfileId": None,
    }
    assert items[str(scenario.chat_b.id)]["counterpart"]["name"] == "Xavi Other"


def test_last_message_is_truncated_and_marks_whether_caller_sent_it(api, scenario):
    provider_view = {item["chatId"]: item for item in api("/api/chats", as_auth_id=PROVIDER_AUTH).json()["items"]}
    customer_view = {item["chatId"]: item for item in api("/api/chats", as_auth_id=CUSTOMER_AUTH).json()["items"]}

    provider_last = provider_view[str(scenario.chat_a.id)]["lastMessage"]
    assert provider_last["content"] == "x" * 140
    assert provider_last["fromMe"] is True
    assert provider_last["sentAt"].startswith("2026-10-01T11:00")

    customer_last = customer_view[str(scenario.chat_a.id)]["lastMessage"]
    assert customer_last["fromMe"] is False
    assert provider_view[str(scenario.chat_b.id)]["lastMessage"] is None


def test_chat_without_messages_is_ordered_by_creation_and_has_null_last_message(api, scenario):
    items = api("/api/chats", as_auth_id=PROVIDER_AUTH).json()["items"]

    # chat_b (created 10-02) sorts ahead of chat_a (last message 10-01 11:00).
    assert [item["chatId"] for item in items] == [str(scenario.chat_b.id), str(scenario.chat_a.id)]
    assert items[0]["lastMessage"] is None


def test_chat_list_never_exposes_contact_or_auth_details(api, scenario):
    for auth_id in (CUSTOMER_AUTH, PROVIDER_AUTH, DRIVER_AUTH):
        response = api("/api/chats", as_auth_id=auth_id)
        assert response.status_code == 200
        text_body = response.text
        for value in SECRET_CONTACT_VALUES:
            assert value not in text_body
        assert str(scenario.customer.auth_user_id) not in text_body
        assert str(scenario.provider_owner.auth_user_id) not in text_body
        assert "email" not in text_body.lower()
        assert "phone" not in text_body.lower()


def test_total_and_items_come_from_the_same_filtered_relation(api, scenario):
    first = api("/api/chats?limit=1&offset=0", as_auth_id=CUSTOMER_AUTH).json()
    second = api("/api/chats?limit=1&offset=1", as_auth_id=CUSTOMER_AUTH).json()

    assert first["total"] == second["total"] == 2
    assert [item["chatId"] for item in first["items"]] == [str(scenario.chat_c.id)]
    assert [item["chatId"] for item in second["items"]] == [str(scenario.chat_a.id)]


def test_caller_without_chats_or_account_gets_an_empty_page(api, scenario):
    unknown = api("/api/chats", as_auth_id=UNKNOWN_AUTH).json()
    assert unknown == {"items": [], "total": 0, "limit": 20, "offset": 0}


@pytest.mark.parametrize("query", ["limit=0", "limit=51", "offset=-1", "offset=5001"])
def test_page_bounds_are_validated(api, scenario, query):
    assert api(f"/api/chats?{query}", as_auth_id=CUSTOMER_AUTH).status_code == 422


def _messages_path(chat_id: UUID, query: str = "") -> str:
    return f"/api/chats/{chat_id}/messages{query}"


def _add_customer_messages(db: Session, scenario: Scenario, timestamps: list[datetime]) -> None:
    db.add_all([
        Mensaje(id=uuid4(), chat_id=scenario.chat_a.id, user_id=scenario.customer.id, content=f"extra {index}",
                created_at=stamp)
        for index, stamp in enumerate(timestamps)
    ])
    db.commit()


def test_participant_gets_header_and_all_messages_oldest_to_newest(api, scenario):
    response = api(_messages_path(scenario.chat_a.id), as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["chatId"] == str(scenario.chat_a.id)
    assert body["serviceName"] == "Mudanzas"
    assert body["counterpart"] == {
        "name": "Transportes Norte",
        "kind": "company",
        "providerProfileId": str(scenario.provider_profile.id),
    }
    assert "lastMessage" not in body
    assert body["nextBefore"] is None
    assert [message["content"] for message in body["timeline"]] == ["Hola, ¿a qué hora llegan?", "x" * 200]
    assert body["timeline"][0]["messageId"] is not None
    assert body["timeline"][0]["sentAt"].startswith("2026-10-01T10:05")


def test_messages_are_marked_from_me_with_sender_names_per_side(api, scenario):
    customer_view = api(_messages_path(scenario.chat_a.id), as_auth_id=CUSTOMER_AUTH).json()["timeline"]
    provider_view = api(_messages_path(scenario.chat_a.id), as_auth_id=PROVIDER_AUTH).json()["timeline"]

    assert [message["fromMe"] for message in customer_view] == [True, False]
    assert [message["fromMe"] for message in provider_view] == [False, True]
    # A customer sees the provider's public name, never the owner's personal name.
    assert customer_view[1]["senderName"] == "Transportes Norte"
    assert customer_view[0]["senderName"] == "Casey Customer"
    assert provider_view[0]["senderName"] == "Casey Customer"
    assert provider_view[1]["senderName"] == "Pat Provider"


def test_chat_with_no_messages_returns_empty_list(api, scenario):
    body = api(_messages_path(scenario.chat_b.id), as_auth_id=PROVIDER_AUTH).json()

    assert body["timeline"] == []
    assert body["nextBefore"] is None


def test_non_participant_and_unknown_chat_both_return_the_same_not_found(api, scenario):
    # Positive control: the same chat is readable by its participant, so the 404s below are not a missing route.
    assert api(_messages_path(scenario.chat_c.id), as_auth_id=CUSTOMER_AUTH).status_code == 200
    other = api(_messages_path(scenario.chat_c.id), as_auth_id=OTHER_CUSTOMER_AUTH)
    provider_outsider = api(_messages_path(scenario.chat_c.id), as_auth_id=PROVIDER_AUTH)
    unknown = api(_messages_path(uuid4()), as_auth_id=CUSTOMER_AUTH)

    assert other.status_code == provider_outsider.status_code == unknown.status_code == 404
    assert other.json() == unknown.json() == provider_outsider.json()


def test_unknown_account_gets_not_found(api, scenario):
    assert api(_messages_path(scenario.chat_a.id), as_auth_id=CUSTOMER_AUTH).status_code == 200
    assert api(_messages_path(scenario.chat_a.id), as_auth_id=UNKNOWN_AUTH).status_code == 404


def test_cursor_pagination_walks_every_message_once_newest_page_first(api, scenario, db):
    _add_customer_messages(db, scenario, [
        datetime(2026, 10, 1, 11, 10, tzinfo=timezone.utc),
        datetime(2026, 10, 1, 11, 20, tzinfo=timezone.utc),
        datetime(2026, 10, 1, 11, 30, tzinfo=timezone.utc),
    ])

    first = api(_messages_path(scenario.chat_a.id, "?limit=2"), as_auth_id=CUSTOMER_AUTH).json()
    assert first["nextBefore"] is not None
    assert [message["content"] for message in first["timeline"]] == ["extra 1", "extra 2"]

    collected = list(first["timeline"])
    page = first
    while page["nextBefore"] is not None:
        page = api(
            _messages_path(scenario.chat_a.id, "?limit=2&before=" + quote(page["nextBefore"], safe="")),
            as_auth_id=CUSTOMER_AUTH,
        ).json()
        collected = page["timeline"] + collected

    assert [message["content"] for message in collected] == [
        "Hola, ¿a qué hora llegan?",
        "x" * 200,
        "extra 0",
        "extra 1",
        "extra 2",
    ]


def test_messages_sharing_a_timestamp_are_never_skipped_across_pages(api, scenario, db):
    same_moment = datetime(2026, 10, 1, 11, 40, tzinfo=timezone.utc)
    _add_customer_messages(db, scenario, [same_moment, same_moment, same_moment, same_moment])

    page = api(_messages_path(scenario.chat_a.id, "?limit=2"), as_auth_id=CUSTOMER_AUTH).json()
    collected = list(page["timeline"])
    while page["nextBefore"] is not None:
        page = api(
            _messages_path(scenario.chat_a.id, "?limit=2&before=" + quote(page["nextBefore"], safe="")),
            as_auth_id=CUSTOMER_AUTH,
        ).json()
        collected = page["timeline"] + collected

    contents = [message["content"] for message in collected]
    # Ties share one created_at, so their relative order is by id; only the set is asserted.
    assert sorted(contents) == sorted([
        "Hola, ¿a qué hora llegan?",
        "x" * 200,
        "extra 0",
        "extra 1",
        "extra 2",
        "extra 3",
    ])


def test_messages_response_names_the_viewer_role(api, scenario):
    customer = api(_messages_path(scenario.chat_a.id), as_auth_id=CUSTOMER_AUTH).json()
    provider = api(_messages_path(scenario.chat_a.id), as_auth_id=PROVIDER_AUTH).json()

    assert customer["viewerRole"] == "customer"
    assert provider["viewerRole"] == "provider"


def test_timeline_entries_are_flat_message_entries_with_kind(api, scenario):
    entry = api(_messages_path(scenario.chat_a.id), as_auth_id=CUSTOMER_AUTH).json()["timeline"][0]

    assert entry["kind"] == "message"
    assert set(entry) == {"kind", "messageId", "content", "sentAt", "fromMe", "senderName"}


def test_customer_can_send_a_message_and_it_is_returned_in_the_timeline(api, scenario):
    response = api(
        _messages_path(scenario.chat_a.id),
        as_auth_id=CUSTOMER_AUTH,
        method="POST",
        json={"content": "  Llegamos a las 10:30  "},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "Llegamos a las 10:30"
    assert body["fromMe"] is True
    assert body["senderName"] == "Casey Customer"
    assert body["messageId"] is not None

    timeline = api(_messages_path(scenario.chat_a.id), as_auth_id=PROVIDER_AUTH).json()["timeline"]
    assert timeline[-1]["messageId"] == body["messageId"]
    assert timeline[-1]["fromMe"] is False
    assert timeline[-1]["senderName"] == "Casey Customer"


def test_provider_message_uses_the_owner_name_as_sender(api, scenario):
    body = api(
        _messages_path(scenario.chat_a.id),
        as_auth_id=PROVIDER_AUTH,
        method="POST",
        json={"content": "Confirmado"},
    ).json()

    assert body["senderName"] == "Pat Provider"
    assert body["fromMe"] is True


@pytest.mark.parametrize("content", [pytest.param("", id="empty"), pytest.param("   ", id="blank"), pytest.param("x" * 2001, id="too-long")])
def test_message_content_must_be_between_one_and_2000_characters_after_trim(api, scenario, content):
    response = api(_messages_path(scenario.chat_a.id), as_auth_id=CUSTOMER_AUTH, method="POST", json={"content": content})

    assert response.status_code == 422


def test_message_with_contact_details_is_rejected_with_a_spanish_reason_and_not_stored(api, scenario, db):
    before = db.query(Mensaje).filter(Mensaje.chat_id == scenario.chat_a.id).count()

    response = api(
        _messages_path(scenario.chat_a.id),
        as_auth_id=CUSTOMER_AUTH,
        method="POST",
        json={"content": "escríbeme a casey.customer@example.test"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["type"] == "contact_details_blocked"
    assert "correo electrónico" in detail["msg"]
    assert db.query(Mensaje).filter(Mensaje.chat_id == scenario.chat_a.id).count() == before


def test_sending_to_a_chat_the_caller_does_not_participate_in_is_not_found(api, scenario, db):
    before = db.query(Mensaje).count()

    outsider = api(
        _messages_path(scenario.chat_c.id),
        as_auth_id=OTHER_CUSTOMER_AUTH,
        method="POST",
        json={"content": "hola"},
    )
    unknown = api(
        _messages_path(uuid4()),
        as_auth_id=CUSTOMER_AUTH,
        method="POST",
        json={"content": "hola"},
    )

    assert outsider.status_code == unknown.status_code == 404
    assert outsider.json() == unknown.json()
    assert db.query(Mensaje).count() == before


@pytest.mark.parametrize("query", ["?limit=0", "?limit=101", "?before=2026-10-01T11:00:00", "?before=not-a-date"])
def test_message_query_inputs_are_validated(api, scenario, query):
    assert api(_messages_path(scenario.chat_a.id, query), as_auth_id=CUSTOMER_AUTH).status_code == 422
