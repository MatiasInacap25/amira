"""Add controlled account/profile roles and auth challenge persistence.

Revision ID: 20260928_0003
Revises: 20260927_0002
"""

import sqlalchemy as sa

from alembic import op

revision = "20260928_0003"
down_revision = "20260927_0002"
branch_labels = None
depends_on = None

RLS_TABLES = ("DriverInvitation", "EmailFallbackChallenge")

ACCOUNT_ROLES = (
    ("b2000000-0000-4000-8000-000000000001", "client", "Client"),
    ("b2000000-0000-4000-8000-000000000002", "company_owner", "Company owner"),
    ("b2000000-0000-4000-8000-000000000003", "company_driver", "Company-linked driver"),
    ("b2000000-0000-4000-8000-000000000004", "independent_driver", "Independent driver"),
)
PROFILE_ROLES = (
    ("b2000000-0000-4000-8000-000000000005", "company", "Company"),
    ("b2000000-0000-4000-8000-000000000006", "independent_driver", "Independent driver"),
)


def upgrade() -> None:
    # The only known existing role rows are synthetic fixtures from revision 0002.
    # Never infer an authorization code from an undocumented lookup label.
    op.execute('ALTER TABLE "Rol_Usuario" ADD COLUMN "code" VARCHAR(64)')
    op.execute('ALTER TABLE "Rol_Perfil" ADD COLUMN "code" VARCHAR(64)')
    op.execute('UPDATE "Rol_Usuario" SET "code" = \'demo_fixture\' WHERE "Rol" = \'[DEMO] fixture owner\'')
    op.execute('UPDATE "Rol_Perfil" SET "code" = \'demo_fixture\' WHERE "Rol" = \'[DEMO] proveedor de prueba\'')
    # Reapply codes only to the deterministic role rows seeded by this revision.
    # Both ID and exact display name must match; all other labels still fail closed.
    for table, seeded_roles in (("Rol_Usuario", ACCOUNT_ROLES), ("Rol_Perfil", PROFILE_ROLES)):
        for role_id, code, name in seeded_roles:
            op.execute(
                f"""UPDATE "{table}" SET "code" = '{code}' WHERE "ID" = '{role_id}' AND "Rol" = '{name}'"""
            )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "Rol_Usuario" WHERE "code" IS NULL)
               OR EXISTS (SELECT 1 FROM "Rol_Perfil" WHERE "code" IS NULL) THEN
                RAISE EXCEPTION 'Unrecognized existing role labels; map them explicitly to approved role codes before upgrading 20260928_0003';
            END IF;
        END $$;
        """
    )
    op.execute('ALTER TABLE "Rol_Usuario" ALTER COLUMN "code" SET NOT NULL')
    op.execute('ALTER TABLE "Rol_Perfil" ALTER COLUMN "code" SET NOT NULL')
    op.create_unique_constraint("uq_rol_usuario_code", "Rol_Usuario", ["code"])
    op.create_unique_constraint("uq_rol_perfil_code", "Rol_Perfil", ["code"])
    op.create_check_constraint(
        "ck_rol_usuario_code_allowed",
        "Rol_Usuario",
        "code IN ('client', 'company_owner', 'company_driver', 'independent_driver', 'demo_fixture')",
    )
    op.create_check_constraint(
        "ck_rol_perfil_code_allowed",
        "Rol_Perfil",
        "code IN ('company', 'independent_driver', 'demo_fixture')",
    )

    op.execute('ALTER TABLE "Perfil" ADD COLUMN "kind" VARCHAR(32)')
    op.execute('UPDATE "Perfil" SET "kind" = \'company\'')
    op.execute('ALTER TABLE "Perfil" ALTER COLUMN "kind" SET NOT NULL')
    op.create_check_constraint(
        "ck_perfil_kind_allowed",
        "Perfil",
        "kind IN ('company', 'independent_driver')",
    )
    op.execute('ALTER TABLE "Perfil" ADD COLUMN "public_activated_at" TIMESTAMP WITH TIME ZONE')
    op.alter_column("Conductor", "ID_perfil", nullable=True)

    op.create_table(
        "DriverInvitation",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_profile_id", sa.Uuid(), nullable=False),
        sa.Column("target_email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_profile_id"], ["Perfil.ID"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["Usuario.ID"], ondelete="RESTRICT"),
        sa.UniqueConstraint("token_hash", name="uq_driver_invitation_token_hash"),
        sa.CheckConstraint("target_email = lower(btrim(target_email))", name="ck_driver_invitation_target_email_normalized"),
    )
    op.create_index("ix_driver_invitation_company_profile_id", "DriverInvitation", ["company_profile_id"])
    op.create_index("ix_driver_invitation_expiry", "DriverInvitation", ["expires_at"])

    op.create_table(
        "EmailFallbackChallenge",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("auth_session_id", sa.String(length=128), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["Usuario.ID"], ondelete="CASCADE"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_email_fallback_attempt_count_nonnegative"),
    )
    op.create_index("ix_email_fallback_user_expiry", "EmailFallbackChallenge", ["user_id", "expires_at"])

    for role_id, code, name in ACCOUNT_ROLES:
        op.execute(
            f'''INSERT INTO "Rol_Usuario" ("ID", "Rol", "code") VALUES ('{role_id}', '{name}', '{code}') ON CONFLICT ("code") DO NOTHING'''
        )
    for role_id, code, name in PROFILE_ROLES:
        op.execute(
            f'''INSERT INTO "Rol_Perfil" ("ID", "Rol", "code") VALUES ('{role_id}', '{name}', '{code}') ON CONFLICT ("code") DO NOTHING'''
        )

    table_literals = ", ".join(f"'{name}'" for name in RLS_TABLES)
    op.execute(
        f"""
        DO $$
        DECLARE table_name text;
        BEGIN
            FOREACH table_name IN ARRAY ARRAY[{table_literals}] LOOP
                EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
                EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC', table_name);
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon', table_name);
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM authenticated', table_name);
                END IF;
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "Conductor" WHERE "ID_perfil" IS NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade: independent drivers require nullable Conductor.ID_perfil';
            END IF;
            IF EXISTS (SELECT 1 FROM "Perfil" WHERE "kind" <> 'company' OR "public_activated_at" IS NOT NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade: independent or activated profile state would be lost';
            END IF;
            IF EXISTS (SELECT 1 FROM "DriverInvitation") OR EXISTS (SELECT 1 FROM "EmailFallbackChallenge") THEN
                RAISE EXCEPTION 'Cannot downgrade: invitation or fallback challenge records would be lost';
            END IF;
        END $$;
        """
    )
    op.drop_index("ix_email_fallback_user_expiry", table_name="EmailFallbackChallenge")
    op.drop_table("EmailFallbackChallenge")
    op.drop_index("ix_driver_invitation_expiry", table_name="DriverInvitation")
    op.drop_index("ix_driver_invitation_company_profile_id", table_name="DriverInvitation")
    op.drop_table("DriverInvitation")
    op.alter_column("Conductor", "ID_perfil", nullable=False)
    op.drop_column("Perfil", "public_activated_at")
    op.drop_constraint("ck_perfil_kind_allowed", "Perfil", type_="check")
    op.drop_column("Perfil", "kind")

    # Preserve seeded role rows. Existing foreign keys and labels remain intact.
    op.drop_constraint("ck_rol_perfil_code_allowed", "Rol_Perfil", type_="check")
    op.drop_constraint("uq_rol_perfil_code", "Rol_Perfil", type_="unique")
    op.drop_column("Rol_Perfil", "code")
    op.drop_constraint("ck_rol_usuario_code_allowed", "Rol_Usuario", type_="check")
    op.drop_constraint("uq_rol_usuario_code", "Rol_Usuario", type_="unique")
    op.drop_column("Rol_Usuario", "code")
