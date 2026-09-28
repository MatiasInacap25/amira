"""Enable default-deny Data API access and add clearly marked browse fixtures.

Revision ID: 20260927_0002
Revises: 20260926_0001
"""

from alembic import op

revision = "20260927_0002"
down_revision = "20260926_0001"
branch_labels = None
depends_on = None

PUBLIC_TABLES = (
    "Usuario",
    "Rol_Usuario",
    "Tipo_Conductor",
    "Rol_Perfil",
    "Perfil",
    "Conductor",
    "Verificacion_Identidad",
    "Vehiculo",
    "Tipos_Servicio",
    "Servicios_Disponibles",
    "Formulario_servicio",
    "Imagenes_Formulario",
    "Chat",
    "Chat_participantes",
    "Mensajes",
    "Cotizacion",
    "Servicio",
    "Pago",
    "Cuenta_Desembolso",
    "Desembolso",
    "Reclamo",
    "Valoracion",
    "Reembolso",
    "Viaje",
    "Viaje_Vehiculo",
    "Parada_Viaje",
    "alembic_version",
)

FIXTURE_ID = "a1000000-0000-4000-8000-000000000001"
AUTH_FIXTURE_ID = "a1000000-0000-4000-8000-000000000002"
PROFILE_ROLE_ID = "a1000000-0000-4000-8000-000000000003"
PROFILE_ID = "a1000000-0000-4000-8000-000000000004"
SERVICE_TYPE_IDS = (
    "a1000000-0000-4000-8000-000000000005",
    "a1000000-0000-4000-8000-000000000006",
)
AVAILABLE_SERVICE_IDS = (
    "a1000000-0000-4000-8000-000000000007",
    "a1000000-0000-4000-8000-000000000008",
)
TRIP_ID = "a1000000-0000-4000-8000-000000000009"
STOP_IDS = (
    "a1000000-0000-4000-8000-000000000010",
    "a1000000-0000-4000-8000-000000000011",
)


def upgrade() -> None:
    table_literals = ", ".join(f"'{name}'" for name in PUBLIC_TABLES)
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

    # This is a synthetic, non-login fixture only. No row is created in auth.users,
    # and there are no verification, payment, or payout records.
    statements = (
        f'''INSERT INTO public."Rol_Usuario" ("ID", "Rol") VALUES ('{FIXTURE_ID}', '[DEMO] fixture owner') ON CONFLICT ("ID") DO NOTHING''',
        f'''INSERT INTO public."Usuario" ("ID", "ID_Auth_Supabase", "Nombre", "Apellido", "Correo", "ID_Rol") VALUES ('{AUTH_FIXTURE_ID}', '{AUTH_FIXTURE_ID}', '[DEMO] Cuenta', 'de prueba', 'amira-fixture@example.invalid', '{FIXTURE_ID}') ON CONFLICT ("ID") DO NOTHING''',
        f'''INSERT INTO public."Rol_Perfil" ("ID", "Rol") VALUES ('{PROFILE_ROLE_ID}', '[DEMO] proveedor de prueba') ON CONFLICT ("ID") DO NOTHING''',
        f'''INSERT INTO public."Perfil" ("ID", "ID_user", "Descripcion", "Nombre", "Rol_Perfil", "Ubicacion") VALUES ('{PROFILE_ID}', '{AUTH_FIXTURE_ID}', '[DEMO] Registro de ejemplo para validar el catálogo.', '[DEMO] Transporte de prueba', '{PROFILE_ROLE_ID}', 'Santiago') ON CONFLICT ("ID") DO NOTHING''',
        f'''INSERT INTO public."Tipos_Servicio" ("ID", "Nombre_servicio") VALUES ('{SERVICE_TYPE_IDS[0]}', '[DEMO] Mudanzas'), ('{SERVICE_TYPE_IDS[1]}', '[DEMO] Carga compartida') ON CONFLICT ("ID") DO NOTHING''',
        f'''INSERT INTO public."Servicios_Disponibles" ("ID", "ID_Perfil", "ID_Tipo_Servicio") VALUES ('{AVAILABLE_SERVICE_IDS[0]}', '{PROFILE_ID}', '{SERVICE_TYPE_IDS[0]}'), ('{AVAILABLE_SERVICE_IDS[1]}', '{PROFILE_ID}', '{SERVICE_TYPE_IDS[1]}') ON CONFLICT ("ID") DO NOTHING''',
        f'''INSERT INTO public."Viaje" ("ID", "ID_Perfil", "Origen", "Destino", "Estado", "Fecha_Salida", "Publicado", "Acepta_Solicitudes") VALUES ('{TRIP_ID}', '{PROFILE_ID}', 'Santiago', 'Valparaíso', '[DEMO] publicado', '2026-11-15 09:00:00+00', TRUE, TRUE) ON CONFLICT ("ID") DO NOTHING''',
        f'''INSERT INTO public."Parada_Viaje" ("ID", "ID_Viaje", "Orden", "Direccion", "Fecha_Hora_Estimada", "Estado") VALUES ('{STOP_IDS[0]}', '{TRIP_ID}', 1, '[DEMO] Casablanca', '2026-11-15 11:00:00+00', '[DEMO] estimada'), ('{STOP_IDS[1]}', '{TRIP_ID}', 2, '[DEMO] Valparaíso', '2026-11-15 13:00:00+00', '[DEMO] estimada') ON CONFLICT ("ID") DO NOTHING''',
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    # Keep the default-deny security posture and fixtures intact on downgrade.
    pass
