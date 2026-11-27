"""Add nullable manual review fields without rewriting historic records."""

from alembic import op
import sqlalchemy as sa

revision = "20261125_0003"
down_revision = "20261125_0002"
branch_labels = None
depends_on = None

COLUMNS = {
    "Reclamo": (("ID_Resolutor_Admin", sa.Uuid()), ("Motivo_Resolucion", sa.String(500))),
    "Valoracion": (("Fecha_Ocultacion", sa.DateTime(timezone=True)), ("Motivo_Ocultacion", sa.String(500))),
    "Verificacion_Identidad": (("ID_Revisor_Admin", sa.Uuid()),),
    "Cuenta_Desembolso": (("Rut_Titular", sa.String(16)), ("Banco", sa.String(100)),
                         ("Tipo_Cuenta", sa.String(50)), ("Numero_Cuenta", sa.String(64))),
}


def upgrade() -> None:
    for table, columns in COLUMNS.items():
        for name, column_type in columns:
            op.add_column(table, sa.Column(name, column_type))


def downgrade() -> None:
    for table, columns in reversed(tuple(COLUMNS.items())):
        for name, _ in reversed(columns):
            op.drop_column(table, name)
