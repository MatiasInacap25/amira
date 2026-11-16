"""Migration structure: additive audit, retained status compatibility and safe rollback."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock
from amira_api.models import Servicio

PATH = Path(__file__).parents[1] / "alembic/versions/20261116_0001_service_cancellation.py"

def load():
    spec = importlib.util.spec_from_file_location("cancellation_migration", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_additive_migration_matches_model_and_keeps_existing_rows():
    module = load()
    assert module.down_revision == "20261113_0001"
    module.op = Mock()
    module.upgrade()
    columns = [call.args[1] for call in module.op.add_column.call_args_list]
    assert {column.name for column in columns} == {"Fecha_Cancelacion", "Cancelado_Por", "Monto_Devuelto_Cancelacion", "Monto_Retenido_Cancelacion"}
    assert all(column.nullable for column in columns)
    assert all(column.name in Servicio.__table__.c for column in columns)
    condition = module.op.create_check_constraint.call_args.args[2]
    assert all(f"'{status}'" in condition for status in ("confirmed", "in_progress", "completed", "disputed", "cancelled"))
    module.op.execute.assert_not_called()

def test_downgrade_checks_cancelled_rows_before_removing_audit():
    module = load()
    module.op = Mock()
    module.downgrade()
    calls = module.op.mock_calls
    assert calls[0][0] == "execute"
    assert "Cannot downgrade while cancelled services exist" in calls[0].args[0]
    assert len(module.op.drop_column.call_args_list) == 4
