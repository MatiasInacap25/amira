from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import postgres_support
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import create_database_engine, get_db_session
from amira_api.main import app
from amira_api.models import Base, Commune, Perfil, Region, RolPerfil, RolUsuario, TipoServicio, Usuario
from postgres_support import (
    REDIRECTING_ENVIRONMENT_VARIABLES,
    REDIRECTING_QUERY_KEYS,
    destructive_test_skip_reason,
    disposable_test_database_url,
    disposable_test_engine,
)

# The public search query uses PostgreSQL-only SQL (json_agg, aggregate_order_by), so this test needs a real database.
# It drops and recreates PUBLIC_SEARCH_TABLES, so AMIRA_TEST_DATABASE_URL must point at a disposable local database
# (guard and engine live in postgres_support).
PUBLIC_SEARCH_TABLES = (
    "Regiones",
    "Comunas",
    "Rol_Usuario",
    "Usuario",
    "Rol_Perfil",
    "Perfil",
    "Tipos_Servicio",
    "Servicios_Disponibles",
)


def load_public_migration():
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "20260927_0002_public_browse_rls_and_demo_seed.py"
    spec = spec_from_file_location("public_browse_migration", migration_path)
    migration = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


def test_database_engine_forces_psycopg_tls_and_bounded_timeouts(monkeypatch) -> None:
    captured = {}

    class FakeEngine:
        url = None
        pool = None

        def dispose(self):
            return None

    def capture_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        engine = FakeEngine()
        engine.url = url
        return engine

    monkeypatch.setattr("amira_api.db.create_engine", capture_engine)
    engine = create_database_engine("postgresql://amira:secret@db.example.test:5432/postgres")

    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.query["sslmode"] == "require"
        args = captured["kwargs"]["connect_args"]
        assert args["sslmode"] == "require"
        assert args["connect_timeout"] == 10
        assert args["options"] == "-c statement_timeout=5000"
        assert captured["kwargs"]["pool_timeout"] == 10
        assert captured["kwargs"]["pool_size"] == 5
        assert captured["kwargs"]["max_overflow"] == 5
    finally:
        engine.dispose()


def test_rls_migrations_cover_all_tables_and_alembic_history() -> None:
    migration = load_public_migration()

    assert len(Base.metadata.tables) == 33
    assert (
        (set(migration.PUBLIC_TABLES) - {"alembic_version"})
        | set(load_auth_migration().RLS_TABLES)
        | {"DriverInvitationAttempt"}
        | set(load_location_migration().RLS_TABLES)
        | set(load_service_assignment_migration().RLS_TABLES)
        | set(load_live_location_migration().RLS_TABLES)
    ) == set(Base.metadata.tables)
    assert "alembic_version" in migration.PUBLIC_TABLES


def test_demo_seed_is_labeled_and_does_not_create_auth_or_payment_records() -> None:
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "20260927_0002_public_browse_rls_and_demo_seed.py"
    source = migration_path.read_text(encoding="utf-8")

    assert "[DEMO]" in source
    assert "example.invalid" in source
    assert 'INSERT INTO public."Verificacion_Identidad"' not in source
    assert 'INSERT INTO auth.users' not in source
    assert 'INSERT INTO public."Pago"' not in source
    assert 'INSERT INTO public."Desembolso"' not in source


def load_location_migration():
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "20261010_0001_location_catalog.py"
    spec = spec_from_file_location("location_catalog_migration", migration_path)
    migration = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


def load_service_assignment_migration():
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "20261011_0003_service_assignments.py"
    spec = spec_from_file_location("service_assignment_migration", migration_path)
    migration = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


def load_live_location_migration():
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "20261108_0001_service_live_location.py"
    spec = spec_from_file_location("service_live_location_migration", migration_path)
    migration = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


def load_auth_migration():
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "20260928_0003_auth_profile_and_challenge_schema.py"
    spec = spec_from_file_location("auth_profile_migration", migration_path)
    migration = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


def test_auth_migration_fails_closed_for_unrecognized_role_labels_and_protects_new_tables() -> None:
    migration = load_auth_migration()
    source = Path(migration.__file__).read_text(encoding="utf-8")

    assert migration.RLS_TABLES == ("DriverInvitation", "EmailFallbackChallenge")
    assert "Unrecognized existing role labels" in source
    assert "[DEMO] fixture owner" in source
    assert "[DEMO] proveedor de prueba" in source
    assert "REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC" in source
    assert "REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon" in source
    assert "REVOKE ALL PRIVILEGES ON TABLE public.%I FROM authenticated" in source
    assert "Cannot downgrade: independent drivers require nullable Conductor.ID_perfil" in source
    assert "independent or activated profile state would be lost" in source
    assert "invitation or fallback challenge records would be lost" in source


class AlembicOperationRecorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record


def test_role_seed_codes_survive_upgrade_downgrade_upgrade_structurally() -> None:
    migration = load_auth_migration()
    recorder = AlembicOperationRecorder()
    original_op = migration.op
    migration.op = recorder

    try:
        migration.upgrade()
        first_upgrade = [args[0] for name, args, _ in recorder.calls if name == "execute" and args]
        recorder.calls.clear()

        migration.downgrade()
        downgrade_calls = list(recorder.calls)
        recorder.calls.clear()

        migration.upgrade()
        second_upgrade = [args[0] for name, args, _ in recorder.calls if name == "execute" and args]
    finally:
        migration.op = original_op

    assert ("drop_column", ("Rol_Usuario", "code"), {}) in downgrade_calls
    assert ("drop_column", ("Rol_Perfil", "code"), {}) in downgrade_calls
    assert not any("DELETE FROM \"Rol_Usuario\"" in sql or "DELETE FROM \"Rol_Perfil\"" in sql for name, args, _ in downgrade_calls if name == "execute" for sql in args)

    for table, seeded_roles in (("Rol_Usuario", migration.ACCOUNT_ROLES), ("Rol_Perfil", migration.PROFILE_ROLES)):
        for role_id, code, name in seeded_roles:
            expected = f"""UPDATE "{table}" SET "code" = '{code}' WHERE "ID" = '{role_id}' AND "Rol" = '{name}'"""
            assert expected in first_upgrade
            assert expected in second_upgrade


def _public_search_ids(client: TestClient) -> list[str]:
    response = client.get("/api/services")

    assert response.status_code == 200
    return [item["profileId"] for item in response.json()["items"]]


def test_published_profile_appears_in_public_search_until_unpublished_or_left_incomplete() -> None:
    engine = disposable_test_engine(disposable_test_database_url())
    tables = [Base.metadata.tables[name] for name in PUBLIC_SEARCH_TABLES]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    driver_auth_id = uuid4()
    profile_id = uuid4()
    service_type_id = uuid4()

    try:
        with Session(engine) as session:
            user_role = RolUsuario(id=uuid4(), name="independent_driver", code="independent_driver")
            profile_role = RolPerfil(id=uuid4(), name="independent_driver", code="independent_driver")
            driver = Usuario(
                id=uuid4(),
                auth_user_id=driver_auth_id,
                first_name="Dana",
                last_name="Test",
                email="dana@example.test",
                role_id=user_role.id,
            )
            session.add_all([
                user_role,
                profile_role,
                Region(code="13", name="Metropolitana de Santiago", order=1),
                Commune(code="13101", region_code="13", name="Santiago"),
                driver,
                Perfil(
                    id=profile_id,
                    owner_user_id=driver.id,
                    name="Dana Fletes",
                    kind="independent_driver",
                    role_id=profile_role.id,
                ),
                TipoServicio(id=service_type_id, name="Mudanza", slug="mudanza"),
            ])
            session.commit()

            app.dependency_overrides[get_db_session] = lambda: session
            app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
                id=driver_auth_id,
                email="dana@example.test",
                session_id=uuid4(),
                assurance="aal2",
                authentication_methods=frozenset({"password", "phone"}),
            )
            try:
                client = TestClient(app)
                complete = {
                    "description": "Fletes en Santiago",
                    "commune_code": "13101",
                    "service_type_ids": [str(service_type_id)],
                }

                assert client.put("/api/provider/profile", json=complete).status_code == 200
                assert _public_search_ids(client) == []

                assert client.post("/api/provider/profile/publish").status_code == 200
                assert _public_search_ids(client) == [str(profile_id)]

                assert client.post("/api/provider/profile/unpublish").status_code == 200
                assert _public_search_ids(client) == []

                assert client.post("/api/provider/profile/publish").status_code == 200
                assert _public_search_ids(client) == [str(profile_id)]

                response = client.put("/api/provider/profile", json={**complete, "description": ""})

                assert response.status_code == 200
                assert response.json()["published"] is False
                assert response.json()["missing"] == ["description"]
                assert _public_search_ids(client) == []
            finally:
                app.dependency_overrides.pop(get_db_session, None)
                app.dependency_overrides.pop(get_current_user, None)
    finally:
        Base.metadata.drop_all(engine, tables=tables)
        engine.dispose()


@pytest.fixture
def clean_pg_environment(monkeypatch):
    for name in REDIRECTING_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("database_url", [
    "postgresql://amira:secret@localhost:5432/amira_test",
    "postgresql+psycopg://amira:secret@127.0.0.1/amira_test",
    "postgresql://amira:secret@[::1]:5432/amira_test",
])
def test_destructive_test_guard_accepts_the_three_allowlisted_hosts(clean_pg_environment, database_url) -> None:
    assert destructive_test_skip_reason(database_url) is None


@pytest.mark.parametrize("database_url", [
    "postgresql:///amira_test",
    "postgresql://amira@/amira_test?host=/var/run/postgresql",
    "postgresql://amira@localhost,127.0.0.1/amira_test",
    "postgresql://amira:secret@db.example.test:5432/amira",
    "postgresql://amira@127.0.0.2/amira_test",
    "not a database url",
])
def test_destructive_test_guard_rejects_hosts_outside_the_allowlist(clean_pg_environment, database_url) -> None:
    assert destructive_test_skip_reason(database_url) is not None


@pytest.mark.parametrize("key", REDIRECTING_QUERY_KEYS)
def test_destructive_test_guard_rejects_redirecting_url_query_keys(clean_pg_environment, key) -> None:
    reason = destructive_test_skip_reason(f"postgresql://amira@localhost/amira_test?{key}=value")

    assert reason is not None
    assert key in reason


@pytest.mark.parametrize("name", REDIRECTING_ENVIRONMENT_VARIABLES)
def test_destructive_test_guard_rejects_redirecting_environment_variables(clean_pg_environment, name) -> None:
    clean_pg_environment.setenv(name, "anything")

    reason = destructive_test_skip_reason("postgresql://amira@localhost/amira_test")

    assert reason is not None
    assert name in reason


def test_destructive_test_is_skipped_for_remote_database_before_any_engine_is_created(monkeypatch) -> None:
    def fail_if_engine_created(*args, **kwargs):
        raise AssertionError("the guard must skip before any engine is created")

    monkeypatch.setenv(postgres_support.PUBLIC_SEARCH_TEST_DATABASE_ENV, "postgresql://amira:secret@db.example.test:5432/amira")
    monkeypatch.setattr("postgres_support.create_engine", fail_if_engine_created)

    with pytest.raises(pytest.skip.Exception, match="explicit host"):
        test_published_profile_appears_in_public_search_until_unpublished_or_left_incomplete()


def test_destructive_test_is_skipped_when_database_url_is_unset(monkeypatch) -> None:
    monkeypatch.delenv(postgres_support.PUBLIC_SEARCH_TEST_DATABASE_ENV, raising=False)

    with pytest.raises(pytest.skip.Exception, match="is not set"):
        test_published_profile_appears_in_public_search_until_unpublished_or_left_incomplete()
