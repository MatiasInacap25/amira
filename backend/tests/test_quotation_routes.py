"""Quotations: provider creation, supersession, expiry, timeline placement and customer rejection."""

from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from amira_api.models import Cotizacion
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


def _quotations_path(chat_id: UUID) -> str:
    return f"/api/chats/{chat_id}/quotations"


def _create(api, scenario: Scenario, *, auth=PROVIDER_AUTH, body=None, chat=None):
    return api(
        _quotations_path((chat or scenario.chat_a).id),
        as_auth_id=auth,
        method="POST",
        json=body if body is not None else VALID_QUOTATION,
    )


def _timeline(api, scenario: Scenario, *, auth=CUSTOMER_AUTH, query: str = "", chat=None) -> list[dict]:
    return api(f"/api/chats/{(chat or scenario.chat_a).id}/messages{query}", as_auth_id=auth).json()["timeline"]


def test_provider_creates_a_pending_quotation_with_requested_validity(api, scenario):
    response = _create(api, scenario)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["amount"] == 150000
    assert body["currency"] == "CLP"
    assert body["serviceAt"].startswith("2026-10-20T09:00")
    assert body["description"] == "Mudanza de 2 dormitorios"
    assert body["paidAt"] is None
    assert body["quotationId"] is not None
    created = datetime.fromisoformat(body["createdAt"])
    assert datetime.fromisoformat(body["expiresAt"]) - created == timedelta(hours=72)


def test_validity_defaults_to_48_hours(api, scenario):
    body = {key: value for key, value in VALID_QUOTATION.items() if key != "validityHours"}

    created = _create(api, scenario, body=body).json()

    assert datetime.fromisoformat(created["expiresAt"]) - datetime.fromisoformat(created["createdAt"]) == timedelta(hours=48)


def test_provider_side_participant_who_is_not_the_customer_can_quote(api, scenario):
    # chat_c pairs the customer with the driver owner, who is the provider side of that chat.
    assert _create(api, scenario, auth=DRIVER_AUTH, chat=scenario.chat_c).status_code == 201


def test_customer_cannot_send_a_quotation_to_their_own_chat(api, scenario):
    response = _create(api, scenario, auth=CUSTOMER_AUTH)

    assert response.status_code == 403


def test_non_participant_and_unknown_chat_get_the_same_not_found(api, scenario):
    outsider = _create(api, scenario, auth=OTHER_CUSTOMER_AUTH, chat=scenario.chat_c)
    unknown_chat = api(_quotations_path(UUID(int=1)), as_auth_id=PROVIDER_AUTH, method="POST", json=VALID_QUOTATION)
    unknown_account = _create(api, scenario, auth=UNKNOWN_AUTH)

    assert outsider.status_code == unknown_chat.status_code == unknown_account.status_code == 404
    assert outsider.json() == unknown_chat.json() == unknown_account.json()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("amount", 0, id="amount-zero"),
        pytest.param("amount", -5, id="amount-negative"),
        pytest.param("amount", 1500.5, id="amount-fractional"),
        pytest.param("serviceAt", "2026-10-20T09:00:00", id="service-naive-datetime"),
        pytest.param("description", "   ", id="description-blank"),
        pytest.param("validityHours", 0, id="validity-zero"),
        pytest.param("validityHours", 169, id="validity-above-week"),
    ],
)
def test_quotation_fields_are_validated(api, scenario, field, value):
    body = {**VALID_QUOTATION, field: value}

    assert _create(api, scenario, body=body).status_code == 422


def test_amount_is_required(api, scenario):
    body = {key: value for key, value in VALID_QUOTATION.items() if key != "amount"}

    assert _create(api, scenario, body=body).status_code == 422


def test_new_quotation_supersedes_the_previous_pending_one(api, scenario, db: Session):
    first = _create(api, scenario).json()
    second = _create(api, scenario, body={**VALID_QUOTATION, "amount": 200000}).json()

    assert db.get(Cotizacion, UUID(first["quotationId"])).status == "superseded"
    assert db.get(Cotizacion, UUID(second["quotationId"])).status == "pending"


def test_quotations_appear_in_the_timeline_after_the_messages_that_preceded_them(api, scenario):
    created = _create(api, scenario).json()

    timeline = _timeline(api, scenario, auth=CUSTOMER_AUTH)
    assert [entry["kind"] for entry in timeline] == ["message", "message", "quotation"]
    entry = timeline[-1]
    assert entry["quotation"]["quotationId"] == created["quotationId"]
    assert entry["quotation"]["status"] == "pending"
    assert entry["quotation"]["amount"] == 150000


def test_timeline_marks_an_expired_pending_quotation_as_expired_on_read(api, scenario, db: Session):
    created = _create(api, scenario).json()
    quotation = db.get(Cotizacion, UUID(created["quotationId"]))
    quotation.created_at = datetime.now(timezone.utc) - timedelta(days=3)
    quotation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    timeline = _timeline(api, scenario, auth=PROVIDER_AUTH)

    assert timeline[-1]["quotation"]["status"] == "expired"
    assert db.get(Cotizacion, quotation.id).status == "pending"


def test_expired_pending_quotation_is_superseded_by_a_new_one(api, scenario, db: Session):
    # Expired quotations are still "pending" in storage, so a new one must still supersede them.
    created = _create(api, scenario).json()
    quotation = db.get(Cotizacion, UUID(created["quotationId"]))
    quotation.created_at = datetime.now(timezone.utc) - timedelta(days=3)
    quotation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    _create(api, scenario, body={**VALID_QUOTATION, "amount": 99000})

    assert db.get(Cotizacion, quotation.id).status == "superseded"


def test_a_chat_with_a_paid_quotation_cannot_receive_another_quotation(api, scenario, db: Session):
    created = _create(api, scenario).json()
    db.get(Cotizacion, UUID(created["quotationId"])).status = "paid"
    db.commit()

    response = _create(api, scenario, body={**VALID_QUOTATION, "amount": 99000})

    assert response.status_code == 409


def test_mixed_timeline_pages_walk_every_entry_once(api, scenario):
    _create(api, scenario)
    _create(api, scenario, body={**VALID_QUOTATION, "amount": 99000})

    page = api(f"/api/chats/{scenario.chat_a.id}/messages?limit=1", as_auth_id=CUSTOMER_AUTH).json()
    collected = list(page["timeline"])
    while page["nextBefore"] is not None:
        page = api(
            f"/api/chats/{scenario.chat_a.id}/messages?limit=1&before={quote(page['nextBefore'], safe='')}",
            as_auth_id=CUSTOMER_AUTH,
        ).json()
        collected = page["timeline"] + collected

    assert [entry["kind"] for entry in collected] == ["message", "message", "quotation", "quotation"]
    assert len({entry.get("messageId") or entry["quotation"]["quotationId"] for entry in collected}) == 4


# Rejection (customer only, pending only)


def _reject(api, quotation_id, *, auth=CUSTOMER_AUTH):
    return api(f"/api/quotations/{quotation_id}/reject", as_auth_id=auth, method="POST")


def test_customer_rejects_a_pending_quotation(api, scenario, db: Session):
    quotation_id = _create(api, scenario).json()["quotationId"]

    response = _reject(api, quotation_id)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["paidAt"] is None
    assert db.get(Cotizacion, UUID(quotation_id)).status == "rejected"


def test_rejecting_twice_is_a_conflict(api, scenario):
    quotation_id = _create(api, scenario).json()["quotationId"]
    _reject(api, quotation_id)

    assert _reject(api, quotation_id).status_code == 409


def test_provider_cannot_reject_their_own_quotation(api, scenario, db: Session):
    quotation_id = _create(api, scenario).json()["quotationId"]

    assert _reject(api, quotation_id, auth=PROVIDER_AUTH).status_code == 403
    assert db.get(Cotizacion, UUID(quotation_id)).status == "pending"


def test_reject_of_an_unknown_or_foreign_quotation_is_not_found(api, scenario):
    quotation_id = _create(api, scenario).json()["quotationId"]

    unknown = _reject(api, UUID(int=2))
    foreign = _reject(api, quotation_id, auth=OTHER_CUSTOMER_AUTH)

    assert unknown.status_code == foreign.status_code == 404
    assert unknown.json() == foreign.json()


def test_expired_quotation_cannot_be_rejected(api, scenario, db: Session):
    quotation_id = _create(api, scenario).json()["quotationId"]
    quotation = db.get(Cotizacion, UUID(quotation_id))
    quotation.created_at = datetime.now(timezone.utc) - timedelta(days=3)
    quotation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    assert _reject(api, quotation_id).status_code == 409


def test_superseded_quotation_cannot_be_rejected(api, scenario):
    first = _create(api, scenario).json()["quotationId"]
    _create(api, scenario, body={**VALID_QUOTATION, "amount": 99000})

    assert _reject(api, first).status_code == 409
