from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import Conductor, FormularioServicio, Servicio

AUTH_USER_ID = UUID("a6607c8d-9ea3-4166-8bf2-2333ae164d57")
ACCOUNT_ID = UUID("59f7cf6f-4d38-4c9c-96e7-62f354874d1d")
PROFILE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e32")
SERVICE_TYPE_ID = UUID("6f6d0ae4-98ac-4a74-9a79-aac79443ed91")


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

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, results=()):
        self.results = iter(results)
        self.added = []
        self.committed = False
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return next(self.results)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        pass

    def commit(self):
        self.committed = True


PROFILE = {
    "profile_id": PROFILE_ID,
    "provider_name": "Transportes del Sur",
    "kind": "company",
    "description": "Traslados y carga en la zona central.",
    "location": "Santiago",
    "commune_code": None,
    "commune_name": None,
    "region_name": None,
    "public_activated_at": datetime(2026, 10, 3, tzinfo=timezone.utc),
    "owner_first_name": "Ana",
    "owner_last_name": "Pérez",
}


def run_request(method: str, path: str, session: FakeSession, *, json_body=None, authenticated=True, reject_unauthenticated=False):
    app.dependency_overrides[get_db_session] = lambda: session
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=AUTH_USER_ID,
            email="private@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
    elif reject_unauthenticated:
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


def test_public_profile_returns_real_provider_and_linked_driver_names_but_only_allowlisted_data():
    session = FakeSession([
        FakeResult(row=PROFILE),
        FakeResult(rows=[{"first_name": "Pedro", "last_name": "Soto", "is_owner": False}]),
        FakeResult(rows=[{"service_type_id": SERVICE_TYPE_ID, "name": "Mudanzas"}]),
        FakeResult(rows=[{"brand": "Volvo", "model": "FH", "year": 2022, "maximum_weight": "18000.00"}]),
        FakeResult(row={"average_rating": 4.5, "rating_count": 2}),
        FakeResult(rows=[{"rating": 5, "comment": "Buen servicio", "created_at": datetime(2026, 10, 4, tzinfo=timezone.utc)}]),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "profileId": str(PROFILE_ID),
        "providerName": "Transportes del Sur",
        "kind": "company",
        "description": "Traslados y carga en la zona central.",
        "location": "Santiago",
        "communeCode": None,
        "communeName": None,
        "regionName": None,
        "ownerName": "Ana Pérez",
        "drivers": [{"firstName": "Pedro", "lastName": "Soto", "isOwner": False}],
        "services": [{"serviceTypeId": str(SERVICE_TYPE_ID), "name": "Mudanzas"}],
        "vehicles": [{"brand": "Volvo", "model": "FH", "year": 2022, "maximumWeight": "18000.00"}],
        "ratings": {
            "averageRating": 4.5,
            "ratingCount": 2,
            "recent": [{"rating": 5, "comment": "Buen servicio", "createdAt": "2026-10-04T00:00:00Z"}],
        },
    }
    for private_field in ("nationalId", "birthDate", "email", "phone", "authUserId", "companyTaxId", "plate", "imageStorageKey", "logoStorageKey", "userId", "serviceId", "customerId", "ratingId"):
        assert private_field not in response.text
    assert "user-chosen" not in response.text


def test_public_profile_location_is_built_from_the_commune_catalog_when_available():
    session = FakeSession([
        FakeResult(row={
            **PROFILE,
            "location": "Calle vieja 123",
            "commune_code": "13101",
            "commune_name": "Santiago",
            "region_name": "Metropolitana de Santiago",
        }),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(row={"average_rating": None, "rating_count": 0}),
        FakeResult(rows=[]),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 200
    body = response.json()
    assert body["location"] == "Santiago, Metropolitana de Santiago"
    assert body["communeCode"] == "13101"
    assert body["communeName"] == "Santiago"
    assert body["regionName"] == "Metropolitana de Santiago"
    assert "Calle vieja 123" not in response.text
    profile_query = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert '"Comunas"."Codigo" = "Perfil"."Codigo_Comuna"' in profile_query
    assert '"Regiones"."Codigo" = "Comunas"."Codigo_Region"' in profile_query


@pytest.mark.parametrize(
    ("commune_name", "region_name", "legacy_location", "expected"),
    [
        ("Santiago", "Metropolitana de Santiago", "Calle vieja 123", "Santiago, Metropolitana de Santiago"),
        ("Santiago", None, "Calle vieja 123", "Santiago"),
        (None, "Metropolitana de Santiago", "Calle vieja 123", "Metropolitana de Santiago"),
        (None, None, "Calle vieja 123", "Calle vieja 123"),
        ("  ", " ", "Calle vieja 123", "Calle vieja 123"),
        (None, None, None, None),
    ],
)
def test_public_profile_location_uses_only_available_parts_and_never_renders_none(
    commune_name, region_name, legacy_location, expected
):
    session = FakeSession([
        FakeResult(row={
            **PROFILE,
            "location": legacy_location,
            "commune_code": "13101",
            "commune_name": commune_name,
            "region_name": region_name,
        }),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(row={"average_rating": None, "rating_count": 0}),
        FakeResult(rows=[]),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 200
    body = response.json()
    assert body["location"] == expected
    assert "None" not in response.text


def test_public_profile_keeps_legacy_location_text_when_no_commune_is_linked():
    session = FakeSession([
        FakeResult(row={**PROFILE, "location": "Calle vieja 123"}),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(row={"average_rating": None, "rating_count": 0}),
        FakeResult(rows=[]),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    body = response.json()
    assert body["location"] == "Calle vieja 123"
    assert body["communeCode"] is None
    assert body["communeName"] is None
    assert body["regionName"] is None


def test_company_profile_marks_only_the_owner_driver_record_with_is_owner():
    session = FakeSession([
        FakeResult(row=PROFILE),
        FakeResult(rows=[
            {"first_name": "Ana", "last_name": "Pérez", "is_owner": True},
            {"first_name": "Pedro", "last_name": "Soto", "is_owner": False},
        ]),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(row={"average_rating": None, "rating_count": 0}),
        FakeResult(rows=[]),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 200
    assert response.json()["drivers"] == [
        {"firstName": "Ana", "lastName": "Pérez", "isOwner": True},
        {"firstName": "Pedro", "lastName": "Soto", "isOwner": False},
    ]
    driver_query = str(session.statements[1].compile(dialect=postgresql.dialect()))
    assert "AS is_owner" in driver_query
    assert '"Conductor"."ID_user" = (SELECT "Perfil"."ID_user"' in driver_query


def test_public_profile_ratings_aggregate_all_eligible_rows_and_bound_recent_reviews():
    recent = [
        {"rating": (index % 5) + 1, "comment": None if index == 0 else f"Comentario {index}", "created_at": datetime(2026, 10, 4, tzinfo=timezone.utc) - timedelta(days=index)}
        for index in range(20)
    ]
    session = FakeSession([
        FakeResult(row=PROFILE),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(row={"average_rating": 4.25, "rating_count": 27}),
        FakeResult(rows=recent),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 200
    assert response.json()["ratings"] == {
        "averageRating": 4.25,
        "ratingCount": 27,
        "recent": [
            {"rating": item["rating"], "comment": item["comment"], "createdAt": item["created_at"].isoformat().replace("+00:00", "Z")}
            for item in recent
        ],
    }
    aggregate_sql = str(session.statements[4].compile(dialect=postgresql.dialect()))
    recent_query = session.statements[5].compile(dialect=postgresql.dialect())
    recent_sql = str(recent_query)
    recent_projection = recent_sql.split("FROM", maxsplit=1)[0]
    assert '"Valoracion"."Rating"' in recent_projection
    assert '"Valoracion"."Comentario"' in recent_projection
    assert '"Valoracion"."Fecha_Registro"' in recent_projection
    assert '"Valoracion"."ID_Usuario"' not in recent_projection
    assert '"Valoracion"."ID_Servicio"' not in recent_projection
    for query in (aggregate_sql, recent_sql):
        assert '"Servicio"."ID_Perfil" = ' in query
        assert '"Servicio"."Fecha_Finalizacion" IS NOT NULL' in query
        assert '"Valoracion"."ID_Usuario" = "Servicio"."ID_Cliente"' in query
    assert 'ORDER BY "Valoracion"."Fecha_Registro" DESC, "Valoracion"."ID" DESC' in recent_sql
    assert "LIMIT" in recent_sql
    assert len(response.json()["ratings"]["recent"]) == 20


def test_public_profile_with_no_eligible_ratings_returns_an_authoritative_empty_summary():
    session = FakeSession([
        FakeResult(row=PROFILE),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(row={"average_rating": None, "rating_count": 0}),
        FakeResult(rows=[]),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 200
    assert response.json()["ratings"] == {"averageRating": None, "ratingCount": 0, "recent": []}


def test_public_profile_without_any_summary_row_still_returns_a_non_null_ratings_object():
    session = FakeSession([
        FakeResult(row=PROFILE),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(row=None),
        FakeResult(rows=[]),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 200
    assert response.json()["ratings"] == {"averageRating": None, "ratingCount": 0, "recent": []}


def test_non_public_profile_is_rejected_before_rating_queries():
    session = FakeSession([FakeResult(row=None)])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 404
    assert len(session.statements) == 1


def test_independent_driver_public_name_uses_real_name_not_profile_handle():
    profile = {
        **PROFILE,
        "kind": "independent_driver",
        "provider_name": "Fletes Pedro",
        "owner_first_name": "Pedro",
        "owner_last_name": "Soto",
    }
    session = FakeSession([
        FakeResult(row=profile),
        FakeResult(rows=[{"first_name": "Pedro", "last_name": "Soto", "is_owner": True}]),
        FakeResult(rows=[{"service_type_id": SERVICE_TYPE_ID, "name": "Fletes"}]),
        FakeResult(rows=[]),
        FakeResult(row={"average_rating": None, "rating_count": 0}),
        FakeResult(rows=[]),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 200
    assert response.json()["providerName"] == "Pedro Soto"
    assert response.json()["drivers"] == [{"firstName": "Pedro", "lastName": "Soto", "isOwner": True}]
    assert "Fletes Pedro" not in response.text
    driver_query = str(session.statements[1].compile(dialect=postgresql.dialect()))
    assert '"Perfil"."ID_user"' in driver_query
    assert '"Conductor"."ID_perfil" IS NULL' in driver_query


@pytest.mark.parametrize("profile_row", [None, {**PROFILE, "public_activated_at": None}])
def test_missing_or_inactive_public_profile_is_hidden(profile_row):
    session = FakeSession([FakeResult(row=profile_row)])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 404
    assert session.committed is False


def test_quote_request_requires_authentication():
    session = FakeSession()

    response = run_request("POST", "/api/service-requests", session, json_body={
        "profileId": str(PROFILE_ID),
        "serviceTypeId": str(SERVICE_TYPE_ID),
        "origin": "Santiago",
        "destination": "Valparaíso", "originCommuneCode": "13101", "destinationCommuneCode": "05101",
    }, authenticated=False, reject_unauthenticated=True)

    assert response.status_code == 401


def test_quote_request_uses_server_account_actor_and_creates_only_request():
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(scalar=SERVICE_TYPE_ID),
        FakeResult(rows=[("13101",), ("05101",)]),
    ])
    body = {
        "profileId": str(PROFILE_ID),
        "serviceTypeId": str(SERVICE_TYPE_ID),
        "origin": " Santiago ",
        "destination": "Valparaíso", "originCommuneCode": "13101", "destinationCommuneCode": "05101",
        "requestedAt": "2026-11-08T10:00:00-03:00",
        "estimatedWeight": "250.50",
        "estimatedVolume": "2.125",
        "description": "Retiro de muebles.",
        "cargoMeasurements": "Sofá y dos cajas.",
    }

    response = run_request("POST", "/api/service-requests", session, json_body=body)

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert session.committed
    assert len(session.added) == 1
    created = session.added[0]
    assert isinstance(created, FormularioServicio)
    assert created.customer_id == ACCOUNT_ID
    assert created.customer_id != AUTH_USER_ID
    assert created.profile_id == PROFILE_ID
    assert created.service_type_id == SERVICE_TYPE_ID
    assert created.origin == "Santiago"
    assert created.destination == "Valparaíso"
    assert created.origin_commune_code == "13101"
    assert created.destination_commune_code == "05101"
    assert created.status == "pending"
    assert created.requested_trip_id is None
    assert created.is_exclusive is False
    assert "chat" not in response.text.lower()
    assert "quote" not in response.text.lower()


@pytest.mark.parametrize("role", ["company_owner", "independent_driver", "company_driver", "demo_fixture"])
def test_non_customer_roles_cannot_create_quote_requests(role):
    session = FakeSession([FakeResult(row=(ACCOUNT_ID, role))])

    response = run_request("POST", "/api/service-requests", session, json_body={
        "profileId": str(PROFILE_ID),
        "serviceTypeId": str(SERVICE_TYPE_ID),
        "origin": "Santiago",
        "destination": "Valparaíso", "originCommuneCode": "13101", "destinationCommuneCode": "05101",
    })

    assert response.status_code == 403
    assert session.added == []
    assert not session.committed


def test_quote_request_rejects_unavailable_profile_service_without_persisting():
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(scalar=None),
    ])

    response = run_request("POST", "/api/service-requests", session, json_body={
        "profileId": str(PROFILE_ID),
        "serviceTypeId": str(SERVICE_TYPE_ID),
        "origin": "Santiago",
        "destination": "Valparaíso", "originCommuneCode": "13101", "destinationCommuneCode": "05101",
    })

    assert response.status_code == 404
    assert session.added == []
    assert not session.committed


def test_profile_owner_can_assign_only_a_driver_from_their_provider_profile():
    service = Servicio(id=uuid4(), profile_id=PROFILE_ID, contracted_driver_id=None)
    driver = Conductor(id=uuid4(), user_id=uuid4(), employer_profile_id=PROFILE_ID, driver_type_id=uuid4())
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "company_owner")),
        FakeResult(scalar=PROFILE_ID),
        FakeResult(scalar=service),
        FakeResult(scalar=driver),
    ])

    response = run_request("PUT", f"/api/provider/services/{service.id}/driver", session, json_body={"driverId": str(driver.id)})

    assert response.status_code == 200
    assert response.json() == {"serviceId": str(service.id), "driverId": str(driver.id)}
    assert service.contracted_driver_id == driver.id
    assert session.committed


def test_profile_owner_cannot_assign_a_driver_from_another_company():
    service = Servicio(id=uuid4(), profile_id=PROFILE_ID, contracted_driver_id=None)
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "company_owner")),
        FakeResult(scalar=PROFILE_ID),
        FakeResult(scalar=service),
        FakeResult(scalar=None),
    ])

    response = run_request("PUT", f"/api/provider/services/{service.id}/driver", session, json_body={"driverId": str(uuid4())})

    assert response.status_code == 404
    assert service.contracted_driver_id is None
    assert not session.committed


def test_company_owner_cannot_assign_their_driver_record_when_it_is_linked_to_another_profile():
    other_profile_id = UUID("4fab3c4d-8f5f-48ea-8ce2-c5187e8e97cd")
    service = Servicio(id=uuid4(), profile_id=PROFILE_ID, contracted_driver_id=None)
    foreign_linked_owner_driver = Conductor(
        id=uuid4(),
        user_id=ACCOUNT_ID,
        employer_profile_id=other_profile_id,
        driver_type_id=uuid4(),
    )
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "company_owner")),
        FakeResult(scalar=PROFILE_ID),
        FakeResult(scalar=service),
        # A database honors the ownership predicate and therefore does not return
        # this otherwise matching owner record.
        FakeResult(scalar=None),
    ])

    response = run_request(
        "PUT",
        f"/api/provider/services/{service.id}/driver",
        session,
        json_body={"driverId": str(foreign_linked_owner_driver.id)},
    )

    assert response.status_code == 404
    assert service.contracted_driver_id is None
    assert not session.committed
    driver_query = session.statements[-1]
    compiled_query = driver_query.compile(dialect=postgresql.dialect())
    sql = str(compiled_query)
    assert '"Conductor"."ID_user"' in sql
    assert '"Conductor"."ID_perfil" IS NULL' in sql
    assert '"Conductor"."ID_perfil" =' in sql
    assert PROFILE_ID in compiled_query.params.values()


def test_company_driver_cannot_assign_services_or_act_as_provider_owner():
    service = Servicio(id=uuid4(), profile_id=PROFILE_ID, contracted_driver_id=None)
    session = FakeSession([FakeResult(row=(ACCOUNT_ID, "company_driver"))])

    response = run_request("PUT", f"/api/provider/services/{service.id}/driver", session, json_body={"driverId": str(uuid4())})

    assert response.status_code == 403
    assert service.contracted_driver_id is None
    assert not session.committed


BASE_QUOTE_BODY = {
    "profileId": str(PROFILE_ID),
    "serviceTypeId": str(SERVICE_TYPE_ID),
    "originCommuneCode": "13101",
    "destinationCommuneCode": "05101",
}


@pytest.mark.parametrize("body", [
    {**BASE_QUOTE_BODY, "originCommuneCode": None},
    {key: value for key, value in BASE_QUOTE_BODY.items() if key != "destinationCommuneCode"},
    {**BASE_QUOTE_BODY, "destinationCommuneCode": "5101"},
    {**BASE_QUOTE_BODY, "originCommuneCode": "13A01"},
    {**BASE_QUOTE_BODY, "origin": "x" * 301},
    {**BASE_QUOTE_BODY, "estimatedWeight": -1},
    {**BASE_QUOTE_BODY, "requestedAt": "2026-11-08T10:00:00"},
    {**BASE_QUOTE_BODY, "requestedAt": "2020-01-01T10:00:00+00:00"},
    {**BASE_QUOTE_BODY, "customerId": str(AUTH_USER_ID)},
])
def test_quote_request_validates_required_fields_and_rejects_client_controlled_actor(body):
    session = FakeSession()

    response = run_request("POST", "/api/service-requests", session, json_body=body)

    assert response.status_code == 422
    assert session.added == []
    assert not session.committed


def test_quote_request_treats_blank_street_address_as_absent_and_keeps_commune_codes():
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(scalar=SERVICE_TYPE_ID),
        FakeResult(rows=[("13101",), ("05101",)]),
    ])

    response = run_request("POST", "/api/service-requests", session, json_body={**BASE_QUOTE_BODY, "origin": "  "})

    assert response.status_code == 201
    created = session.added[0]
    assert created.origin is None
    assert created.origin_commune_code == "13101"


def test_quote_request_rejects_commune_codes_missing_from_the_catalog_without_persisting():
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(scalar=SERVICE_TYPE_ID),
        FakeResult(rows=[("13101",)]),
    ])

    response = run_request("POST", "/api/service-requests", session, json_body=BASE_QUOTE_BODY | {"destinationCommuneCode": "99999"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "destinationCommuneCode"]
    assert session.added == []
    assert not session.committed

