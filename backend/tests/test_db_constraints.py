import importlib.util
import re
from pathlib import Path

from amira_api.account_schemas import AccountProvisionRequest
from amira_api.models import Base


MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261010_0005_data_integrity_constraints.py"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "company_profile_demo.sql"

RUT_PATTERN = r"^\d{7,8}-[0-9K]$"
PHONE_PATTERN = r"^\+[1-9]\d{7,14}$"
SERVICE_REQUEST_STATUSES = ("pending", "accepted", "rejected")

# Regex CHECKs (RUT, phone) are PostgreSQL-only and are asserted against the migration instead.
REGEX_CHECKS = {"ck_usuario_rut_format", "ck_usuario_phone_format", "ck_perfil_company_tax_id_format"}
EXPECTED_CHECKS = {
    "Formulario_servicio": {"ck_form_status_allowed", "ck_form_volume_nonnegative"},
    "Cotizacion": {"ck_quote_currency_clp"},
    "Pago": {"ck_payment_currency_clp"},
    "Reembolso": {"ck_refund_currency_clp"},
    "Desembolso": {"ck_payout_currency_clp"},
}
EXPECTED_PARTIAL_UNIQUE = {
    "Usuario": {"uq_usuario_rut"},
    "Perfil": {"uq_perfil_rut_empresa"},
}


def load_migration_source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_integrity_checks_are_declared_on_the_mapped_tables() -> None:
    for table_name, expected in EXPECTED_CHECKS.items():
        table = Base.metadata.tables[table_name]
        names = {constraint.name for constraint in table.constraints if constraint.name and constraint.name.startswith("ck_")}
        assert expected <= names, table_name


def test_regex_checks_are_declared_in_the_migration_for_postgresql() -> None:
    source = load_migration_source()

    for name in REGEX_CHECKS:
        assert name in source, name


def test_rut_columns_have_partial_unique_indexes_that_allow_null() -> None:
    for table_name, expected in EXPECTED_PARTIAL_UNIQUE.items():
        table = Base.metadata.tables[table_name]
        indexes = {index.name: index for index in table.indexes if index.unique}
        assert expected <= set(indexes), table_name
        for name in expected:
            where = indexes[name].dialect_options["postgresql"]["where"]
            assert where is not None, name


def test_rut_pattern_accepts_normalized_values_and_rejects_display_or_demo_forms() -> None:
    for value in ("12345678-5", "76000000-0", "1234567-K"):
        assert re.fullmatch(RUT_PATTERN, value), value
    for value in ("DEMO-76000000", "12.345.678-5", "12345678-k", "12345678 5", "123456-5"):
        assert not re.fullmatch(RUT_PATTERN, value), value


def test_phone_pattern_matches_the_e164_form_used_by_provisioning() -> None:
    assert re.fullmatch(PHONE_PATTERN, "+56912345678")
    for value in ("+0912345678", "56912345678", "+56 9 1234 5678", "+1234"):
        assert not re.fullmatch(PHONE_PATTERN, value), value


def test_database_rut_pattern_matches_the_pattern_under_test() -> None:
    source = load_migration_source()

    assert RUT_PATTERN in source
    assert PHONE_PATTERN in source
    assert "[0-9K]" in source


def test_migration_normalizes_existing_rows_before_adding_checks() -> None:
    source = load_migration_source()

    first_check = source.index("create_check_constraint")
    assert source.index('UPDATE public."Usuario"') < first_check
    assert source.index('UPDATE public."Perfil"') < first_check
    # Invalid identity values must fail the migration, not be silently nulled out.
    assert 'SET "Rut" = NULL' not in source
    assert 'SET "Rut_Empresa" = NULL' not in source


def test_service_request_status_check_matches_the_values_the_api_writes() -> None:
    module_source = (Path(__file__).parents[1] / "src" / "amira_api" / "public_routes.py").read_text(encoding="utf-8")
    model_check = next(
        constraint
        for constraint in Base.metadata.tables["Formulario_servicio"].constraints
        if constraint.name == "ck_form_status_allowed"
    )
    compiled = str(model_check.sqltext)

    for status in SERVICE_REQUEST_STATUSES:
        assert f"'{status}'" in compiled
    assert 'status="pending"' in module_source
    assert 'request.status = decision' in module_source


def test_demo_company_fixture_uses_a_rut_that_passes_the_new_check() -> None:
    fixture = FIXTURE_PATH.read_text(encoding="utf-8")

    assert "DEMO-76000000" not in fixture
    assert "'76000000-0'" in fixture
    assert AccountProvisionRequest.normalize_rut("76000000-0") == "76000000-0"
    assert re.fullmatch(RUT_PATTERN, "76000000-0")
