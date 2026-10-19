import importlib.util
from pathlib import Path


MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261019_0001_chat_message_attachments.py"


def load_migration():
    spec = importlib.util.spec_from_file_location("chat_message_attachments", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_after_the_current_head():
    migration = load_migration()

    assert migration.revision == "20261019_0001"
    assert migration.down_revision == "20261011_0004"


def test_attachment_columns_are_nullable_and_named_in_the_spanish_erd_style():
    migration = load_migration()

    assert migration.ATTACHMENT_COLUMNS == ("Adjunto_Clave", "Adjunto_Tipo", "Adjunto_Bytes")


def test_checks_are_added_not_valid_then_validated():
    migration = load_migration()
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    upgrade = source.split("def upgrade() -> None:", 1)[1].split("def downgrade() -> None:", 1)[0]

    assert migration.CONTENT_CHECK == "ck_message_text_or_attachment"
    assert migration.ALL_OR_NONE_CHECK == "ck_message_attachment_all_or_none"
    for name in ("CONTENT_CHECK", "ALL_OR_NONE_CHECK"):
        assert f"ADD CONSTRAINT {{{name}}}" in upgrade
        assert f"VALIDATE CONSTRAINT {{{name}}}" in upgrade
    assert upgrade.index("NOT VALID") < upgrade.index("VALIDATE CONSTRAINT")


def test_content_check_requires_text_or_an_attachment():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "btrim" in source
    assert '"Adjunto_Clave" IS NOT NULL' in source


def test_downgrade_drops_the_checks_and_the_columns():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", 1)[1]

    assert "DROP CONSTRAINT {CONTENT_CHECK}" in downgrade
    assert "DROP CONSTRAINT {ALL_OR_NONE_CHECK}" in downgrade
    assert "DROP COLUMN" in downgrade
