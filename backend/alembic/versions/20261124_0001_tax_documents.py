"""Simulated tax documents: the customer's boleta and Amira's commission invoice, one per service and type."""
from alembic import op
import sqlalchemy as sa

revision = "20261124_0001"
down_revision = "20261123_0001"
branch_labels = None
depends_on = None
RLS_TABLES = ("Documento_Tributario",)


def upgrade():
    op.create_table(
        "Documento_Tributario",
        sa.Column("ID", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ID_Servicio", sa.Uuid(), sa.ForeignKey("Servicio.ID", ondelete="RESTRICT"), nullable=False),
        sa.Column("ID_Pago", sa.Uuid(), sa.ForeignKey("Pago.ID", ondelete="RESTRICT"), nullable=True),
        sa.Column("ID_Desembolso", sa.Uuid(), sa.ForeignKey("Desembolso.ID", ondelete="RESTRICT"), nullable=True),
        sa.Column("Tipo", sa.String(40), nullable=False),
        sa.Column("Folio", sa.Integer(), nullable=False),
        sa.Column("Emisor_Nombre", sa.String(160), nullable=False),
        sa.Column("Emisor_Rut", sa.String(16), nullable=True),
        sa.Column("Receptor_Nombre", sa.String(160), nullable=False),
        sa.Column("Receptor_Rut", sa.String(16), nullable=True),
        sa.Column("Neto", sa.Numeric(18, 4), nullable=False),
        sa.Column("IVA", sa.Numeric(18, 4), nullable=False),
        sa.Column("Total", sa.Numeric(18, 4), nullable=False),
        sa.Column("Moneda", sa.String(3), nullable=False),
        sa.Column("Emitido_En", sa.DateTime(timezone=True), nullable=False),
        sa.Column("Simulado", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("ID_Servicio", "Tipo", name="uq_tax_document_service_type"),
        sa.UniqueConstraint("Tipo", "Folio", name="uq_tax_document_type_folio"),
        sa.CheckConstraint("\"Tipo\" IN ('boleta', 'factura_comision')", name="ck_tax_document_type_allowed"),
        sa.CheckConstraint('"Folio" > 0', name="ck_tax_document_folio_positive"),
        sa.CheckConstraint('"Neto" >= 0', name="ck_tax_document_net_nonnegative"),
        sa.CheckConstraint('"IVA" >= 0', name="ck_tax_document_iva_nonnegative"),
        sa.CheckConstraint('"Total" >= 0', name="ck_tax_document_total_nonnegative"),
        sa.CheckConstraint("\"Moneda\" = 'CLP'", name="ck_tax_document_currency_clp"),
    )
    op.create_index("ix_Documento_Tributario_ID_Servicio", "Documento_Tributario", ["ID_Servicio"])
    op.create_index("ix_Documento_Tributario_ID_Pago", "Documento_Tributario", ["ID_Pago"])
    op.create_index("ix_Documento_Tributario_ID_Desembolso", "Documento_Tributario", ["ID_Desembolso"])
    op.execute('ALTER TABLE "Documento_Tributario" ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON TABLE "Documento_Tributario" FROM PUBLIC, anon, authenticated')


def downgrade():
    op.drop_index("ix_Documento_Tributario_ID_Desembolso", table_name="Documento_Tributario")
    op.drop_index("ix_Documento_Tributario_ID_Pago", table_name="Documento_Tributario")
    op.drop_index("ix_Documento_Tributario_ID_Servicio", table_name="Documento_Tributario")
    op.drop_table("Documento_Tributario")
