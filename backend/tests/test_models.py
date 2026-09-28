from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from sqlalchemy.orm import configure_mappers

from amira_api.models import Base


def test_mappers_configure_and_all_expected_tables_are_registered() -> None:
    configure_mappers()

    assert {
        "Usuario",
        "Perfil",
        "Conductor",
        "Vehiculo",
        "Viaje_Vehiculo",
        "Pago",
        "Desembolso",
        "Reembolso",
        "Cuenta_Desembolso",
    } <= set(Base.metadata.tables)


def test_user_links_to_supabase_auth_without_local_password_storage() -> None:
    user = Base.metadata.tables["Usuario"]

    assert user.c["ID_Auth_Supabase"].unique is True
    assert "Hash_Contraseña" not in user.c
    assert "ID_Auth_Supabase" in user.c


def test_vehicle_has_one_required_storage_image_and_required_identity_fields() -> None:
    vehicle = Base.metadata.tables["Vehiculo"]

    for name in ("Patente", "Marca", "Modelo", "Imagen_Storage_Key"):
        assert vehicle.c[name].nullable is False
    assert "Año" in vehicle.c and vehicle.c["Año"].nullable is True
    assert "Peso_maximo" in vehicle.c and vehicle.c["Peso_maximo"].nullable is True


def test_trip_vehicle_assignment_is_composite_and_required() -> None:
    assignment = Base.metadata.tables["Viaje_Vehiculo"]

    assert {"ID_Viaje", "ID_Vehiculo"} == {
        column.name for column in assignment.primary_key.columns
    }
    assert assignment.c["ID_Conductor"].nullable is False


def test_postgresql_ddl_contains_compound_service_assignment_fk() -> None:
    service = Base.metadata.tables["Servicio"]
    ddl = str(CreateTable(service).compile(dialect=postgresql.dialect()))

    assert 'FOREIGN KEY("ID_Viaje", "ID_Vehiculo")' in ddl
    assert 'REFERENCES "Viaje_Vehiculo" ("ID_Viaje", "ID_Vehiculo")' in ddl


def test_driver_and_public_profile_are_separate_memberships() -> None:
    driver = Base.metadata.tables["Conductor"]
    profile = Base.metadata.tables["Perfil"]

    assert any(
        constraint.name == "uq_conductor_user"
        for constraint in driver.constraints
    )
    assert driver.c["ID_perfil"].nullable is False
    assert profile.c["ID_user"].unique is True
    assert profile.c["Rut_Empresa"].nullable is True
