"""Activate the synthetic demo provider profile for public browsing.

Revision ID: 20261003_0001
Revises: 20260928_0003
"""

from alembic import op

revision = "20261003_0001"
down_revision = "20260928_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        '''UPDATE "Perfil"
           SET "public_activated_at" = now()
           WHERE "ID" = 'a1000000-0000-4000-8000-000000000004'
             AND "Nombre" = '[DEMO] Transporte de prueba'
             AND "public_activated_at" IS NULL'''
    )


def downgrade() -> None:
    # Do not revoke activation if the synthetic profile is changed after upgrade.
    pass
