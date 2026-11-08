import importlib.util
from pathlib import Path

from amira_api.models import Base

MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261108_0001_service_live_location.py"
RLS_TABLE = "Servicio_Ubicacion"


def load_migration():
    spec = importlib.util.spec_from_file_location("service_live_location", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_source() -> str:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    return source.split("def upgrade() -> None:", 1)[1].split("def downgrade() -> None:", 1)[0]


def test_migration_chains_after_the_chat_unread_head():
    migration = load_migration()

    assert migration.revision == "20261108_0001"
    assert migration.down_revision == "20261019_0002"


def test_location_table_keeps_at_most_one_row_per_service():
    table = Base.metadata.tables["Servicio_Ubicacion"]
    foreign_key = next(iter(table.foreign_keys))

    assert set(table.columns.keys()) == {
        "ID_Servicio", "Latitud", "Longitud", "Precision_Metros", "Fecha_Actualizacion",
    }
    assert [column.name for column in table.primary_key.columns] == ["ID_Servicio"]
    assert foreign_key.column.table.name == "Servicio"
    assert foreign_key.ondelete == "CASCADE"


def test_location_table_checks_coordinate_ranges_and_non_negative_accuracy():
    table = Base.metadata.tables["Servicio_Ubicacion"]

    assert {constraint.name for constraint in table.constraints if constraint.name and constraint.name.startswith("ck_")} == {
        "ck_service_location_latitude_range",
        "ck_service_location_longitude_range",
        "ck_service_location_accuracy_nonnegative",
    }


def test_location_table_gets_rls_and_revoked_client_privileges():
    migration = load_migration()
    upgrade = _upgrade_source()

    assert tuple(migration.RLS_TABLES) == (RLS_TABLE,)
    assert f'ALTER TABLE public."{RLS_TABLE}" ENABLE ROW LEVEL SECURITY' in upgrade
    assert f'REVOKE ALL PRIVILEGES ON TABLE public."{RLS_TABLE}" FROM anon' in upgrade
    assert f'REVOKE ALL PRIVILEGES ON TABLE public."{RLS_TABLE}" FROM authenticated' in upgrade


def test_downgrade_drops_the_location_table():
    downgrade = MIGRATION_PATH.read_text(encoding="utf-8").split("def downgrade() -> None:", 1)[1]

    assert 'drop_table("Servicio_Ubicacion")' in downgrade
