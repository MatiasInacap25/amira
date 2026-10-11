import importlib.util
from pathlib import Path

from amira_api.models import Base

MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261011_0003_service_assignments.py"
SERVICE_STATUSES = {"confirmed", "in_progress", "completed", "disputed"}


def load_migration():
    spec = importlib.util.spec_from_file_location("service_assignments", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_source() -> str:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    return source.split("def upgrade() -> None:", 1)[1].split("def downgrade() -> None:", 1)[0]


def test_migration_chains_after_the_checkout_consumption_column():
    migration = load_migration()

    assert migration.revision == "20261011_0003"
    assert migration.down_revision == "20261011_0002"


def test_assignment_table_is_unique_per_service_driver_and_service_vehicle():
    table = Base.metadata.tables["Servicio_Asignacion"]
    uniques = {
        constraint.name: [column.name for column in constraint.columns]
        for constraint in table.constraints
        if constraint.name and constraint.name.startswith("uq_")
    }

    assert set(table.columns.keys()) == {
        "ID", "ID_Servicio", "ID_Conductor", "ID_Vehiculo", "Fecha_Asignacion", "ID_Usuario_Asigna",
    }
    assert uniques == {
        "uq_service_assignment_driver": ["ID_Servicio", "ID_Conductor"],
        "uq_service_assignment_vehicle": ["ID_Servicio", "ID_Vehiculo"],
    }
    upgrade = _upgrade_source()
    assert "uq_service_assignment_driver" in upgrade and "uq_service_assignment_vehicle" in upgrade


def test_assignment_table_gets_rls_and_revoked_client_privileges():
    migration = load_migration()
    upgrade = _upgrade_source()

    assert tuple(migration.RLS_TABLES) == ("Servicio_Asignacion",)
    assert 'ALTER TABLE public."Servicio_Asignacion" ENABLE ROW LEVEL SECURITY' in upgrade
    assert 'REVOKE ALL PRIVILEGES ON TABLE public."Servicio_Asignacion" FROM anon' in upgrade
    assert 'REVOKE ALL PRIVILEGES ON TABLE public."Servicio_Asignacion" FROM authenticated' in upgrade


def test_service_status_check_is_added_not_valid_then_validated():
    migration = load_migration()
    upgrade = _upgrade_source()
    service = Base.metadata.tables["Servicio"]

    assert set(migration.SERVICE_STATUSES) == SERVICE_STATUSES
    assert "ck_service_status_allowed" in {constraint.name for constraint in service.constraints}
    # NOT VALID must belong to the status CHECK statement itself, not to the started-by foreign key added earlier.
    status_statements = [chunk for chunk in upgrade.split("op.execute(") if "ADD CONSTRAINT {STATUS_CONSTRAINT}" in chunk]
    assert len(status_statements) == 1
    assert "NOT VALID" in status_statements[0]
    assert upgrade.index("ADD CONSTRAINT {STATUS_CONSTRAINT}") < upgrade.index("VALIDATE CONSTRAINT {STATUS_CONSTRAINT}")


def test_service_records_who_started_it():
    service = Base.metadata.tables["Servicio"]

    assert service.columns["ID_Usuario_Inicio"].nullable is True
    assert 'ADD COLUMN "ID_Usuario_Inicio" UUID NULL' in _upgrade_source()


def test_downgrade_reverses_every_change():
    downgrade = MIGRATION_PATH.read_text(encoding="utf-8").split("def downgrade() -> None:", 1)[1]

    assert "DROP CONSTRAINT {STATUS_CONSTRAINT}" in downgrade
    assert 'DROP COLUMN "ID_Usuario_Inicio"' in downgrade
    assert 'drop_table("Servicio_Asignacion")' in downgrade
