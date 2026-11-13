"""Store driver certificate verifications in Verificacion_Identidad.

Adds the document type, the certificate's registers, the key of the official PDF and the review timestamp. All new
columns are nullable, so adding them only touches the catalog. The status and document-type CHECKs are added NOT
VALID: they bind every new or updated row without scanning (or failing on) rows written before this revision. The
index serves the "latest certificate of this type for this user" lookup. RLS and the revoked client privileges set
on this table in 20260927_0002 are unchanged.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261113_0001"
down_revision = "20261108_0001"
branch_labels = None
depends_on = None

TABLE = "Verificacion_Identidad"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("Tipo_Documento", sa.String(length=40), nullable=True))
    op.add_column(TABLE, sa.Column("Anotaciones", postgresql.JSONB(), nullable=True))
    op.add_column(TABLE, sa.Column("Clave_PDF", sa.String(length=512), nullable=True))
    op.add_column(TABLE, sa.Column("Fecha_Revision", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        'ALTER TABLE public."Verificacion_Identidad" ADD CONSTRAINT ck_identity_verification_document_type '
        "CHECK (\"Tipo_Documento\" IS NULL OR \"Tipo_Documento\" IN ('criminal_record', 'driver_record')) NOT VALID"
    )
    op.execute(
        'ALTER TABLE public."Verificacion_Identidad" ADD CONSTRAINT ck_identity_verification_status '
        "CHECK (\"Estado\" IN ('verified', 'in_review', 'rejected')) NOT VALID"
    )
    op.create_index(
        "ix_identity_verification_user_document",
        TABLE,
        ["ID_Usuario", "Tipo_Documento", "Fecha_Creacion"],
    )


def downgrade() -> None:
    op.drop_index("ix_identity_verification_user_document", table_name=TABLE)
    op.execute('ALTER TABLE public."Verificacion_Identidad" DROP CONSTRAINT ck_identity_verification_status')
    op.execute('ALTER TABLE public."Verificacion_Identidad" DROP CONSTRAINT ck_identity_verification_document_type')
    op.drop_column(TABLE, "Fecha_Revision")
    op.drop_column(TABLE, "Clave_PDF")
    op.drop_column(TABLE, "Anotaciones")
    op.drop_column(TABLE, "Tipo_Documento")
