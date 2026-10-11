"""Make the service start-actor foreign key ON DELETE SET NULL.

Migration 0003 added fk_service_started_by with ON DELETE RESTRICT, so deleting a user who started a service was
blocked. The constraint is replaced: dropped, added again as NOT VALID, then validated. NOT VALID avoids a full table
scan under the exclusive lock; VALIDATE checks existing rows under a weaker lock. The downgrade restores RESTRICT the
same way.
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
