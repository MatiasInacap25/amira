-- LOCAL TEST FIXTURE ONLY. Do not add this file to Alembic or apply it to Supabase.
-- Synthetic application rows only: this does not write to auth.users or create credentials.
BEGIN;

DO $$
DECLARE
    owner_role uuid;
    company_role uuid;
    driver_role uuid;
    driver_type uuid := 'b3000000-0000-4000-8000-000000000009';
BEGIN
    SELECT "ID" INTO owner_role FROM public."Rol_Usuario" WHERE code = 'company_owner';
    SELECT "ID" INTO driver_role FROM public."Rol_Usuario" WHERE code = 'company_driver';
    SELECT "ID" INTO company_role FROM public."Rol_Perfil" WHERE code = 'company';
    IF owner_role IS NULL OR driver_role IS NULL OR company_role IS NULL THEN
        RAISE EXCEPTION 'Canonical company profile/account roles are required for this local fixture';
    END IF;

    INSERT INTO public."Tipo_Conductor" ("ID", "Rol")
    VALUES (driver_type, '[DEMO] Conductor de empresa')
    ON CONFLICT ("ID") DO NOTHING;
    IF NOT EXISTS (
        SELECT 1 FROM public."Tipo_Conductor"
        WHERE "ID" = driver_type AND "Rol" = '[DEMO] Conductor de empresa'
    ) THEN
        RAISE EXCEPTION 'Synthetic driver type ID conflicts with a non-fixture row';
    END IF;

    IF EXISTS (SELECT 1 FROM public."Usuario" WHERE "ID" = 'b3000000-0000-4000-8000-000000000001'
        AND ("ID_Auth_Supabase" IS DISTINCT FROM 'b3000000-0000-4000-8000-00000000000a'
             OR "Correo" IS DISTINCT FROM 'demo-compania@example.invalid' OR "Nombre" IS DISTINCT FROM '[DEMO] Elena'
             OR "Apellido" IS DISTINCT FROM 'Dueña' OR "ID_Rol" IS DISTINCT FROM owner_role)) THEN
        RAISE EXCEPTION 'Company demo owner ID conflicts with a non-fixture row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Perfil" WHERE "ID" = 'b3000000-0000-4000-8000-000000000002'
        AND ("ID_user" IS DISTINCT FROM 'b3000000-0000-4000-8000-000000000001'
             OR "Nombre" IS DISTINCT FROM '[DEMO] Logística del Valle' OR kind IS DISTINCT FROM 'company'
             OR "Rol_Perfil" IS DISTINCT FROM company_role OR "Rut_Empresa" IS DISTINCT FROM 'DEMO-76000000')) THEN
        RAISE EXCEPTION 'Company demo profile ID conflicts with a non-fixture row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Usuario" WHERE "ID" = 'b3000000-0000-4000-8000-000000000003'
        AND ("ID_Auth_Supabase" IS DISTINCT FROM 'b3000000-0000-4000-8000-00000000000b'
             OR "Correo" IS DISTINCT FROM 'demo-mateo@example.invalid' OR "Nombre" IS DISTINCT FROM '[DEMO] Mateo'
             OR "Apellido" IS DISTINCT FROM 'Silva' OR "ID_Rol" IS DISTINCT FROM driver_role)) THEN
        RAISE EXCEPTION 'First company demo driver ID conflicts with a non-fixture row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Usuario" WHERE "ID" = 'b3000000-0000-4000-8000-000000000004'
        AND ("ID_Auth_Supabase" IS DISTINCT FROM 'b3000000-0000-4000-8000-00000000000c'
             OR "Correo" IS DISTINCT FROM 'demo-lucia@example.invalid' OR "Nombre" IS DISTINCT FROM '[DEMO] Lucía'
             OR "Apellido" IS DISTINCT FROM 'Rojas' OR "ID_Rol" IS DISTINCT FROM driver_role)) THEN
        RAISE EXCEPTION 'Second company demo driver ID conflicts with a non-fixture row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Conductor" WHERE "ID" = 'b3000000-0000-4000-8000-000000000005'
        AND ("ID_user" IS DISTINCT FROM 'b3000000-0000-4000-8000-000000000003'
             OR "ID_perfil" IS DISTINCT FROM 'b3000000-0000-4000-8000-000000000002'
             OR "Tipo_Conductor" IS DISTINCT FROM driver_type OR "Rol" IS DISTINCT FROM '[DEMO] Conductor'))
       OR EXISTS (SELECT 1 FROM public."Conductor" WHERE "ID" = 'b3000000-0000-4000-8000-000000000006'
        AND ("ID_user" IS DISTINCT FROM 'b3000000-0000-4000-8000-000000000004'
             OR "ID_perfil" IS DISTINCT FROM 'b3000000-0000-4000-8000-000000000002'
             OR "Tipo_Conductor" IS DISTINCT FROM driver_type OR "Rol" IS DISTINCT FROM '[DEMO] Conductora')) THEN
        RAISE EXCEPTION 'Company demo driver record IDs conflict with non-fixture rows';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Vehiculo" WHERE "ID" = 'b3000000-0000-4000-8000-000000000007'
        AND ("ID_Perfil" IS DISTINCT FROM 'b3000000-0000-4000-8000-000000000002'
             OR "Patente" IS DISTINCT FROM 'DEMO-001' OR "Marca" IS DISTINCT FROM 'Volvo' OR "Modelo" IS DISTINCT FROM 'FH de muestra'
             OR "Año" IS DISTINCT FROM 2022 OR "Peso_maximo" IS DISTINCT FROM 18000 OR "Imagen_Storage_Key" IS DISTINCT FROM 'fixture-only/no-image'))
       OR EXISTS (SELECT 1 FROM public."Vehiculo" WHERE "ID" = 'b3000000-0000-4000-8000-000000000008'
        AND ("ID_Perfil" IS DISTINCT FROM 'b3000000-0000-4000-8000-000000000002'
             OR "Patente" IS DISTINCT FROM 'DEMO-002' OR "Marca" IS DISTINCT FROM 'Mercedes-Benz' OR "Modelo" IS DISTINCT FROM 'Actros de muestra'
             OR "Año" IS DISTINCT FROM 2021 OR "Peso_maximo" IS DISTINCT FROM 12000 OR "Imagen_Storage_Key" IS DISTINCT FROM 'fixture-only/no-image')) THEN
        RAISE EXCEPTION 'Company demo vehicle IDs conflict with non-fixture rows';
    END IF;

    INSERT INTO public."Usuario" ("ID", "ID_Auth_Supabase", "Nombre", "Apellido", "Correo", "ID_Rol")
    VALUES
        ('b3000000-0000-4000-8000-000000000001', 'b3000000-0000-4000-8000-00000000000a', '[DEMO] Elena', 'Dueña', 'demo-compania@example.invalid', owner_role),
        ('b3000000-0000-4000-8000-000000000003', 'b3000000-0000-4000-8000-00000000000b', '[DEMO] Mateo', 'Silva', 'demo-mateo@example.invalid', driver_role),
        ('b3000000-0000-4000-8000-000000000004', 'b3000000-0000-4000-8000-00000000000c', '[DEMO] Lucía', 'Rojas', 'demo-lucia@example.invalid', driver_role)
    ON CONFLICT ("ID") DO NOTHING;

    INSERT INTO public."Perfil" ("ID", "ID_user", "Nombre", "Descripcion", "Rol_Perfil", "Ubicacion", "Rut_Empresa", kind, public_activated_at)
    VALUES ('b3000000-0000-4000-8000-000000000002', 'b3000000-0000-4000-8000-000000000001',
        '[DEMO] Logística del Valle', '[DEMO] Perfil sintético para pruebas locales.', company_role,
        'Santiago, Región Metropolitana', 'DEMO-76000000', 'company', now())
    ON CONFLICT ("ID") DO NOTHING;

    INSERT INTO public."Conductor" ("ID", "ID_user", "ID_perfil", "Rol", "Tipo_Conductor", "Ubicacion")
    VALUES
        ('b3000000-0000-4000-8000-000000000005', 'b3000000-0000-4000-8000-000000000003', 'b3000000-0000-4000-8000-000000000002', '[DEMO] Conductor', driver_type, 'Santiago'),
        ('b3000000-0000-4000-8000-000000000006', 'b3000000-0000-4000-8000-000000000004', 'b3000000-0000-4000-8000-000000000002', '[DEMO] Conductora', driver_type, 'Santiago')
    ON CONFLICT ("ID") DO NOTHING;

    INSERT INTO public."Vehiculo" ("ID", "ID_Perfil", "Patente", "Marca", "Modelo", "Año", "Peso_maximo", "Imagen_Storage_Key")
    VALUES
        ('b3000000-0000-4000-8000-000000000007', 'b3000000-0000-4000-8000-000000000002', 'DEMO-001', 'Volvo', 'FH de muestra', 2022, 18000, 'fixture-only/no-image'),
        ('b3000000-0000-4000-8000-000000000008', 'b3000000-0000-4000-8000-000000000002', 'DEMO-002', 'Mercedes-Benz', 'Actros de muestra', 2021, 12000, 'fixture-only/no-image')
    ON CONFLICT ("ID") DO NOTHING;
END $$;

COMMIT;
