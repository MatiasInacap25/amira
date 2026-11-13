import importlib.util
from pathlib import Path

from amira_api.models import Base

MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261113_0001_driver_certificate_verification.py"


def load_migration():
    spec = importlib.util.spec_from_file_location("driver_certificate_verification", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section(name: str) -> str:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    body = source.split(f"def {name}() -> None:", 1)[1]
    return body.split("\ndef ", 1)[0]


def test_migration_chains_after_the_live_location_head():
    migration = load_migration()
    assert migration.revision == "20261113_0001"
    assert migration.down_revision == "20261108_0001"


def test_identity_verification_gains_the_certificate_columns():
    columns = Base.metadata.tables["Verificacion_Identidad"].columns
    assert {"Tipo_Documento", "Anotaciones", "Clave_PDF", "Fecha_Revision"} <= set(columns.keys())
    upgrade = _section("upgrade")
    for column in ("Tipo_Documento", "Anotaciones", "Clave_PDF", "Fecha_Revision"):
        assert f'"{column}"' in upgrade


def test_new_checks_do_not_validate_existing_rows():
    upgrade = _section("upgrade")
    assert "ck_identity_verification_document_type" in upgrade
    assert "ck_identity_verification_status" in upgrade
    assert upgrade.count("NOT VALID") == 2


def test_downgrade_removes_what_the_upgrade_added():
    downgrade = _section("downgrade")
    for name in ("Tipo_Documento", "Anotaciones", "Clave_PDF", "Fecha_Revision", "ck_identity_verification_document_type",
                 "ck_identity_verification_status", "ix_identity_verification_user_document"):
        assert name in downgrade
