from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import Servicio, Valoracion

AUTH_USER_ID = UUID("a6607c8d-9ea3-4166-8bf2-2333ae164d57")
ACCOUNT_ID = UUID("59f7cf6f-4d38-4c9c-96e7-62f354874d1d")
PROFILE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e32")
SERVICE_ID = UUID("0c3b7b0e-6f0a-4a57-8f7e-3d1f0f6a9b10")
COMPLETED_AT = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
RATED_AT = datetime(2026, 10, 6, 9, 30, tzinfo=timezone.utc)


class FakeResult:
    def __init__(self, *, row=None, scalar=None, rows=(), count=None):
        self.row = row
        self.scalar = scalar
        self.rows = list(rows)
        self.count = count

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.count

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, results=(), flush_error: Exception | None = None):
        self.results = iter(results)
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.statements = []
        self.flush_error = flush_error

    def execute(self, statement):
        self.statements.append(statement)
        return next(self.results)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        if self.flush_error is not None:
            raise self.flush_error

    def refresh(self, value):
        value.created_at = RATED_AT

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def run_request(method: str, path: str, session: FakeSession, *, json_body=None, authenticated=True):
    app.dependency_overrides[get_db_session] = lambda: session
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=AUTH_USER_ID,
            email="private@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
    else:
        def reject():
            raise HTTPException(status_code=401, detail="Not authenticated.")
        app.dependency_overrides[get_current_user] = reject

    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, json=json_body)

    try:
        return asyncio.run(send())
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


def service_row(**overrides):
    row = {
        "service_id": SERVICE_ID,
        "provider_profile_id": PROFILE_ID,
        "provider_kind": "company",
        "profile_name": "Transportes del Sur",
        "owner_first_name": "Ana",
        "owner_last_name": "Pérez",
        "service_type_name": "Mudanzas",
        "completed_at": COMPLETED_AT,
        "rating_value": None,
        "rating_comment": None,
        "rating_created_at": None,
    }
    return {**row, **overrides}


def test_customer_services_list_returns_own_services_with_optional_rating_and_pagination():
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(count=2),
        FakeResult(rows=[
            service_row(rating_value=5, rating_comment="Buen servicio", rating_created_at=RATED_AT),
            service_row(service_id=uuid4(), completed_at=None),
        ]),
    ])

    response = run_request("GET", "/api/customer/services?limit=10&offset=0", session)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert body["items"][0] == {
        "serviceId": str(SERVICE_ID),
        "providerProfileId": str(PROFILE_ID),
        "providerName": "Transportes del Sur",
        "serviceTypeName": "Mudanzas",
        "completedAt": "2026-10-05T12:00:00Z",
        "rating": {"rating": 5, "comment": "Buen servicio", "createdAt": "2026-10-06T09:30:00Z"},
    }
    assert body["items"][1]["rating"] is None
    assert body["items"][1]["completedAt"] is None
    rows_sql = str(session.statements[2].compile(dialect=postgresql.dialect()))
    assert '"Servicio"."ID_Cliente" = ' in rows_sql
    assert 'ORDER BY "Servicio"."Fecha_Creacion" DESC' in rows_sql
    assert "LIMIT" in rows_sql
    count_sql = str(session.statements[1].compile(dialect=postgresql.dialect()))
    assert '"Servicio"."ID_Cliente" = ' in count_sql


def test_customer_services_total_and_items_are_counted_over_the_same_joined_relation():
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(count=0),
        FakeResult(rows=[]),
    ])

    response = run_request("GET", "/api/customer/services", session)

    assert response.status_code == 200
    count_sql = str(session.statements[1].compile(dialect=postgresql.dialect()))
    rows_sql = str(session.statements[2].compile(dialect=postgresql.dialect()))
    for table in ('"Perfil"', '"Usuario"', '"Formulario_servicio"', '"Tipos_Servicio"'):
        assert f"JOIN {table}" in count_sql
        assert f"JOIN {table}" in rows_sql


@pytest.mark.parametrize(
    ("provider_kind", "profile_name", "first_name", "last_name", "expected"),
    [
        ("independent_driver", "Fletes Pedro", "Pedro", "Soto", "Pedro Soto"),
        ("independent_driver", "Fletes Pedro", None, "Soto", "Soto"),
        ("independent_driver", "Fletes Pedro", "Pedro", None, "Pedro"),
        ("independent_driver", "Fletes Pedro", "  ", "", "Prestador"),
        ("independent_driver", "Fletes Pedro", None, None, "Prestador"),
        ("company", "Transportes del Sur", None, None, "Transportes del Sur"),
        ("company", "   ", None, None, "Prestador"),
    ],
)
def test_customer_service_provider_name_is_never_null_or_empty(provider_kind, profile_name, first_name, last_name, expected):
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(count=1),
        FakeResult(rows=[
            service_row(
                provider_kind=provider_kind,
                profile_name=profile_name,
                owner_first_name=first_name,
                owner_last_name=last_name,
            )
        ]),
    ])

    response = run_request("GET", "/api/customer/services", session)

    assert response.status_code == 200
    assert response.json()["items"][0]["providerName"] == expected


def test_customer_services_list_does_not_expose_private_identifiers():
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(count=1),
        FakeResult(rows=[service_row(rating_value=4, rating_comment=None, rating_created_at=RATED_AT)]),
    ])

    response = run_request("GET", "/api/customer/services", session)

    assert response.status_code == 200
    for private_field in ("customerId", "userId", "authUserId", "email", "ratingId", "formId", "userIdentifier"):
        assert private_field not in response.text
    assert str(ACCOUNT_ID) not in response.text
    assert str(AUTH_USER_ID) not in response.text


@pytest.mark.parametrize("row", [(ACCOUNT_ID, "company_owner"), (ACCOUNT_ID, "company_driver"), None])
def test_customer_services_list_requires_a_customer_account(row):
    session = FakeSession([FakeResult(row=row)])

    response = run_request("GET", "/api/customer/services", session)

    assert response.status_code == 403
    assert len(session.statements) == 1


def test_customer_services_list_requires_authentication():
    session = FakeSession()

    response = run_request("GET", "/api/customer/services", session, authenticated=False)

    assert response.status_code == 401
    assert session.statements == []


@pytest.mark.parametrize("query", ["limit=51", "limit=0", "offset=5001", "offset=-1"])
def test_customer_services_list_bounds_page_size_and_offset(query):
    session = FakeSession()

    response = run_request("GET", f"/api/customer/services?{query}", session)

    assert response.status_code == 422
    assert session.statements == []


def test_customer_rating_is_stored_for_the_callers_completed_service():
    service = Servicio(id=SERVICE_ID, customer_id=ACCOUNT_ID, profile_id=PROFILE_ID, completed_at=COMPLETED_AT)
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(scalar=service),
    ])

    response = run_request("POST", f"/api/customer/services/{SERVICE_ID}/rating", session, json_body={
        "rating": 4,
        "comment": "  Llegó a tiempo.  ",
    })

    assert response.status_code == 201
    assert response.json() == {"rating": 4, "comment": "Llegó a tiempo.", "createdAt": "2026-10-06T09:30:00Z"}
    assert len(session.added) == 1
    stored = session.added[0]
    assert isinstance(stored, Valoracion)
    assert stored.service_id == SERVICE_ID
    assert stored.user_id == ACCOUNT_ID
    assert stored.user_id != AUTH_USER_ID
    assert stored.rating == 4
    assert stored.comment == "Llegó a tiempo."
    assert session.committed
    service_sql = str(session.statements[1].compile(dialect=postgresql.dialect()))
    assert '"Servicio"."ID_Cliente" = ' in service_sql


def test_blank_rating_comment_is_stored_as_absent():
    service = Servicio(id=SERVICE_ID, customer_id=ACCOUNT_ID, profile_id=PROFILE_ID, completed_at=COMPLETED_AT)
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(scalar=service),
    ])

    response = run_request("POST", f"/api/customer/services/{SERVICE_ID}/rating", session, json_body={"rating": 5, "comment": "   "})

    assert response.status_code == 201
    assert response.json()["comment"] is None
    assert session.added[0].comment is None


def test_rating_for_missing_or_foreign_service_is_not_found_without_leaking_existence():
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(scalar=None),
    ])

    response = run_request("POST", f"/api/customer/services/{SERVICE_ID}/rating", session, json_body={"rating": 3})

    assert response.status_code == 404
    assert response.json()["detail"] == "Service not found."
    assert session.added == []
    assert not session.committed


def test_rating_requires_a_completed_service():
    service = Servicio(id=SERVICE_ID, customer_id=ACCOUNT_ID, profile_id=PROFILE_ID, completed_at=None)
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(scalar=service),
    ])

    response = run_request("POST", f"/api/customer/services/{SERVICE_ID}/rating", session, json_body={"rating": 3})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["type"] == "service_not_completed"
    assert detail[0]["loc"] == ["path", "service_id"]
    assert session.added == []
    assert not session.committed


def test_second_rating_for_the_same_service_maps_the_unique_constraint_to_conflict():
    class Diag:
        constraint_name = "uq_rating_service"

    class Orig(Exception):
        diag = Diag()

    service = Servicio(id=SERVICE_ID, customer_id=ACCOUNT_ID, profile_id=PROFILE_ID, completed_at=COMPLETED_AT)
    session = FakeSession(
        [FakeResult(row=(ACCOUNT_ID, "client")), FakeResult(scalar=service)],
        flush_error=IntegrityError("INSERT", {}, Orig("duplicate key")),
    )

    response = run_request("POST", f"/api/customer/services/{SERVICE_ID}/rating", session, json_body={"rating": 2})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail[0]["type"] == "already_rated"
    assert session.rolled_back
    assert not session.committed


def test_unrelated_integrity_errors_are_not_reported_as_already_rated():
    class Diag:
        constraint_name = "fk_valoracion_servicio"

    class Orig(Exception):
        diag = Diag()

    service = Servicio(id=SERVICE_ID, customer_id=ACCOUNT_ID, profile_id=PROFILE_ID, completed_at=COMPLETED_AT)
    session = FakeSession(
        [FakeResult(row=(ACCOUNT_ID, "client")), FakeResult(scalar=service)],
        flush_error=IntegrityError("INSERT", {}, Orig("foreign key violation")),
    )

    with pytest.raises(IntegrityError):
        run_request("POST", f"/api/customer/services/{SERVICE_ID}/rating", session, json_body={"rating": 2})
    assert session.rolled_back
    assert not session.committed


def test_rating_requires_a_customer_account():
    session = FakeSession([FakeResult(row=(ACCOUNT_ID, "company_owner"))])

    response = run_request("POST", f"/api/customer/services/{SERVICE_ID}/rating", session, json_body={"rating": 5})

    assert response.status_code == 403
    assert session.added == []


def test_rating_requires_authentication():
    session = FakeSession()

    response = run_request("POST", f"/api/customer/services/{SERVICE_ID}/rating", session, json_body={"rating": 5}, authenticated=False)

    assert response.status_code == 401
    assert session.added == []


@pytest.mark.parametrize("body", [
    {"rating": 0},
    {"rating": 6},
    {"rating": 4.5},
    {"rating": None},
    {"comment": "sin calificación"},
    {"rating": 4, "comment": "x" * 1001},
    {"rating": 4, "customerId": str(AUTH_USER_ID)},
    {"rating": 4, "serviceId": str(SERVICE_ID)},
])
def test_rating_body_is_validated_and_rejects_client_controlled_fields(body):
    session = FakeSession()

    response = run_request("POST", f"/api/customer/services/{SERVICE_ID}/rating", session, json_body=body)

    assert response.status_code == 422
    assert session.statements == []
    assert session.added == []
