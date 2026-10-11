"""Structural guard: the started-by foreign key added by migration 0003 is validated in the same upgrade.

Migration 0003 adds ``fk_service_started_by`` as NOT VALID and then runs VALIDATE CONSTRAINT. This test keeps that
sequence from regressing. Migration 0004 later replaces the constraint with ON DELETE SET NULL, using the same sequence
(see test_started_by_set_null_migration.py).
"""

from pathlib import Path

from amira_api.models import Base

MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261011_0003_service_assignments.py"


def _upgrade_source() -> str:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    return source.split("def upgrade() -> None:", 1)[1].split("def downgrade() -> None:", 1)[0]


def _statement_containing(source: str, marker: str) -> str:
    """The single op.execute(...) call whose SQL contains ``marker``. NOT VALID is checked inside that call only."""
    matches = [chunk for chunk in source.split("op.execute(") if marker in chunk]
    assert len(matches) == 1, marker
    return matches[0]


def test_started_by_foreign_key_is_added_not_valid_then_validated():
    upgrade = _upgrade_source()

    assert "NOT VALID" in _statement_containing(upgrade, "ADD CONSTRAINT {STARTED_BY_FK} FOREIGN KEY")
    assert upgrade.index("ADD CONSTRAINT {STARTED_BY_FK}") < upgrade.index("VALIDATE CONSTRAINT {STARTED_BY_FK}")


def test_started_by_foreign_key_targets_usuario_and_is_declared_on_the_model():
    fks = {
        fk.name: fk.target_fullname
        for fk in Base.metadata.tables["Servicio"].foreign_keys
        if fk.name == "fk_service_started_by"
    }

    assert fks == {"fk_service_started_by": "Usuario.ID"}
