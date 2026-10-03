from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import FormularioServicio

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

    def execute(self, statement):
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
        FakeResult(rows=[{"first_name": "Pedro", "last_name": "Soto"}]),
        FakeResult(rows=[{"service_type_id": SERVICE_TYPE_ID, "name": "Mudanzas"}]),
        FakeResult(rows=[{"brand": "Volvo", "model": "FH", "year": 2022, "maximum_weight": "18000.00"}]),
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
        "ownerName": "Ana Pérez",
        "drivers": [{"firstName": "Pedro", "lastName": "Soto"}],
        "services": [{"serviceTypeId": str(SERVICE_TYPE_ID), "name": "Mudanzas"}],
        "vehicles": [{"brand": "Volvo", "model": "FH", "year": 2022, "maximumWeight": "18000.00"}],
    }
    for private_field in ("nationalId", "birthDate", "email", "phone", "authUserId", "companyTaxId", "plate", "imageStorageKey", "logoStorageKey"):
        assert private_field not in response.text
    assert "user-chosen" not in response.text


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
        FakeResult(rows=[]),
        FakeResult(rows=[{"service_type_id": SERVICE_TYPE_ID, "name": "Fletes"}]),
        FakeResult(rows=[]),
    ])

    response = run_request("GET", f"/api/providers/{PROFILE_ID}", session, authenticated=False)

    assert response.status_code == 200
    assert response.json()["providerName"] == "Pedro Soto"
    assert "Fletes Pedro" not in response.text


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
        "destination": "Valparaíso",
    }, authenticated=False, reject_unauthenticated=True)

    assert response.status_code == 401


def test_quote_request_uses_server_account_actor_and_creates_only_request():
    session = FakeSession([
        FakeResult(row=(ACCOUNT_ID, "client")),
        FakeResult(scalar=SERVICE_TYPE_ID),
    ])
    body = {
        "profileId": str(PROFILE_ID),
        "serviceTypeId": str(SERVICE_TYPE_ID),
        "origin": " Santiago ",
        "destination": "Valparaíso",
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
        "destination": "Valparaíso",
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
        "destination": "Valparaíso",
    })

    assert response.status_code == 404
    assert session.added == []
    assert not session.committed


@pytest.mark.parametrize("body", [
    {"profileId": str(PROFILE_ID), "serviceTypeId": str(SERVICE_TYPE_ID), "origin": " ", "destination": "Valparaíso"},
    {"profileId": str(PROFILE_ID), "serviceTypeId": str(SERVICE_TYPE_ID), "origin": "Santiago", "destination": " "},
    {"profileId": str(PROFILE_ID), "serviceTypeId": str(SERVICE_TYPE_ID), "origin": "Santiago", "destination": "Valparaíso", "estimatedWeight": -1},
    {"profileId": str(PROFILE_ID), "serviceTypeId": str(SERVICE_TYPE_ID), "origin": "Santiago", "destination": "Valparaíso", "requestedAt": "2026-11-08T10:00:00"},
    {"profileId": str(PROFILE_ID), "serviceTypeId": str(SERVICE_TYPE_ID), "origin": "Santiago", "destination": "Valparaíso", "customerId": str(AUTH_USER_ID)},
])
def test_quote_request_validates_required_fields_and_rejects_client_controlled_actor(body):
    session = FakeSession()

    response = run_request("POST", "/api/service-requests", session, json_body=body)

    assert response.status_code == 422
    assert session.added == []
    assert not session.committed
