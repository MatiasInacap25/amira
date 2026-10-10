"""Attach a catalog commune to provider profiles and independent driver records.

Free-text ``Ubicacion`` stays for display and backward compatibility; ``Codigo_Comuna``
becomes the source of truth for location filters. Existing demo rows are backfilled
only when their free-text location matches a catalog commune exactly.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261010_0002"
down_revision = "20261010_0001"
branch_labels = None
depends_on = None


DEMO_COMMUNE_BACKFILL = (
    ("Santiago", "13101"),
    ("Valparaíso", "05101"),
)


def upgrade() -> None:
    op.add_column("Perfil", sa.Column("Codigo_Comuna", sa.String(length=5), nullable=True))
    op.add_column("Conductor", sa.Column("Codigo_Comuna", sa.String(length=5), nullable=True))
    op.create_foreign_key(
        "fk_perfil_comuna", "Perfil", "Comunas", ["Codigo_Comuna"], ["Codigo"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_conductor_comuna", "Conductor", "Comunas", ["Codigo_Comuna"], ["Codigo"], ondelete="RESTRICT"
    )
    op.create_index("ix_Perfil_Codigo_Comuna", "Perfil", ["Codigo_Comuna"])
    op.create_index("ix_Conductor_Codigo_Comuna", "Conductor", ["Codigo_Comuna"])

    for free_text, commune_code in DEMO_COMMUNE_BACKFILL:
        op.execute(
            sa.text(
                'UPDATE public."Perfil" SET "Codigo_Comuna" = :code '
                'WHERE "Ubicacion" = :free_text AND "Codigo_Comuna" IS NULL'
            ).bindparams(code=commune_code, free_text=free_text)
        )
        op.execute(
            sa.text(
                'UPDATE public."Conductor" SET "Codigo_Comuna" = :code '
                'WHERE "Ubicacion" = :free_text AND "Codigo_Comuna" IS NULL'
            ).bindparams(code=commune_code, free_text=free_text)
        )


def downgrade() -> None:
    op.drop_index("ix_Conductor_Codigo_Comuna", table_name="Conductor")
    op.drop_index("ix_Perfil_Codigo_Comuna", table_name="Perfil")
    op.drop_constraint("fk_conductor_comuna", "Conductor", type_="foreignkey")
    op.drop_constraint("fk_perfil_comuna", "Perfil", type_="foreignkey")
    op.drop_column("Conductor", "Codigo_Comuna")
    op.drop_column("Perfil", "Codigo_Comuna")
