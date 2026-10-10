"""Finalize the service catalog: clean names for the seeded demo types and four real types.

The two seeded rows keep their IDs (so existing availability links stay valid) and lose the
``[DEMO] `` prefix. The four new rows use fixed IDs, and inserts skip rows that already
exist, so re-running the upgrade is safe. The downgrade restores the demo names and deletes
only inserted rows that nothing references.
"""

from alembic import op

revision = "20261010_0006"
down_revision = "20261010_0005"
branch_labels = None
depends_on = None

NEW_SERVICE_TYPES = (
    ("fecf8e67-8387-4ab3-aa1f-8ea453c95b82", ("Transporte de mercadería", "mercaderia")),
    ("f4940a97-9fca-4665-a813-5e6ff396e4fa", ("Fletes y traslados", "fletes")),
    ("f9c72b3d-413c-4af5-94a0-d239e1b19ff2", ("Recolección de escombros", "escombros")),
    ("bbbc620f-9faa-4675-bd0c-2d7ea0f20a51", ("Servicios de grúa", "grua")),
)


def upgrade() -> None:
    op.execute(
        """
        UPDATE public."Tipos_Servicio" SET "Nombre_servicio" = 'Mudanzas', "Slug" = 'mudanzas'
        WHERE "ID" = 'a1000000-0000-4000-8000-000000000005'
        """
    )
    op.execute(
        """
        UPDATE public."Tipos_Servicio" SET "Nombre_servicio" = 'Carga compartida', "Slug" = 'carga-compartida'
        WHERE "ID" = 'a1000000-0000-4000-8000-000000000006'
        """
    )
    op.execute(
        """
        INSERT INTO public."Tipos_Servicio" ("ID", "Nombre_servicio", "Slug") VALUES
            ('fecf8e67-8387-4ab3-aa1f-8ea453c95b82', 'Transporte de mercadería', 'mercaderia'),
            ('f4940a97-9fca-4665-a813-5e6ff396e4fa', 'Fletes y traslados', 'fletes'),
            ('f9c72b3d-413c-4af5-94a0-d239e1b19ff2', 'Recolección de escombros', 'escombros'),
            ('bbbc620f-9faa-4675-bd0c-2d7ea0f20a51', 'Servicios de grúa', 'grua')
        ON CONFLICT ("ID") DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM public."Tipos_Servicio" AS t
        WHERE t."ID" IN (
            'fecf8e67-8387-4ab3-aa1f-8ea453c95b82',
            'f4940a97-9fca-4665-a813-5e6ff396e4fa',
            'f9c72b3d-413c-4af5-94a0-d239e1b19ff2',
            'bbbc620f-9faa-4675-bd0c-2d7ea0f20a51'
        )
          AND NOT EXISTS (SELECT 1 FROM public."Servicios_Disponibles" s WHERE s."ID_Tipo_Servicio" = t."ID")
          AND NOT EXISTS (SELECT 1 FROM public."Formulario_servicio" f WHERE f."Tipo_Servicio" = t."ID")
          AND NOT EXISTS (SELECT 1 FROM public."Cotizacion" c WHERE c."Tipo_Servicio" = t."ID")
        """
    )
    op.execute(
        """
        UPDATE public."Tipos_Servicio" SET "Nombre_servicio" = '[DEMO] Mudanzas'
        WHERE "ID" = 'a1000000-0000-4000-8000-000000000005'
        """
    )
    op.execute(
        """
        UPDATE public."Tipos_Servicio" SET "Nombre_servicio" = '[DEMO] Carga compartida'
        WHERE "ID" = 'a1000000-0000-4000-8000-000000000006'
        """
    )
