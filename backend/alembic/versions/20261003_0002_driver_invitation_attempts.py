"""Track short-lived authenticated driver invitation acceptance attempts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261003_0002"
down_revision = "20261003_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "DriverInvitationAttempt",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("auth_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auth_session_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_driver_invitation_attempt_identity_created",
        "DriverInvitationAttempt",
        ["auth_user_id", "auth_session_id", "created_at"],
    )
    op.create_index("ix_driver_invitation_attempt_created_at", "DriverInvitationAttempt", ["created_at"])
    op.execute('ALTER TABLE public."DriverInvitationAttempt" ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL PRIVILEGES ON TABLE public."DriverInvitationAttempt" FROM PUBLIC')
    op.execute(
        """DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public."DriverInvitationAttempt" FROM anon';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public."DriverInvitationAttempt" FROM authenticated';
            END IF;
        END $$;"""
    )


def downgrade() -> None:
    op.drop_index("ix_driver_invitation_attempt_created_at", table_name="DriverInvitationAttempt")
    op.drop_index("ix_driver_invitation_attempt_identity_created", table_name="DriverInvitationAttempt")
    op.drop_table("DriverInvitationAttempt")
