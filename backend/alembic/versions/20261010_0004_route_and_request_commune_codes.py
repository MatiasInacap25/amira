"""Constrain shared-route and quote-request locations to catalog communes.

``Origen``/``Destino`` stay as display text; the new ``Codigo_Comuna_*`` columns are what
filters use. Legacy rows keep NULL codes. Quote requests make the street address optional
because the commune is now the required location.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261010_0004"
down_revision = "20261010_0003"
branch_labels = None
depends_on = None

DEMO_TRIP_BACKFILL = (
    ("Santiago", "13101"),
    ("Valparaíso", "05101"),
)


def upgrade() -> None:
    for table in ("Viaje", "Formulario_servicio"):
        op.add_column(table, sa.Column("Codigo_Comuna_Origen", sa.String(length=5), nullable=True))
        op.add_column(table, sa.Column("Codigo_Comuna_Destino", sa.String(length=5), nullable=True))
        op.create_foreign_key(
            f"fk_{table.lower()}_comuna_origen", table, "Comunas", ["Codigo_Comuna_Origen"], ["Codigo"], ondelete="RESTRICT"
        )
        op.create_foreign_key(
            f"fk_{table.lower()}_comuna_destino", table, "Comunas", ["Codigo_Comuna_Destino"], ["Codigo"], ondelete="RESTRICT"
        )
        op.create_index(f"ix_{table}_Codigo_Comuna_Origen", table, ["Codigo_Comuna_Origen"])
        op.create_index(f"ix_{table}_Codigo_Comuna_Destino", table, ["Codigo_Comuna_Destino"])

    op.alter_column("Formulario_servicio", "Origen", existing_type=sa.String(length=300), nullable=True)
    op.alter_column("Formulario_servicio", "Destino", existing_type=sa.String(length=300), nullable=True)

    for free_text, commune_code in DEMO_TRIP_BACKFILL:
        op.execute(
            sa.text(
                'UPDATE public."Viaje" SET "Codigo_Comuna_Origen" = :code '
                'WHERE "Origen" = :free_text AND "Codigo_Comuna_Origen" IS NULL'
            ).bindparams(code=commune_code, free_text=free_text)
        )
        op.execute(
            sa.text(
                'UPDATE public."Viaje" SET "Codigo_Comuna_Destino" = :code '
                'WHERE "Destino" = :free_text AND "Codigo_Comuna_Destino" IS NULL'
            ).bindparams(code=commune_code, free_text=free_text)
        )


def downgrade() -> None:
    op.execute('UPDATE public."Formulario_servicio" SET "Origen" = COALESCE("Origen", \'\'), "Destino" = COALESCE("Destino", \'\')')
    op.alter_column("Formulario_servicio", "Destino", existing_type=sa.String(length=300), nullable=False)
    op.alter_column("Formulario_servicio", "Origen", existing_type=sa.String(length=300), nullable=False)
    for table in ("Formulario_servicio", "Viaje"):
        op.drop_index(f"ix_{table}_Codigo_Comuna_Destino", table_name=table)
        op.drop_index(f"ix_{table}_Codigo_Comuna_Origen", table_name=table)
        op.drop_constraint(f"fk_{table.lower()}_comuna_destino", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table.lower()}_comuna_origen", table, type_="foreignkey")
        op.drop_column(table, "Codigo_Comuna_Destino")
        op.drop_column(table, "Codigo_Comuna_Origen")
