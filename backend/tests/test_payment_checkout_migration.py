import importlib.util
import re
from pathlib import Path


MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261011_0002_payment_checkout_consumed.py"


def load_migration():
    spec = importlib.util.spec_from_file_location("payment_checkout_consumed", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_after_the_quotation_status_check():
    migration = load_migration()

    assert migration.revision == "20261011_0002"
    assert migration.down_revision == "20261011_0001"


def test_upgrade_adds_a_nullable_consumption_timestamp_to_pago():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    upgrade = source.split("def upgrade() -> None:", 1)[1].split("def downgrade() -> None:", 1)[0]

    assert re.search(r'ALTER TABLE public\."Pago" ADD COLUMN "Fecha_Token_Usado" TIMESTAMP WITH TIME ZONE NULL', upgrade)


def test_downgrade_drops_the_column():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", 1)[1]

    assert 'DROP COLUMN "Fecha_Token_Usado"' in downgrade
