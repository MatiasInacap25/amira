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
        AND ("ID_Auth_Supabase" <> 'b3000000-0000-4000-8000-00000000000a'
             OR "Correo" <> 'demo-compania@example.invalid' OR "Nombre" <> '[DEMO] Elena'
             OR "Apellido" <> 'Dueña' OR "ID_Rol" <> owner_role)) THEN
        RAISE EXCEPTION 'Company demo owner ID conflicts with a non-fixture row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Perfil" WHERE "ID" = 'b3000000-0000-4000-8000-000000000002'
        AND ("ID_user" <> 'b3000000-0000-4000-8000-000000000001'
             OR "Nombre" <> '[DEMO] Logística del Valle' OR kind <> 'company'
             OR "Rol_Perfil" <> company_role OR "Rut_Empresa" <> 'DEMO-76000000')) THEN
        RAISE EXCEPTION 'Company demo profile ID conflicts with a non-fixture row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Usuario" WHERE "ID" = 'b3000000-0000-4000-8000-000000000003'
        AND ("ID_Auth_Supabase" <> 'b3000000-0000-4000-8000-00000000000b'
             OR "Correo" <> 'demo-mateo@example.invalid' OR "Nombre" <> '[DEMO] Mateo'
             OR "Apellido" <> 'Silva' OR "ID_Rol" <> driver_role)) THEN
        RAISE EXCEPTION 'First company demo driver ID conflicts with a non-fixture row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Usuario" WHERE "ID" = 'b3000000-0000-4000-8000-000000000004'
        AND ("ID_Auth_Supabase" <> 'b3000000-0000-4000-8000-00000000000c'
             OR "Correo" <> 'demo-lucia@example.invalid' OR "Nombre" <> '[DEMO] Lucía'
             OR "Apellido" <> 'Rojas' OR "ID_Rol" <> driver_role)) THEN
        RAISE EXCEPTION 'Second company demo driver ID conflicts with a non-fixture row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Conductor" WHERE "ID" = 'b3000000-0000-4000-8000-000000000005'
        AND ("ID_user" <> 'b3000000-0000-4000-8000-000000000003'
             OR "ID_perfil" <> 'b3000000-0000-4000-8000-000000000002'
             OR "Tipo_Conductor" <> driver_type OR "Rol" <> '[DEMO] Conductor'))
       OR EXISTS (SELECT 1 FROM public."Conductor" WHERE "ID" = 'b3000000-0000-4000-8000-000000000006'
        AND ("ID_user" <> 'b3000000-0000-4000-8000-000000000004'
             OR "ID_perfil" <> 'b3000000-0000-4000-8000-000000000002'
             OR "Tipo_Conductor" <> driver_type OR "Rol" <> '[DEMO] Conductora')) THEN
        RAISE EXCEPTION 'Company demo driver record IDs conflict with non-fixture rows';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Vehiculo" WHERE "ID" = 'b3000000-0000-4000-8000-000000000007'
        AND ("ID_Perfil" <> 'b3000000-0000-4000-8000-000000000002'
             OR "Patente" <> 'DEMO-001' OR "Marca" <> 'Volvo' OR "Modelo" <> 'FH de muestra'
             OR "Año" <> 2022 OR "Peso_maximo" <> 18000 OR "Imagen_Storage_Key" <> 'fixture-only/no-image'))
       OR EXISTS (SELECT 1 FROM public."Vehiculo" WHERE "ID" = 'b3000000-0000-4000-8000-000000000008'
        AND ("ID_Perfil" <> 'b3000000-0000-4000-8000-000000000002'
             OR "Patente" <> 'DEMO-002' OR "Marca" <> 'Mercedes-Benz' OR "Modelo" <> 'Actros de muestra'
             OR "Año" <> 2021 OR "Peso_maximo" <> 12000 OR "Imagen_Storage_Key" <> 'fixture-only/no-image')) THEN
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
