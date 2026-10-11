from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from sqlalchemy.dialects import postgresql

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.main import app

PROVIDER_ACCOUNT_ID = UUID("59f7cf6f-4d38-4c9c-96e7-62f354874d1d")
PROFILE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e32")
OTHER_PROFILE_ID = UUID("4fab3c4d-8f5f-48ea-8ce2-c5187e8e97cd")
SERVICE_TYPE_ID = UUID("6f6d0ae4-98ac-4a74-9a79-aac79443ed91")
CUSTOMER_EMAIL = "customer-private@example.test"
CUSTOMER_PHONE = "+56987654321"


class FakeResult:
    def __init__(self, *, row=None, scalar=None, rows=()):
        self.row = row
        self.scalar = scalar
        self.rows = list(rows)

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar

    def all(self):
        return self.rows


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def request_row(*, status="pending", profile_id=PROFILE_ID, **overrides) -> dict:
    """Row shape returned by the inbox query, before the customer name policy is applied."""
    row = {
        "profile_id": profile_id,
        "request_id": uuid4(),
        "status": status,
        "origin": "Santiago",
        "destination": "Valparaíso",
        "requested_at": datetime(2026, 10, 12, 12, tzinfo=timezone.utc),
        "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "estimated_weight": None,
        "estimated_volume": None,
        "description": "Traslado de muebles",
        "cargo_measurements": None,
        "service_name": "Mudanzas",
        "chat_id": None,
        "origin_commune_code": "13101",
        "origin_commune_name": "Santiago",
        "origin_region_name": "Metropolitana de Santiago",
        "destination_commune_code": "05101",
        "destination_commune_name": "Valparaíso",
        "destination_region_name": "Valparaíso",
        "is_exclusive": False,
        "customer_first_name": "Casey",
        "customer_last_name": "Customer",
    }
    row.update(overrides)
    return row


class InboxSession:
    """Answers the two ownership queries, then serves the inbox queries from a row list.

    The status predicate and grouping are read from the compiled SQL, so a route that filters
    its counts or leaks an unexpected column is observable.
    """

    def __init__(self, rows: list[dict], statements: list[str], role: str = "company_owner"):
        self.rows = rows
        self.statements = statements
        self.role = role
        self.calls = 0

    def execute(self, statement):
        self.calls += 1
        if self.calls == 1:
            return FakeResult(row=(PROVIDER_ACCOUNT_ID, self.role))
        if self.calls == 2:
            return FakeResult(scalar=PROFILE_ID)
        sql = _sql(statement)
        self.statements.append(sql)
        status_filter = re.search(r'"Estado" = \'(\w+)\'', sql)
        request_filter = re.search(r'"Formulario_servicio"\."ID" = \'([0-9a-f-]{36})\'', sql)
        matching = [
            row for row in self.rows
            if row["profile_id"] == PROFILE_ID
            and (status_filter is None or row["status"] == status_filter.group(1))
            and (request_filter is None or str(row["request_id"]) == request_filter.group(1))
        ]
        if "group by" in sql.lower():
            statuses = ("pending", "accepted", "rejected")
            return FakeResult(rows=[
                (status, sum(1 for row in self.rows if row["profile_id"] == PROFILE_ID and row["status"] == status))
                for status in statuses
            ])
        if "count(" in sql.lower():
            return FakeResult(scalar=len(matching))
        return FakeResult(row=matching[0] if matching else None, rows=matching)

    def add(self, value):
        raise AssertionError("The inbox is read-only")


def get_inbox(path: str, rows: list[dict], *, role: str = "company_owner"):
    statements: list[str] = []
    app.dependency_overrides[get_db_session] = lambda: InboxSession(rows, statements, role=role)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=PROVIDER_ACCOUNT_ID,
        email="provider@example.test",
        session_id=uuid4(),
        assurance="aal2",
        authentication_methods=frozenset({"password"}),
    )

    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get(path)

    try:
        response = asyncio.run(send())
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)
    return response, statements


def test_counts_cover_every_status_and_ignore_the_status_filter():
    rows = [
        request_row(status="pending"),
        request_row(status="pending"),
        request_row(status="accepted", customer_last_name="Customer"),
        request_row(status="rejected"),
        request_row(status="pending", profile_id=OTHER_PROFILE_ID),
    ]

    everything, _ = get_inbox("/api/provider/requests", rows)
    accepted_only, _ = get_inbox("/api/provider/requests?status=accepted", rows)

    expected_counts = {"pending": 2, "accepted": 1, "rejected": 1}
    assert everything.json()["counts"] == expected_counts
    assert accepted_only.json()["counts"] == expected_counts
    assert everything.json()["total"] == 4


def test_status_filter_limits_items_and_total_to_that_status():
    rows = [request_row(status="pending"), request_row(status="accepted"), request_row(status="rejected")]

    response, _ = get_inbox("/api/provider/requests?status=accepted", rows)

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 1
    assert [item["status"] for item in body["items"]] == ["accepted"]


def test_invalid_status_is_rejected_with_a_spanish_validation_message():
    response, _ = get_inbox("/api/provider/requests?status=cancelled", [request_row()])

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["query", "status"]
    assert "estado válido" in detail["msg"]


def test_commune_and_region_names_are_returned_and_destination_may_be_null():
    rows = [
        request_row(
            origin_commune_code="13101",
            origin_commune_name="Santiago",
            origin_region_name="Metropolitana de Santiago",
            destination=None,
            destination_commune_code=None,
            destination_commune_name=None,
            destination_region_name=None,
        )
    ]

    response, _ = get_inbox("/api/provider/requests", rows)

    item = response.json()["items"][0]
    assert item["originCommuneCode"] == "13101"
    assert item["originCommuneName"] == "Santiago"
    assert item["originRegionName"] == "Metropolitana de Santiago"
    assert item["destination"] is None
    assert item["destinationCommuneCode"] is None
    assert item["destinationCommuneName"] is None
    assert item["destinationRegionName"] is None


def test_origin_may_be_null_for_legacy_free_text_requests():
    rows = [request_row(origin=None, origin_commune_code=None, origin_commune_name=None, origin_region_name=None)]

    response, _ = get_inbox("/api/provider/requests", rows)

    item = response.json()["items"][0]
    assert response.status_code == 200
    assert item["origin"] is None
    assert item["originCommuneName"] is None


def test_customer_first_name_is_shared_before_acceptance_without_last_name():
    rows = [request_row(status="pending"), request_row(status="rejected")]

    response, _ = get_inbox("/api/provider/requests", rows)

    for item in response.json()["items"]:
        assert item["customerFirstName"] == "Casey"
        assert item["customerLastName"] is None


def test_customer_last_name_is_shared_only_after_acceptance():
    rows = [request_row(status="accepted", customer_last_name="Customer")]

    response, _ = get_inbox("/api/provider/requests", rows)

    item = response.json()["items"][0]
    assert item["customerFirstName"] == "Casey"
    assert item["customerLastName"] == "Customer"


def test_inbox_queries_never_select_customer_phone_or_email():
    rows = [request_row(status="accepted", customer_last_name="Customer")]

    response, statements = get_inbox("/api/provider/requests", rows)

    assert response.status_code == 200
    assert statements, "the inbox must run queries"
    for sql in statements:
        assert '"Correo"' not in sql
        assert '"Telefono"' not in sql
        assert "customer_email" not in sql
    assert CUSTOMER_EMAIL not in response.text
    assert CUSTOMER_PHONE not in response.text


def test_is_exclusive_is_exposed_on_each_item():
    rows = [request_row(is_exclusive=True)]

    response, _ = get_inbox("/api/provider/requests", rows)

    assert response.json()["items"][0]["isExclusive"] is True


def test_detail_returns_the_owned_request_with_the_list_shape():
    row = request_row(status="pending", destination=None, destination_commune_code=None, destination_commune_name=None, destination_region_name=None)
    request_id = row["request_id"]

    response, statements = get_inbox(f"/api/provider/requests/{request_id}", [row])

    assert response.status_code == 200
    body = response.json()
    assert body["requestId"] == str(request_id)
    assert body["status"] == "pending"
    assert body["originCommuneName"] == "Santiago"
    assert body["destination"] is None
    assert body["customerFirstName"] == "Casey"
    assert body["customerLastName"] is None
    assert "counts" not in body
    assert any(f'"ID" = \'{request_id}\'' in sql for sql in statements)


def test_detail_shares_customer_last_name_only_after_acceptance():
    accepted = request_row(status="accepted", customer_last_name="Customer")
    rejected = request_row(status="rejected", customer_last_name="Customer")

    accepted_response, _ = get_inbox(f"/api/provider/requests/{accepted['request_id']}", [accepted, rejected])
    rejected_response, _ = get_inbox(f"/api/provider/requests/{rejected['request_id']}", [accepted, rejected])

    assert accepted_response.json()["customerLastName"] == "Customer"
    assert rejected_response.json()["customerLastName"] is None


def test_detail_hides_other_providers_requests_and_unknown_ids_identically():
    foreign = request_row(profile_id=OTHER_PROFILE_ID)
    unknown_id = uuid4()

    foreign_response, _ = get_inbox(f"/api/provider/requests/{foreign['request_id']}", [foreign])
    unknown_response, _ = get_inbox(f"/api/provider/requests/{unknown_id}", [foreign])

    assert foreign_response.status_code == unknown_response.status_code == 404
    assert foreign_response.json() == unknown_response.json()


def test_detail_requires_a_provider_account():
    row = request_row()

    response, _ = get_inbox(f"/api/provider/requests/{row['request_id']}", [row], role="client")

    assert response.status_code == 403


def test_detail_queries_never_select_customer_phone_or_email():
    row = request_row(status="accepted", customer_last_name="Customer")

    response, statements = get_inbox(f"/api/provider/requests/{row['request_id']}", [row])

    assert response.status_code == 200
    assert statements
    for sql in statements:
        assert '"Correo"' not in sql
        assert '"Telefono"' not in sql
    assert CUSTOMER_EMAIL not in response.text
    assert CUSTOMER_PHONE not in response.text
