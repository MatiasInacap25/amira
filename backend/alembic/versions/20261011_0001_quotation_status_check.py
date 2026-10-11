"""Restrict quotation statuses to the states the quotation workflow uses.

The check is added NOT VALID so the table is not scanned under the exclusive lock taken by ADD CONSTRAINT;
VALIDATE then checks existing rows under a weaker lock. A row with any other status fails the migration.
"""

from alembic import op

revision = "20261011_0001"
down_revision = "20261010_0006"
branch_labels = None
depends_on = None

QUOTATION_STATUSES = ("pending", "paid", "rejected", "expired", "superseded")
CONSTRAINT_NAME = "ck_quote_status_allowed"


def upgrade() -> None:
    statuses = ", ".join(f"'{status}'" for status in QUOTATION_STATUSES)
    op.execute(
        f'ALTER TABLE public."Cotizacion" ADD CONSTRAINT {CONSTRAINT_NAME} '
        f'CHECK ("Estado" IN ({statuses})) NOT VALID'
    )
    op.execute(f'ALTER TABLE public."Cotizacion" VALIDATE CONSTRAINT {CONSTRAINT_NAME}')


def downgrade() -> None:
    op.execute(f'ALTER TABLE public."Cotizacion" DROP CONSTRAINT {CONSTRAINT_NAME}')
