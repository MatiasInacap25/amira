from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from amira_api.models import EmailFallbackChallenge


def load_migration():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "20260928_0004_email_fallback_proofs.py"
    spec = spec_from_file_location("email_fallback_proofs_migration", path)
    migration = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


class OperationRecorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record


def test_fallback_model_persists_identity_and_one_use_proof_state():
    columns = EmailFallbackChallenge.__table__.c

    assert columns.auth_user_id.nullable is False
    assert columns.user_id.nullable is True
    assert columns.activated_at.nullable is True
    assert columns.proof_hash.nullable is True
    assert columns.proof_expires_at.nullable is True
    assert columns.proof_consumed_at.nullable is True
    assert any(index.name == "ix_email_fallback_auth_session_created" for index in EmailFallbackChallenge.__table__.indexes)


def test_fallback_proof_migration_backfills_and_guards_rollback():
    migration = load_migration()
    recorder = OperationRecorder()
    original = migration.op
    migration.op = recorder
    try:
        migration.upgrade()
        upgrade = list(recorder.calls)
        recorder.calls.clear()
        migration.downgrade()
        downgrade = list(recorder.calls)
    finally:
        migration.op = original

    sql = [args[0] for name, args, _ in upgrade if name == "execute"]
    assert any('"ID_Auth_Supabase"' in statement for statement in sql)
    assert any('WHERE "auth_user_id" IS NULL' in statement for statement in sql)
    assert ("alter_column", ("EmailFallbackChallenge", "user_id"), {"nullable": True}) in upgrade
    assert any(
        name == "execute" and "unprovisioned identity or fallback proof state would be lost" in args[0]
        for name, args, _ in downgrade
    )
