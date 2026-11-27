"""Retain allowlisted metadata from verified provider transactions for admin support."""

from alembic import op
import sqlalchemy as sa

revision = "20261125_0004"
down_revision = "20261125_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("Pago_Transaccion_Proveedor", sa.Column("Estado_Verificado", sa.String(20)))
    op.add_column("Pago_Transaccion_Proveedor", sa.Column("Monto_Verificado", sa.Numeric(18, 4)))
    op.add_column("Pago_Transaccion_Proveedor", sa.Column("Modo_Produccion", sa.Boolean()))
    op.add_column("Pago_Transaccion_Proveedor", sa.Column("Detalle_Estado", sa.String(120)))


def downgrade() -> None:
    for name in ("Detalle_Estado", "Modo_Produccion", "Monto_Verificado", "Estado_Verificado"):
        op.drop_column("Pago_Transaccion_Proveedor", name)
