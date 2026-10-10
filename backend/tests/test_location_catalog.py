import asyncio
import importlib.util
from pathlib import Path

import httpx

from amira_api.db import get_db_session
from amira_api.main import app


MIGRATION_PATH = (
    Path(__file__).parents[1] / "alembic" / "versions" / "20261010_0001_location_catalog.py"
)


def load_catalog():
    spec = importlib.util.spec_from_file_location("location_catalog_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.REGIONS, module.COMMUNES


class FakeResult:
    def __init__(self, rows):
        self.rows = list(rows)

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement):
        return FakeResult(self.rows)


def run_get(path: str, rows) -> httpx.Response:
    session = FakeSession(rows)
    app.dependency_overrides[get_db_session] = lambda: session

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(path)

    try:
        return asyncio.run(request())
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_catalog_has_exactly_16_regions_and_346_communes() -> None:
    regions, communes = load_catalog()

    assert len(regions) == 16
    assert len(communes) == 346


def test_catalog_codes_are_well_formed_unique_and_nested() -> None:
    regions, communes = load_catalog()
    region_codes = {code for code, _ in regions}

    assert len(region_codes) == 16
    assert all(len(code) == 2 and code.isdigit() for code in region_codes)
    commune_codes = [code for code, _, _ in communes]
    assert len(set(commune_codes)) == len(commune_codes)
    for commune_code, name, region_code in communes:
        assert len(commune_code) == 5 and commune_code.isdigit()
        assert commune_code.startswith(region_code)
        assert region_code in region_codes
        assert name.strip() == name and name


def test_catalog_contains_seed_communes_used_by_demo_providers() -> None:
    _, communes = load_catalog()
    by_code = {code: name for code, name, _ in communes}

    assert by_code["13101"] == "Santiago"
    assert by_code["05101"] == "Valparaíso"


def test_locations_endpoint_returns_nested_regions_with_spanish_sorted_communes() -> None:
    # Rows arrive ordered by Regiones.Orden (north to south), as the SQL ORDER BY guarantees.
    rows = [
        {"region_code": "01", "region_name": "Tarapacá", "commune_code": "01101", "commune_name": "Iquique"},
        {"region_code": "13", "region_name": "Metropolitana de Santiago", "commune_code": "13201", "commune_name": "Ñuñoa"},
        {"region_code": "13", "region_name": "Metropolitana de Santiago", "commune_code": "13101", "commune_name": "Santiago"},
        {"region_code": "13", "region_name": "Metropolitana de Santiago", "commune_code": "13126", "commune_name": "Nos"},
    ]

    response = run_get("/api/locations", rows)

    assert response.status_code == 200
    assert "public" in response.headers["cache-control"]
    assert response.json() == {
        "regions": [
            {
                "code": "01",
                "name": "Tarapacá",
                "communes": [{"code": "01101", "name": "Iquique"}],
            },
            {
                "code": "13",
                "name": "Metropolitana de Santiago",
                "communes": [
                    {"code": "13126", "name": "Nos"},
                    {"code": "13201", "name": "Ñuñoa"},
                    {"code": "13101", "name": "Santiago"},
                ],
            },
        ]
    }


def test_demo_provider_backfill_codes_exist_in_the_catalog() -> None:
    _, communes = load_catalog()
    catalog_codes = {code for code, _, _ in communes}
    spec = importlib.util.spec_from_file_location(
        "provider_commune_codes_migration",
        Path(__file__).parents[1] / "alembic" / "versions" / "20261010_0002_provider_commune_codes.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert dict(module.DEMO_COMMUNE_BACKFILL) == {"Santiago": "13101", "Valparaíso": "05101"}
    assert set(dict(module.DEMO_COMMUNE_BACKFILL).values()) <= catalog_codes
    assert module.down_revision == "20261010_0001"


def test_regions_are_seeded_north_to_south_and_orden_matches_that_position() -> None:
    spec = importlib.util.spec_from_file_location("location_catalog_order", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.REGION_ORDER == ("15", "01", "02", "03", "04", "05", "13", "06", "07", "16", "08", "09", "14", "10", "11", "12")
    assert sorted(module.REGION_ORDER) == sorted(code for code, _ in module.REGIONS)
    for position, code in enumerate(module.REGION_ORDER, start=1):
        assert module.REGION_ORDER.index(code) + 1 == position


def test_locations_endpoint_orders_regions_by_orden_not_by_code() -> None:
    session_rows = [
        {"region_code": "15", "region_name": "Arica y Parinacota", "commune_code": "15101", "commune_name": "Arica"},
        {"region_code": "01", "region_name": "Tarapacá", "commune_code": "01101", "commune_name": "Iquique"},
    ]
    response = run_get("/api/locations", session_rows)

    assert [region["code"] for region in response.json()["regions"]] == ["15", "01"]

