from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "company_profile_demo.sql"


def test_company_demo_fixture_is_local_only_and_uses_canonical_roles():
    sql = FIXTURE.read_text(encoding="utf-8")

    assert "LOCAL TEST FIXTURE ONLY" in sql
    assert "Rol_Usuario\" WHERE code = 'company_owner'" in sql
    assert "Rol_Usuario\" WHERE code = 'company_driver'" in sql
    assert "Rol_Perfil\" WHERE code = 'company'" in sql
    assert "[DEMO] proveedor de prueba" not in sql
    assert "INSERT INTO auth.users" not in sql
    assert "@example.invalid" in sql
    assert "ON CONFLICT (\"ID\") DO NOTHING" in sql
    assert "RAISE EXCEPTION" in sql


def test_company_demo_fixture_only_seeds_two_linked_drivers_and_two_demo_vehicles():
    sql = FIXTURE.read_text(encoding="utf-8")

    assert "INSERT INTO public.\"Conductor\"" in sql
    driver_values = sql.split('INSERT INTO public."Conductor"', 1)[1].split("ON CONFLICT", 1)[0]
    assert driver_values.count("'[DEMO] Conductor'") == 1
    assert driver_values.count("'[DEMO] Conductora'") == 1
    assert "DEMO-001" in sql and "DEMO-002" in sql
    assert "public.\"Perfil\"" in sql
    assert "'company'" in sql
    assert "public.\"Rol_Perfil\"" in sql
    assert "UPDATE public.\"Perfil\"" not in sql
    assert "DELETE FROM" not in sql


def test_nullable_fixture_identity_fields_detect_null_collisions():
    sql = FIXTURE.read_text(encoding="utf-8")

    assert '"Rut_Empresa" IS DISTINCT FROM' in sql
    assert '"Rol" IS DISTINCT FROM' in sql
    assert '"Año" IS DISTINCT FROM' in sql
    assert '"Peso_maximo" IS DISTINCT FROM' in sql
