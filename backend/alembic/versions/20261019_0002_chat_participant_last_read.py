"""Track when each chat participant last read a chat, for unread counts.

The column is NOT NULL with a now() default, so existing participant rows get the migration time and old chats do
not show as unread. Additive: no existing data changes.
"""

from alembic import op

revision = "20261019_0002"
down_revision = "20261019_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE public."Chat_participantes" '
        'ADD COLUMN "Ultima_Lectura" TIMESTAMPTZ NOT NULL DEFAULT now()'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE public."Chat_participantes" DROP COLUMN "Ultima_Lectura"')
