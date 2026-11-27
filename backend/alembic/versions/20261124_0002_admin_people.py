"""Add nullable account, provider and vehicle moderation markers."""

from alembic import op
import sqlalchemy as sa

revision = "20261124_0002"
down_revision = "20261124_0001"
branch_labels = None
depends_on = None

COLUMNS = {
    "Usuario": ("Fecha_Bloqueo", "Motivo_Bloqueo"),
    "Perfil": ("Fecha_Suspension", "Motivo_Suspension"),
    "Vehiculo": ("Fecha_Deshabilitacion", "Motivo_Deshabilitacion"),
}


def upgrade() -> None:
    for table, (at, reason) in COLUMNS.items():
        op.add_column(table, sa.Column(at, sa.DateTime(timezone=True)))
        op.add_column(table, sa.Column(reason, sa.String(500)))


def downgrade() -> None:
    for table, (at, reason) in COLUMNS.items():
        op.drop_column(table, reason)
        op.drop_column(table, at)
