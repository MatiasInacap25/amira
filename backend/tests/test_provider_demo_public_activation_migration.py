from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


class OperationRecorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


def test_demo_profile_activation_migration_is_narrow_and_null_guarded():
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20261003_0001_activate_demo_profile_publication.py"
    )
    spec = spec_from_file_location("demo_profile_activation_migration", path)
    migration = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    recorder = OperationRecorder()
    original = migration.op
    migration.op = recorder
    try:
        migration.upgrade()
    finally:
        migration.op = original

    statements = [args[0] for name, args, _ in recorder.calls if name == "execute"]
    assert len(statements) == 1
    statement = statements[0]
    assert 'UPDATE "Perfil"' in statement
    assert '"ID" = \'a1000000-0000-4000-8000-000000000004\'' in statement
    assert '"Nombre" = \'[DEMO] Transporte de prueba\'' in statement
    assert '"public_activated_at" IS NULL' in statement
