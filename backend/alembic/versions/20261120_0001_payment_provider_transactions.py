"""Record every provider approval, including duplicates requiring review."""
from alembic import op
import sqlalchemy as sa

revision = "20261120_0001"
down_revision = "20261116_0001"
branch_labels = None
depends_on = None
RLS_TABLES = ("Pago_Transaccion_Proveedor",)


def upgrade():
    op.create_table(
        "Pago_Transaccion_Proveedor",
        sa.Column("ID_Transaccion", sa.String(200), primary_key=True),
        sa.Column("ID_Pago", sa.Uuid(), sa.ForeignKey("Pago.ID", ondelete="RESTRICT"), nullable=False),
        sa.Column("Fecha_Creacion", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_Pago_Transaccion_Proveedor_ID_Pago", "Pago_Transaccion_Proveedor", ["ID_Pago"])
    op.execute('ALTER TABLE "Pago_Transaccion_Proveedor" ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON TABLE "Pago_Transaccion_Proveedor" FROM PUBLIC, anon, authenticated')


def downgrade():
    op.drop_index("ix_Pago_Transaccion_Proveedor_ID_Pago", table_name="Pago_Transaccion_Proveedor")
    op.drop_table("Pago_Transaccion_Proveedor")
