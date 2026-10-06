"""Persist signed-in identity and one-use fallback proof state.

Revision ID: 20260928_0004
Revises: 20260928_0003
"""

import sqlalchemy as sa
from alembic import op

revision = "20260928_0004"
down_revision = "20260928_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("EmailFallbackChallenge", sa.Column("auth_user_id", sa.Uuid(), nullable=True))
    op.execute(
        '''UPDATE "EmailFallbackChallenge" AS challenge
           SET "auth_user_id" = app_user."ID_Auth_Supabase"
           FROM "Usuario" AS app_user
           WHERE challenge."user_id" = app_user."ID"'''
    )
    op.execute(
        '''DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM "EmailFallbackChallenge" WHERE "auth_user_id" IS NULL) THEN
                RAISE EXCEPTION 'Cannot bind existing email fallback challenges to Supabase users';
            END IF;
        END $$'''
    )
    op.alter_column("EmailFallbackChallenge", "auth_user_id", nullable=False)
    op.alter_column("EmailFallbackChallenge", "user_id", nullable=True)
    op.add_column("EmailFallbackChallenge", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("EmailFallbackChallenge", sa.Column("proof_hash", sa.String(length=128), nullable=True))
    op.add_column("EmailFallbackChallenge", sa.Column("proof_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("EmailFallbackChallenge", sa.Column("proof_consumed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_email_fallback_auth_session_created",
        "EmailFallbackChallenge",
        ["auth_user_id", "auth_session_id", "created_at"],
    )


def downgrade() -> None:
    op.execute(
        '''DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM "EmailFallbackChallenge"
                WHERE "user_id" IS NULL OR "activated_at" IS NOT NULL OR "proof_hash" IS NOT NULL
                   OR "proof_expires_at" IS NOT NULL OR "proof_consumed_at" IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: unprovisioned identity or fallback proof state would be lost';
            END IF;
        END $$'''
    )
    op.drop_index("ix_email_fallback_auth_session_created", table_name="EmailFallbackChallenge")
    op.drop_column("EmailFallbackChallenge", "proof_consumed_at")
    op.drop_column("EmailFallbackChallenge", "proof_expires_at")
    op.drop_column("EmailFallbackChallenge", "proof_hash")
    op.drop_column("EmailFallbackChallenge", "activated_at")
    op.alter_column("EmailFallbackChallenge", "user_id", nullable=False)
    op.drop_column("EmailFallbackChallenge", "auth_user_id")
