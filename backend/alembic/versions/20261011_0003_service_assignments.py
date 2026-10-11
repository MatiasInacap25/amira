"""Add service (driver, vehicle) assignments, the service start actor and the service status check.

Existing services are only created by payment confirmation with status 'confirmed', so the status check is
safe on live data. It is added NOT VALID so ADD CONSTRAINT does not scan the table under its exclusive lock;
VALIDATE then checks existing rows under a weaker lock. The new start-actor column is nullable, so its
foreign key follows the same NOT VALID then VALIDATE split.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261011_0003"
down_revision = "20261011_0002"
branch_labels = None
depends_on = None

RLS_TABLES = ("Servicio_Asignacion",)
SERVICE_STATUSES = ("confirmed", "in_progress", "completed", "disputed")
STATUS_CONSTRAINT = "ck_service_status_allowed"
STARTED_BY_FK = "fk_service_started_by"


def upgrade() -> None:
    op.create_table(
        "Servicio_Asignacion",
        sa.Column("ID", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ID_Servicio", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ID_Conductor", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ID_Vehiculo", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("Fecha_Asignacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ID_Usuario_Asigna", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("ID"),
        sa.ForeignKeyConstraint(["ID_Servicio"], ["Servicio.ID"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ID_Conductor"], ["Conductor.ID"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ID_Vehiculo"], ["Vehiculo.ID"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ID_Usuario_Asigna"], ["Usuario.ID"], ondelete="RESTRICT"),
        sa.UniqueConstraint("ID_Servicio", "ID_Conductor", name="uq_service_assignment_driver"),
        sa.UniqueConstraint("ID_Servicio", "ID_Vehiculo", name="uq_service_assignment_vehicle"),
    )
    # The table is new and empty, so plain (non-concurrent) index creation takes no meaningful lock.
    op.create_index("ix_Servicio_Asignacion_ID_Conductor", "Servicio_Asignacion", ["ID_Conductor"])
    op.create_index("ix_Servicio_Asignacion_ID_Vehiculo", "Servicio_Asignacion", ["ID_Vehiculo"])
    op.execute('ALTER TABLE public."Servicio_Asignacion" ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL PRIVILEGES ON TABLE public."Servicio_Asignacion" FROM PUBLIC')
    op.execute(
        """DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public."Servicio_Asignacion" FROM anon';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public."Servicio_Asignacion" FROM authenticated';
            END IF;
        END $$;"""
    )

    op.execute('ALTER TABLE public."Servicio" ADD COLUMN "ID_Usuario_Inicio" UUID NULL')
    op.execute(
        f'ALTER TABLE public."Servicio" ADD CONSTRAINT {STARTED_BY_FK} FOREIGN KEY ("ID_Usuario_Inicio") '
        'REFERENCES public."Usuario" ("ID") ON DELETE RESTRICT NOT VALID'
    )
    op.execute(f'ALTER TABLE public."Servicio" VALIDATE CONSTRAINT {STARTED_BY_FK}')

    statuses = ", ".join(f"'{status}'" for status in SERVICE_STATUSES)
    op.execute(
        f'ALTER TABLE public."Servicio" ADD CONSTRAINT {STATUS_CONSTRAINT} '
        f'CHECK ("Estado" IN ({statuses})) NOT VALID'
    )
    op.execute(f'ALTER TABLE public."Servicio" VALIDATE CONSTRAINT {STATUS_CONSTRAINT}')


def downgrade() -> None:
    op.execute(f'ALTER TABLE public."Servicio" DROP CONSTRAINT {STATUS_CONSTRAINT}')
    op.execute(f'ALTER TABLE public."Servicio" DROP CONSTRAINT {STARTED_BY_FK}')
    op.execute('ALTER TABLE public."Servicio" DROP COLUMN "ID_Usuario_Inicio"')
    op.drop_index("ix_Servicio_Asignacion_ID_Vehiculo", table_name="Servicio_Asignacion")
    op.drop_index("ix_Servicio_Asignacion_ID_Conductor", table_name="Servicio_Asignacion")
    op.drop_table("Servicio_Asignacion")
