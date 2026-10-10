from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from amira_api.db import create_database_engine
from amira_api.models import Base


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

    assert len(Base.metadata.tables) == 31
    assert (
        (set(migration.PUBLIC_TABLES) - {"alembic_version"})
        | set(load_auth_migration().RLS_TABLES)
        | {"DriverInvitationAttempt"}
        | set(load_location_migration().RLS_TABLES)
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
