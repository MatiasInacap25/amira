"""Record when a simulated checkout token was consumed, so each checkout link is single-use."""

from alembic import op

revision = "20261011_0002"
down_revision = "20261011_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE public."Pago" ADD COLUMN "Fecha_Token_Usado" TIMESTAMP WITH TIME ZONE NULL')


def downgrade() -> None:
    op.execute('ALTER TABLE public."Pago" DROP COLUMN "Fecha_Token_Usado"')
