"""Add the current location of an in-progress service, for the customer's live map.

One row per service at most. The row is written when the driver starts the service and updated while it is in
progress; completion deletes it. The table is new and empty, so plain table creation takes no meaningful lock.
Like the other service tables it has RLS enabled and no client privileges: only the API reads and writes it.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261108_0001"
down_revision = "20261019_0002"
branch_labels = None
depends_on = None

RLS_TABLES = ("Servicio_Ubicacion",)


def upgrade() -> None:
    op.create_table(
        "Servicio_Ubicacion",
        sa.Column("ID_Servicio", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("Latitud", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("Longitud", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("Precision_Metros", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("Fecha_Actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("ID_Servicio"),
        sa.ForeignKeyConstraint(["ID_Servicio"], ["Servicio.ID"], ondelete="CASCADE"),
        sa.CheckConstraint('"Latitud" BETWEEN -90 AND 90', name="ck_service_location_latitude_range"),
        sa.CheckConstraint('"Longitud" BETWEEN -180 AND 180', name="ck_service_location_longitude_range"),
        sa.CheckConstraint(
            '"Precision_Metros" IS NULL OR "Precision_Metros" >= 0',
            name="ck_service_location_accuracy_nonnegative",
        ),
    )
    op.execute('ALTER TABLE public."Servicio_Ubicacion" ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL PRIVILEGES ON TABLE public."Servicio_Ubicacion" FROM PUBLIC')
    op.execute(
        """DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public."Servicio_Ubicacion" FROM anon';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public."Servicio_Ubicacion" FROM authenticated';
            END IF;
        END $$;"""
    )


def downgrade() -> None:
    op.drop_table("Servicio_Ubicacion")
