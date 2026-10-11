"""Merge email fallback and demo profile migration branches.

Revision ID: 20261005_0001
Revises: 20260928_0004, 20261003_0002
"""

from alembic import op

revision = "20261005_0001"
down_revision = ("20260928_0004", "20261003_0002")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
