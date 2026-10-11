import asyncio
import importlib.util
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy.dialects import postgresql

from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import TipoServicio


MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261010_0003_service_type_slugs.py"


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


def load_migration():
    spec = importlib.util.spec_from_file_location("service_type_slugs_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_service_type_slug_is_unique_and_format_checked_in_the_model() -> None:
    table = TipoServicio.__table__
    constraint_names = {constraint.name for constraint in table.constraints}

    assert "uq_tipos_servicio_slug" in constraint_names
    assert "ck_tipos_servicio_slug_format" in constraint_names
    assert table.c.Slug.nullable is False


def test_service_type_slug_migration_chains_after_the_provider_commune_migration() -> None:
    migration = load_migration()

    assert migration.revision == "20261010_0003"
    assert migration.down_revision == "20261010_0002"


def test_service_types_endpoint_returns_slug_id_and_name() -> None:
    type_id = UUID("c3000000-0000-4000-8000-000000000001")
    response = run_get(
        "/api/service-types",
        [FakeResult(rows=[{"id": type_id, "slug": "mudanzas", "name": "Mudanzas"}])],
    )

    assert response.status_code == 200
    assert response.json() == {"items": [{"id": str(type_id), "slug": "mudanzas", "name": "Mudanzas"}]}


def test_services_filters_by_service_type_slug() -> None:
    sessions = []
    response = run_get(
        "/api/services",
        [FakeResult(scalar=0), FakeResult(rows=[])],
        sessions=sessions,
        serviceType="mudanzas",
    )

    assert response.status_code == 200
    count_params = set(sessions[0].statements[0].compile(dialect=postgresql.dialect()).params.values())
    assert "mudanzas" in count_params


def test_services_rejects_non_slug_service_type_values() -> None:
    assert run_get("/api/services", [], serviceType="Mudanzas").status_code == 422
    assert run_get("/api/services", [], serviceType="carga--compartida").status_code == 422
    assert run_get("/api/services", [], serviceType="x" * 121).status_code == 422
