"""Add stable, unique slugs to service types for public filters and links.

Slugs are derived from the stored name: the ``[DEMO] `` prefix is dropped, the text is
lowercased, Spanish accents are removed, and runs of other characters become hyphens.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261010_0003"
down_revision = "20261010_0002"
branch_labels = None
depends_on = None

SLUG_PATTERN = "^[a-z0-9]+(-[a-z0-9]+)*$"


def upgrade() -> None:
    op.add_column("Tipos_Servicio", sa.Column("Slug", sa.String(length=120), nullable=True))
    op.execute(
        """
        UPDATE public."Tipos_Servicio"
        SET "Slug" = trim(both '-' FROM regexp_replace(
            translate(
                lower(regexp_replace("Nombre_servicio", '^\\[DEMO\\] ', '')),
                'áéíóúüñ',
                'aeiouun'
            ),
            '[^a-z0-9]+',
            '-',
            'g'
        ))
        WHERE "Slug" IS NULL
        """
    )
    op.alter_column("Tipos_Servicio", "Slug", existing_type=sa.String(length=120), nullable=False)
    op.create_unique_constraint("uq_tipos_servicio_slug", "Tipos_Servicio", ["Slug"])
    op.create_check_constraint(
        "ck_tipos_servicio_slug_format",
        "Tipos_Servicio",
        f"\"Slug\" ~ '{SLUG_PATTERN}'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tipos_servicio_slug_format", "Tipos_Servicio", type_="check")
    op.drop_constraint("uq_tipos_servicio_slug", "Tipos_Servicio", type_="unique")
    op.drop_column("Tipos_Servicio", "Slug")
