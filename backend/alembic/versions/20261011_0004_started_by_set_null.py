"""Make the service start-actor foreign key ON DELETE SET NULL.

Migration 0003 added fk_service_started_by with ON DELETE RESTRICT, so deleting a user who started a service was
blocked. The constraint is replaced: dropped, added again as NOT VALID, then validated.

The three statements run in one transaction (Alembic wraps the run in one transaction on PostgreSQL). DROP CONSTRAINT
takes ACCESS EXCLUSIVE on "Servicio" and holds it until that commit. The VALIDATE scan of existing rows therefore runs
under the same ACCESS EXCLUSIVE lock, not a weaker one, so splitting ADD and VALIDATE does not shorten the lock here.
The downgrade restores RESTRICT the same way.
"""

from alembic import op

revision = "20261011_0004"
down_revision = "20261011_0003"
branch_labels = None
depends_on = None

STARTED_BY_FK = "fk_service_started_by"


def upgrade() -> None:
    op.execute(f'ALTER TABLE public."Servicio" DROP CONSTRAINT {STARTED_BY_FK}')
    op.execute(
        f'ALTER TABLE public."Servicio" ADD CONSTRAINT {STARTED_BY_FK} FOREIGN KEY ("ID_Usuario_Inicio") '
        'REFERENCES public."Usuario" ("ID") ON DELETE SET NULL NOT VALID'
    )
    op.execute(f'ALTER TABLE public."Servicio" VALIDATE CONSTRAINT {STARTED_BY_FK}')


def downgrade() -> None:
    op.execute(f'ALTER TABLE public."Servicio" DROP CONSTRAINT {STARTED_BY_FK}')
    op.execute(
        f'ALTER TABLE public."Servicio" ADD CONSTRAINT {STARTED_BY_FK} FOREIGN KEY ("ID_Usuario_Inicio") '
        'REFERENCES public."Usuario" ("ID") ON DELETE RESTRICT NOT VALID'
    )
    op.execute(f'ALTER TABLE public."Servicio" VALIDATE CONSTRAINT {STARTED_BY_FK}')
