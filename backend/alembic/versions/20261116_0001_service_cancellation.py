"""Add auditable service cancellation without changing existing service rows."""
from alembic import op
import sqlalchemy as sa

revision = "20261116_0001"
down_revision = "20261113_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("Servicio", sa.Column("Fecha_Cancelacion", sa.DateTime(timezone=True), nullable=True))
    op.add_column("Servicio", sa.Column("Cancelado_Por", sa.String(20), nullable=True))
    op.add_column("Servicio", sa.Column("Monto_Devuelto_Cancelacion", sa.Numeric(18, 4), nullable=True))
    op.add_column("Servicio", sa.Column("Monto_Retenido_Cancelacion", sa.Numeric(18, 4), nullable=True))
    op.drop_constraint("ck_service_status_allowed", "Servicio", type_="check")
    op.create_check_constraint("ck_service_status_allowed", "Servicio", '"Estado" IN (\'confirmed\', \'in_progress\', \'completed\', \'disputed\', \'cancelled\')')


def downgrade() -> None:
    # Never erase cancellation/refund history or silently remap a cancelled service to a live state.
    op.execute('DO $$ BEGIN IF EXISTS (SELECT 1 FROM "Servicio" WHERE "Estado" = \'cancelled\') THEN RAISE EXCEPTION \'Cannot downgrade while cancelled services exist\'; END IF; END $$')
    op.drop_constraint("ck_service_status_allowed", "Servicio", type_="check")
    op.create_check_constraint("ck_service_status_allowed", "Servicio", '"Estado" IN (\'confirmed\', \'in_progress\', \'completed\', \'disputed\')')
    for column in ("Monto_Retenido_Cancelacion", "Monto_Devuelto_Cancelacion", "Cancelado_Por", "Fecha_Cancelacion"):
        op.drop_column("Servicio", column)
