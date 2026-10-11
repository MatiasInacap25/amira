"""Enforce identity, contact, status, volume, and currency invariants at the database level.

Existing values are normalized first, but only in ways that do not change their meaning
(spacing, dots, letter case, phone punctuation). A value that still violates a rule after
normalization makes this migration fail; it is never silently replaced with NULL.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261010_0005"
down_revision = "20261010_0004"
branch_labels = None
depends_on = None

RUT_PATTERN = r"^\d{7,8}-[0-9K]$"
PHONE_PATTERN = r"^\+[1-9]\d{7,14}$"
SERVICE_REQUEST_STATUSES = ("pending", "accepted", "rejected")
CURRENCY_TABLES = {
    "Cotizacion": "ck_quote_currency_clp",
    "Pago": "ck_payment_currency_clp",
    "Reembolso": "ck_refund_currency_clp",
    "Desembolso": "ck_payout_currency_clp",
}


def upgrade() -> None:
    # 1. Normalize formatting that the API already produces in canonical form.
    op.execute(
        r"""
        UPDATE public."Usuario"
        SET "Rut" = regexp_replace(upper(regexp_replace("Rut", '[.\s]', '', 'g')), '^([0-9]{7,8})-?([0-9K])$', '\1-\2')
        WHERE "Rut" IS NOT NULL
        """
    )
    op.execute(
        r"""
        UPDATE public."Perfil"
        SET "Rut_Empresa" = regexp_replace(upper(regexp_replace("Rut_Empresa", '[.\s]', '', 'g')), '^([0-9]{7,8})-?([0-9K])$', '\1-\2')
        WHERE "Rut_Empresa" IS NOT NULL
        """
    )
    op.execute(
        r"""
        UPDATE public."Usuario"
        SET "Telefono" = regexp_replace("Telefono", '[\s()-]', '', 'g')
        WHERE "Telefono" IS NOT NULL
        """
    )

    # 2. Add the rules. Any remaining violation aborts the migration here.
    op.create_check_constraint(
        "ck_usuario_rut_format", "Usuario", f"\"Rut\" IS NULL OR \"Rut\" ~ '{RUT_PATTERN}'"
    )
    op.create_check_constraint(
        "ck_usuario_phone_format", "Usuario", f"\"Telefono\" IS NULL OR \"Telefono\" ~ '{PHONE_PATTERN}'"
    )
    op.create_index(
        "uq_usuario_rut",
        "Usuario",
        [sa.text('"Rut"')],
        unique=True,
        postgresql_where=sa.text('"Rut" IS NOT NULL'),
    )
    op.create_check_constraint(
        "ck_perfil_company_tax_id_format", "Perfil", f"\"Rut_Empresa\" IS NULL OR \"Rut_Empresa\" ~ '{RUT_PATTERN}'"
    )
    op.create_index(
        "uq_perfil_rut_empresa",
        "Perfil",
        [sa.text('"Rut_Empresa"')],
        unique=True,
        postgresql_where=sa.text('"Rut_Empresa" IS NOT NULL'),
    )
    statuses = ", ".join(f"'{status}'" for status in SERVICE_REQUEST_STATUSES)
    op.create_check_constraint("ck_form_status_allowed", "Formulario_servicio", f'"Estado" IN ({statuses})')
    op.create_check_constraint(
        "ck_form_volume_nonnegative", "Formulario_servicio", '"Volumen_Estimado" IS NULL OR "Volumen_Estimado" >= 0'
    )
    for table, constraint_name in CURRENCY_TABLES.items():
        op.create_check_constraint(constraint_name, table, "\"Moneda\" = 'CLP'")


def downgrade() -> None:
    for table, constraint_name in reversed(list(CURRENCY_TABLES.items())):
        op.drop_constraint(constraint_name, table, type_="check")
    op.drop_constraint("ck_form_volume_nonnegative", "Formulario_servicio", type_="check")
    op.drop_constraint("ck_form_status_allowed", "Formulario_servicio", type_="check")
    op.drop_index("uq_perfil_rut_empresa", table_name="Perfil")
    op.drop_constraint("ck_perfil_company_tax_id_format", "Perfil", type_="check")
    op.drop_index("uq_usuario_rut", table_name="Usuario")
    op.drop_constraint("ck_usuario_phone_format", "Usuario", type_="check")
    op.drop_constraint("ck_usuario_rut_format", "Usuario", type_="check")
