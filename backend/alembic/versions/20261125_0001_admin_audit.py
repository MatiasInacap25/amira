"""Create the private administrator audit log."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261125_0001"
down_revision = "20261124_0001"
branch_labels = None
depends_on = None
RLS_TABLES = ("admin_audit_log",)


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("admin_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("before", JSONB(none_as_null=True)),
        sa.Column("after", JSONB(none_as_null=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at", "id"])
    op.execute("ALTER TABLE public.admin_audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL PRIVILEGES ON TABLE public.admin_audit_log FROM PUBLIC, anon, authenticated")


def downgrade() -> None:
    op.drop_table("admin_audit_log")
