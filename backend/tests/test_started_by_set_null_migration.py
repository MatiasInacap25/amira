"""Structural guard: migration 20261011_0004 makes the started-by foreign key ON DELETE SET NULL.

The foreign key is replaced, not altered in place: it is dropped, added again as NOT VALID and then validated, so the
upgrade never scans the table under the exclusive lock. The downgrade restores ON DELETE RESTRICT the same way.
"""

import importlib.util
from pathlib import Path

from amira_api.models import Base

MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261011_0004_started_by_set_null.py"


def load_migration():
    spec = importlib.util.spec_from_file_location("started_by_set_null", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section(function_name: str) -> str:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    body = source.split(f"def {function_name}() -> None:", 1)[1]
    return body.split("\ndef ", 1)[0]


def test_migration_chains_after_the_service_assignment_migration():
    migration = load_migration()

    assert migration.revision == "20261011_0004"
    assert migration.down_revision == "20261011_0003"


def test_upgrade_drops_the_started_by_fk_then_adds_set_null_not_valid_then_validates():
    upgrade = _section("upgrade")

    drop = upgrade.index("DROP CONSTRAINT {STARTED_BY_FK}")
    add = upgrade.index("ADD CONSTRAINT {STARTED_BY_FK} FOREIGN KEY")
    not_valid = upgrade.index("ON DELETE SET NULL NOT VALID")
    validate = upgrade.index("VALIDATE CONSTRAINT {STARTED_BY_FK}")
    assert drop < add < not_valid < validate
    assert "ON DELETE RESTRICT" not in upgrade


def test_downgrade_restores_restrict_not_valid_then_validates():
    downgrade = _section("downgrade")

    drop = downgrade.index("DROP CONSTRAINT {STARTED_BY_FK}")
    add = downgrade.index("ADD CONSTRAINT {STARTED_BY_FK} FOREIGN KEY")
    not_valid = downgrade.index("ON DELETE RESTRICT NOT VALID")
    validate = downgrade.index("VALIDATE CONSTRAINT {STARTED_BY_FK}")
    assert drop < add < not_valid < validate
    assert "ON DELETE SET NULL" not in downgrade


def test_model_declares_the_started_by_fk_as_set_null():
    fks = {
        fk.name: (fk.target_fullname, fk.ondelete)
        for fk in Base.metadata.tables["Servicio"].foreign_keys
        if fk.name == "fk_service_started_by"
    }

    assert fks == {"fk_service_started_by": ("Usuario.ID", "SET NULL")}
