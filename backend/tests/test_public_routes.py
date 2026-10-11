import asyncio
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy.dialects import postgresql

from amira_api.db import get_db_session
from amira_api.main import app


class FakeResult:
    def __init__(self, *, scalar=None, rows=()):
        self.scalar = scalar
        self.rows = list(rows)

    def scalar_one(self):
        return self.scalar

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, results):
        self.results = iter(results)
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return next(self.results)


def run_get(path: str, results, *, sessions=None, **params) -> httpx.Response:
    session = FakeSession(results)
    app.dependency_overrides[get_db_session] = lambda: session
    if sessions is not None:
        sessions.append(session)

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(path, params=params)

    try:
        return asyncio.run(request())
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_services_returns_only_public_provider_and_service_fields() -> None:
    profile_id = UUID("be7374de-165b-4d95-8da6-9a08c233b003")
    service_id = UUID("ae7374de-165b-4d95-8da6-9a08c233b004")
    sessions = []
    response = run_get(
        "/api/services",
        [
            FakeResult(scalar=1),
            FakeResult(
                rows=[
                    {
                        "profile_id": profile_id,
                        "provider_name": "[DEMO] Transporte Prueba",
                        "category": "Mudanzas",
                        "description": "Servicio de demostración.",
                        "location": "Santiago, Metropolitana de Santiago",
                        "commune_code": "13101",
                        "commune_name": "Santiago",
                        "region_name": "Metropolitana de Santiago",
                        "services": [
                            {"serviceTypeId": str(service_id), "name": "Mudanzas"},
                        ],
                    }
                ]
            ),
        ],
        sessions=sessions,
        q="mudanza",
        limit=20,
        offset=0,
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "profileId": str(profile_id),
                "providerName": "[DEMO] Transporte Prueba",
                "category": "Mudanzas",
                "description": "Servicio de demostración.",
                "location": "Santiago, Metropolitana de Santiago",
                "communeCode": "13101",
                "communeName": "Santiago",
                "regionName": "Metropolitana de Santiago",
                "logoUrl": None,
                "services": [
                    {"serviceTypeId": str(service_id), "name": "Mudanzas"},
                ],
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
    }
    assert "logo_storage_key" not in response.text
    assert "company_tax_id" not in response.text
    count_sql = str(sessions[0].statements[0].compile(dialect=postgresql.dialect())).lower()
    page_sql = str(sessions[0].statements[1].compile(dialect=postgresql.dialect())).lower()
    assert "count(distinct" in count_sql
    assert "public_activated_at" in count_sql
    assert "group by" in page_sql
    assert " limit " in page_sql and " offset " in page_sql


def test_services_paginates_provider_profiles_and_keeps_total_independent_of_offers() -> None:
    profile_id = UUID("be7374de-165b-4d95-8da6-9a08c233b003")
    service_id = UUID("ae7374de-165b-4d95-8da6-9a08c233b004")
    response = run_get(
        "/api/services",
        [
            FakeResult(scalar=21),
            FakeResult(
                rows=[
                    {
                        "profile_id": profile_id,
                        "provider_name": "Ana Pérez",
                        "category": "Mudanzas",
                        "description": None,
                        "location": "Santiago",
                        "services": [{"serviceTypeId": str(service_id), "name": "Mudanzas"}],
                    }
                ]
            ),
        ],
        limit=20,
        offset=20,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 21
    assert body["limit"] == 20
    assert body["offset"] == 20
    assert [item["profileId"] for item in body["items"]] == [str(profile_id)]
    assert body["items"][0]["services"] == [{"serviceTypeId": str(service_id), "name": "Mudanzas"}]


def test_shared_routes_returns_ordered_public_stops_without_vehicle_or_driver() -> None:
    trip_id = UUID("c4ab4de6-4b14-4c5e-85c8-57306928c1dc")
    profile_id = UUID("be7374de-165b-4d95-8da6-9a08c233b003")
    departure = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    stop_time = datetime(2026, 10, 5, 14, tzinfo=timezone.utc)
    response = run_get(
        "/api/shared-routes",
        [
            FakeResult(scalar=1),
            FakeResult(
                rows=[
                    {
                        "trip_id": trip_id,
                        "profile_id": profile_id,
                        "provider_name": "[DEMO] Transporte Prueba",
                        "origin": "Santiago",
                        "destination": "Valparaíso",
                        "origin_commune_code": "13101",
                        "destination_commune_code": "05101",
                        "departure_at": departure,
                    }
                ]
            ),
            FakeResult(
                rows=[
                    {
                        "trip_id": trip_id,
                        "stop_number": 1,
                        "estimated_at": stop_time,
                    }
                ]
            ),
        ],
        originCommuneCode="13101",
        destinationCommuneCode="05101",
        departureFrom="2026-10-01T00:00:00Z",
        departureTo="2026-10-31T00:00:00Z",
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item == {
        "tripId": str(trip_id),
        "profileId": str(profile_id),
        "providerName": "[DEMO] Transporte Prueba",
        "origin": "Santiago",
        "destination": "Valparaíso",
        "originCommuneCode": "13101",
        "destinationCommuneCode": "05101",
        "departureAt": "2026-10-05T12:00:00Z",
        "stops": [
            {
                "stopNumber": 1,
                "estimatedAt": "2026-10-05T14:00:00Z",
            }
        ],
    }
    assert "driver" not in response.text.lower()
    assert "vehicle" not in response.text.lower()
    assert "address" not in response.text.lower()


def test_public_list_endpoints_reject_unbounded_page_sizes() -> None:
    response = run_get("/api/services", [], limit=51)

    assert response.status_code == 422


def test_shared_routes_reject_inverted_departure_window() -> None:
    response = run_get(
        "/api/shared-routes",
        [],
        departureFrom="2026-10-31T00:00:00Z",
        departureTo="2026-10-01T00:00:00Z",
    )

    assert response.status_code == 422


def test_shared_routes_reject_timezone_naive_departure_filter() -> None:
    response = run_get(
        "/api/shared-routes",
        [],
        departureFrom="2026-10-01T00:00:00",
    )

    assert response.status_code == 422


def test_services_filters_by_region_and_commune_codes_and_returns_commune_labels() -> None:
    profile_id = UUID("be7374de-165b-4d95-8da6-9a08c233b003")
    service_id = UUID("ae7374de-165b-4d95-8da6-9a08c233b004")
    sessions = []
    response = run_get(
        "/api/services",
        [
            FakeResult(scalar=1),
            FakeResult(
                rows=[
                    {
                        "profile_id": profile_id,
                        "provider_name": "Ana Pérez",
                        "category": "Mudanzas",
                        "description": None,
                        "location": "Valparaíso, Valparaíso",
                        "commune_code": "05101",
                        "commune_name": "Valparaíso",
                        "region_name": "Valparaíso",
                        "services": [{"serviceTypeId": str(service_id), "name": "Mudanzas"}],
                    }
                ]
            ),
        ],
        sessions=sessions,
        regionCode="05",
        communeCode="05101",
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["communeCode"] == "05101"
    assert item["communeName"] == "Valparaíso"
    assert item["regionName"] == "Valparaíso"
    assert item["location"] == "Valparaíso, Valparaíso"
    count_params = set(sessions[0].statements[0].compile(dialect=postgresql.dialect()).params.values())
    assert {"05", "05101"} <= count_params
    count_sql = str(sessions[0].statements[0].compile(dialect=postgresql.dialect())).lower()
    assert "codigo_region" in count_sql
    assert "comunas" in count_sql


def test_services_rejects_malformed_region_and_commune_codes() -> None:
    assert run_get("/api/services", [], regionCode="5").status_code == 422
    assert run_get("/api/services", [], communeCode="1310").status_code == 422
    assert run_get("/api/services", [], communeCode="13A01").status_code == 422


def test_shared_routes_filter_by_commune_codes_and_keep_legacy_rows_without_codes() -> None:
    sessions = []
    response = run_get(
        "/api/shared-routes",
        [
            FakeResult(scalar=0),
            FakeResult(rows=[]),
        ],
        sessions=sessions,
        originCommuneCode="13101",
        destinationCommuneCode="05101",
    )

    assert response.status_code == 200
    count_params = set(sessions[0].statements[0].compile(dialect=postgresql.dialect()).params.values())
    assert {"13101", "05101"} <= count_params
    count_sql = str(sessions[0].statements[0].compile(dialect=postgresql.dialect())).lower()
    assert "codigo_comuna_origen" in count_sql
    assert "codigo_comuna_destino" in count_sql


def test_shared_routes_reject_malformed_commune_codes() -> None:
    assert run_get("/api/shared-routes", [], originCommuneCode="131").status_code == 422
    assert run_get("/api/shared-routes", [], destinationCommuneCode="0510A").status_code == 422

