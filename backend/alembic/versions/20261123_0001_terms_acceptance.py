"""Record each account's acceptance of a Terms and Conditions version at provisioning."""
from alembic import op
import sqlalchemy as sa

revision = "20261123_0001"
down_revision = "20261120_0001"
branch_labels = None
depends_on = None
RLS_TABLES = ("Aceptacion_Terminos",)


def upgrade():
    op.create_table(
        "Aceptacion_Terminos",
        sa.Column("ID", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ID_Usuario", sa.Uuid(), sa.ForeignKey("Usuario.ID", ondelete="CASCADE"), nullable=False),
        sa.Column("Version", sa.String(20), nullable=False),
        sa.Column("Fecha_Aceptacion", sa.DateTime(timezone=True), nullable=False),
        sa.Column("IP", sa.String(64), nullable=True),
        sa.Column("User_Agent", sa.String(512), nullable=True),
        sa.UniqueConstraint("ID_Usuario", "Version", name="uq_aceptacion_terminos_usuario_version"),
    )
    op.create_index("ix_Aceptacion_Terminos_ID_Usuario", "Aceptacion_Terminos", ["ID_Usuario"])
    op.execute('ALTER TABLE "Aceptacion_Terminos" ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON TABLE "Aceptacion_Terminos" FROM PUBLIC, anon, authenticated')


def downgrade():
    op.drop_index("ix_Aceptacion_Terminos_ID_Usuario", table_name="Aceptacion_Terminos")
    op.drop_table("Aceptacion_Terminos")
