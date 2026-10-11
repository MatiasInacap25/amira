import importlib.util
import re
from pathlib import Path


MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261011_0001_quotation_status_check.py"
STATUSES = {"pending", "paid", "rejected", "expired", "superseded"}


def load_migration():
    spec = importlib.util.spec_from_file_location("quotation_status_check", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_after_the_current_head():
    migration = load_migration()

    assert migration.revision == "20261011_0001"
    assert migration.down_revision == "20261010_0006"


def test_status_check_allows_exactly_the_quotation_workflow_states():
    migration = load_migration()

    assert set(migration.QUOTATION_STATUSES) == STATUSES


def test_status_check_is_added_not_valid_then_validated():
    migration = load_migration()
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    upgrade = source.split("def upgrade() -> None:", 1)[1].split("def downgrade() -> None:", 1)[0]

    assert migration.CONSTRAINT_NAME == "ck_quote_status_allowed"
    assert re.search(r"ADD CONSTRAINT \{CONSTRAINT_NAME\} .*NOT VALID", upgrade, re.DOTALL)
    assert "VALIDATE CONSTRAINT {CONSTRAINT_NAME}" in upgrade
    assert upgrade.index("NOT VALID") < upgrade.index("VALIDATE CONSTRAINT")


def test_downgrade_drops_the_constraint():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", 1)[1]

    assert "DROP CONSTRAINT {CONSTRAINT_NAME}" in downgrade
