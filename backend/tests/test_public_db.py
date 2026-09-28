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


def test_rls_migration_covers_all_26_tables_and_alembic_history() -> None:
    migration = load_public_migration()

    assert len(Base.metadata.tables) == 26
    assert set(migration.PUBLIC_TABLES) - {"alembic_version"} == set(Base.metadata.tables)
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
