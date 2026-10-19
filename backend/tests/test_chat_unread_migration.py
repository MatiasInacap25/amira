import importlib.util
from pathlib import Path


MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261019_0002_chat_participant_last_read.py"


def load_migration():
    spec = importlib.util.spec_from_file_location("chat_participant_last_read", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_after_the_attachment_migration():
    migration = load_migration()

    assert migration.revision == "20261019_0002"
    assert migration.down_revision == "20261019_0001"


def test_last_read_column_is_timestamptz_not_null_with_now_default():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    upgrade = source.split("def upgrade() -> None:", 1)[1].split("def downgrade() -> None:", 1)[0]

    assert 'ADD COLUMN "Ultima_Lectura" TIMESTAMPTZ NOT NULL DEFAULT now()' in upgrade
    assert 'ON public."Chat_participantes"' in upgrade or 'public."Chat_participantes"' in upgrade


def test_downgrade_drops_only_the_last_read_column():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", 1)[1]

    assert 'DROP COLUMN "Ultima_Lectura"' in downgrade
    assert "Chat_participantes" in downgrade
    assert "DROP TABLE" not in downgrade
