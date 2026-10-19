"""Add optional image attachments to chat messages.

The three attachment columns are nullable, so existing rows are unchanged. Two checks are added NOT VALID and then
validated, the same way as ck_quote_status_allowed: a message needs non-empty text or an attachment, and the three
attachment columns are either all set or all null. A row that breaks either rule fails the migration.
"""

from alembic import op

revision = "20261019_0001"
down_revision = "20261011_0004"
branch_labels = None
depends_on = None

ATTACHMENT_COLUMNS = ("Adjunto_Clave", "Adjunto_Tipo", "Adjunto_Bytes")
CONTENT_CHECK = "ck_message_text_or_attachment"
ALL_OR_NONE_CHECK = "ck_message_attachment_all_or_none"


def upgrade() -> None:
    op.execute(
        'ALTER TABLE public."Mensajes" '
        'ADD COLUMN "Adjunto_Clave" VARCHAR(300), '
        'ADD COLUMN "Adjunto_Tipo" VARCHAR(40), '
        'ADD COLUMN "Adjunto_Bytes" INTEGER'
    )
    op.execute(
        f'ALTER TABLE public."Mensajes" ADD CONSTRAINT {CONTENT_CHECK} '
        'CHECK (btrim("Contenido") <> \'\' OR "Adjunto_Clave" IS NOT NULL) NOT VALID'
    )
    op.execute(
        f'ALTER TABLE public."Mensajes" ADD CONSTRAINT {ALL_OR_NONE_CHECK} '
        'CHECK (("Adjunto_Clave" IS NULL AND "Adjunto_Tipo" IS NULL AND "Adjunto_Bytes" IS NULL) '
        'OR ("Adjunto_Clave" IS NOT NULL AND "Adjunto_Tipo" IS NOT NULL AND "Adjunto_Bytes" IS NOT NULL)) NOT VALID'
    )
    op.execute(f'ALTER TABLE public."Mensajes" VALIDATE CONSTRAINT {CONTENT_CHECK}')
    op.execute(f'ALTER TABLE public."Mensajes" VALIDATE CONSTRAINT {ALL_OR_NONE_CHECK}')


def downgrade() -> None:
    # Image-only messages keep their row and their empty Contenido; only the attachment reference is dropped.
    op.execute(f'ALTER TABLE public."Mensajes" DROP CONSTRAINT {ALL_OR_NONE_CHECK}')
    op.execute(f'ALTER TABLE public."Mensajes" DROP CONSTRAINT {CONTENT_CHECK}')
    op.execute(
        'ALTER TABLE public."Mensajes" '
        'DROP COLUMN "Adjunto_Clave", '
        'DROP COLUMN "Adjunto_Tipo", '
        'DROP COLUMN "Adjunto_Bytes"'
    )
