"""Provider vehicles: owner registration with one photo, duplicate plates, signed photo reads, and safe deletion."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.evidence_storage import EvidenceStorageError
from amira_api.vehicle_routes import get_vehicle_image_storage_resolver
from amira_api.main import app
from amira_api.models import (
    Base,
    Conductor,
    Perfil,
    RolPerfil,
    RolUsuario,
    ServicioAsignacion,
    Usuario,
    Vehiculo,
    Viaje,
    ViajeVehiculo,
)
from amira_api.settings import Settings, get_settings
from chat_support import _register_btrim

OWNER_AUTH = UUID("7c2e0d11-3a4b-4c5d-8e6f-000000000001")
OTHER_OWNER_AUTH = UUID("7c2e0d11-3a4b-4c5d-8e6f-000000000002")
INDEPENDENT_AUTH = UUID("7c2e0d11-3a4b-4c5d-8e6f-000000000003")
CUSTOMER_AUTH = UUID("7c2e0d11-3a4b-4c5d-8e6f-000000000004")
EMPLOYED_DRIVER_AUTH = UUID("7c2e0d11-3a4b-4c5d-8e6f-000000000005")
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
HTML = b"<html><script>alert(1)</script></html>"
SIGNED_BASE = "https://storage.example.test"
MAX_BYTES = 5 * 1024 * 1024
CONFIGURED = {
    "supabase_url": "https://project.example.test",
    "supabase_service_role_key": "service-role-test",
    "vehicle_images_bucket": "vehicle-images",
}


class FakeVehicleImageStorage:
    def __init__(self) -> None:
        self.fail_upload = False
        self.uploads: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []
        self.signed: list[tuple[str, int]] = []

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        if self.fail_upload:
            raise EvidenceStorageError("storage unavailable")
        self.uploads[key] = (content, content_type)

    def delete(self, key: str) -> None:
        self.deleted.append(key)

    def create_signed_url(self, key: str, expires_in: int) -> str:
        self.signed.append((key, expires_in))
        return f"{SIGNED_BASE}/{key}?token=signed"


@dataclass
class Fleet:
    owner: Usuario
    other_owner: Usuario
    company: Perfil
    other_company: Perfil


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _register_btrim)
    tables = (
        "Rol_Usuario", "Rol_Perfil", "Usuario", "Perfil", "Conductor", "Vehiculo",
        "Formulario_servicio", "Servicio", "Viaje", "Viaje_Vehiculo", "Servicio_Asignacion",
    )
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in tables])
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def storage() -> FakeVehicleImageStorage:
    return FakeVehicleImageStorage()


class VehicleApi:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def as_user(self, auth_id: UUID) -> None:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )

    def configure(self, **overrides) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **{**CONFIGURED, **overrides})

    def create(self, *, as_auth_id: UUID, photo: bytes = JPEG, filename: str = "auto.jpg",
               content_type: str = "image/jpeg", **fields):
        self.as_user(as_auth_id)
        data = {"plate": "ABCD12", "brand": "Hyundai", "model": "Porter", **fields}
        return self.client.post("/api/provider/vehicles", data=data, files={"photo": (filename, photo, content_type)})

    def list(self, *, as_auth_id: UUID):
        self.as_user(as_auth_id)
        return self.client.get("/api/provider/vehicles")

    def delete(self, vehicle_id, *, as_auth_id: UUID):
        self.as_user(as_auth_id)
        return self.client.delete(f"/api/provider/vehicles/{vehicle_id}")


@pytest.fixture
def api(db: Session, storage: FakeVehicleImageStorage):
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_vehicle_image_storage_resolver] = lambda: (lambda: storage)
    vehicle_api = VehicleApi(client=TestClient(app))
    vehicle_api.configure()
    yield vehicle_api
    for dependency in (get_db_session, get_current_user, get_vehicle_image_storage_resolver, get_settings):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture
def fleet(db: Session) -> Fleet:
    roles = {code: RolUsuario(id=uuid4(), name=code, code=code)
             for code in ("client", "company_owner", "company_driver", "independent_driver")}
    profile_roles = {code: RolPerfil(id=uuid4(), name=code, code=code) for code in ("company", "independent_driver")}
    db.add_all([*roles.values(), *profile_roles.values()])
    db.flush()

    def user(auth_id: UUID, role: str, email: str) -> Usuario:
        row = Usuario(id=uuid4(), auth_user_id=auth_id, first_name="Pat", last_name="Test", email=email,
                      phone=None, national_id=None, role_id=roles[role].id)
        db.add(row)
        db.flush()
        return row

    def profile(owner: Usuario, kind: str, name: str) -> Perfil:
        row = Perfil(id=uuid4(), owner_user_id=owner.id, name=name, kind=kind, role_id=profile_roles[kind].id)
        db.add(row)
        db.flush()
        return row

    owner = user(OWNER_AUTH, "company_owner", "owner@example.test")
    other_owner = user(OTHER_OWNER_AUTH, "company_owner", "other@example.test")
    independent = user(INDEPENDENT_AUTH, "independent_driver", "independent@example.test")
    user(CUSTOMER_AUTH, "client", "customer@example.test")
    employed = user(EMPLOYED_DRIVER_AUTH, "company_driver", "employed@example.test")
    company = profile(owner, "company", "Transportes Norte")
    other_company = profile(other_owner, "company", "Otra Logística")
    profile(independent, "independent_driver", "Solo Fletes")
    db.add(Conductor(id=uuid4(), user_id=employed.id, employer_profile_id=company.id, driver_type_id=uuid4()))
    db.commit()
    return Fleet(owner=owner, other_owner=other_owner, company=company, other_company=other_company)


def _vehicles(db: Session) -> list[Vehiculo]:
    return db.query(Vehiculo).all()


def test_owner_creates_a_vehicle_with_its_photo_in_one_request(api, db: Session, fleet, storage):
    response = api.create(as_auth_id=OWNER_AUTH, year="2019", maximum_weight="1200.5")

    assert response.status_code == 201
    vehicle_id = response.json()["vehicleId"]
    rows = _vehicles(db)
    assert len(rows) == 1
    row = rows[0]
    assert str(row.id) == vehicle_id
    assert row.profile_id == fleet.company.id
    assert (row.plate, row.brand, row.model, row.year) == ("ABCD12", "Hyundai", "Porter", 2019)
    assert str(row.maximum_weight) == "1200.50"
    assert row.image_storage_key.startswith(f"vehicles/{fleet.company.id}/")
    assert row.image_storage_key.endswith(".jpg")
    assert storage.uploads[row.image_storage_key] == (JPEG, "image/jpeg")


def test_a_duplicate_plate_after_trim_and_case_is_refused_with_409(api, db: Session, fleet, storage):
    assert api.create(as_auth_id=OWNER_AUTH).status_code == 201

    response = api.create(as_auth_id=OWNER_AUTH, plate="  abcd12 ", photo=PNG, filename="b.png", content_type="image/png")

    assert response.status_code == 409
    assert response.json()["detail"] == "Ya existe un vehículo registrado con esta patente."
    assert len(_vehicles(db)) == 1
    assert len(storage.uploads) == 1


@pytest.mark.parametrize("fields", [{"year": "1885"}, {"year": "2201"}, {"maximum_weight": "0"}, {"maximum_weight": "-5"}])
def test_an_invalid_year_or_weight_is_refused_with_422_and_nothing_is_stored(api, db: Session, fleet, storage, fields):
    response = api.create(as_auth_id=OWNER_AUTH, **fields)

    assert response.status_code == 422
    assert _vehicles(db) == []
    assert storage.uploads == {}


def test_a_non_image_with_an_image_extension_is_refused_with_415(api, db: Session, fleet, storage):
    response = api.create(as_auth_id=OWNER_AUTH, photo=HTML, filename="auto.jpg")

    assert response.status_code == 415
    assert _vehicles(db) == []
    assert storage.uploads == {}


def test_a_customer_is_refused_with_403(api, db: Session, fleet, storage):
    response = api.create(as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 403
    assert _vehicles(db) == []
    assert storage.uploads == {}


def test_a_driver_employed_by_a_company_is_refused_with_403(api, db: Session, fleet, storage):
    response = api.create(as_auth_id=EMPLOYED_DRIVER_AUTH)

    assert response.status_code == 403
    assert _vehicles(db) == []


def test_the_list_returns_only_the_callers_vehicles_with_signed_photo_urls(api, db: Session, fleet, storage):
    api.create(as_auth_id=OWNER_AUTH)
    api.create(as_auth_id=OTHER_OWNER_AUTH, plate="ZZZZ99", photo=PNG, filename="x.png", content_type="image/png")

    response = api.list(as_auth_id=OWNER_AUTH)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["plate"] for item in items] == ["ABCD12"]
    key = _vehicles(db)[0].image_storage_key
    assert items[0]["url"] == f"{SIGNED_BASE}/{key}?token=signed"
    assert items[0]["expiresAt"]
    assert storage.signed == [(key, 300)]


def test_another_provider_cannot_list_or_delete_a_vehicle(api, db: Session, fleet, storage):
    created = api.create(as_auth_id=OWNER_AUTH)
    vehicle_id = created.json()["vehicleId"]

    listing = api.list(as_auth_id=OTHER_OWNER_AUTH)
    deleted = api.delete(vehicle_id, as_auth_id=OTHER_OWNER_AUTH)

    assert listing.status_code == 200
    assert listing.json()["items"] == []
    assert deleted.status_code == 404
    assert deleted.json() == api.delete(uuid4(), as_auth_id=OTHER_OWNER_AUTH).json()
    assert len(_vehicles(db)) == 1
    assert storage.deleted == []


def test_the_owner_deletes_an_unreferenced_vehicle_and_its_photo(api, db: Session, fleet, storage):
    vehicle_id = api.create(as_auth_id=OWNER_AUTH).json()["vehicleId"]
    key = _vehicles(db)[0].image_storage_key

    response = api.delete(vehicle_id, as_auth_id=OWNER_AUTH)

    assert response.status_code == 204
    assert _vehicles(db) == []
    assert storage.deleted == [key]


def test_delete_is_refused_with_409_while_a_service_assignment_references_the_vehicle(api, db: Session, fleet, storage):
    vehicle_id = api.create(as_auth_id=OWNER_AUTH).json()["vehicleId"]
    driver = db.query(Conductor).one()
    db.add(ServicioAsignacion(
        id=uuid4(), service_id=uuid4(), driver_id=driver.id, vehicle_id=UUID(vehicle_id), assigned_by_user_id=fleet.owner.id,
    ))
    db.commit()

    response = api.delete(vehicle_id, as_auth_id=OWNER_AUTH)

    assert response.status_code == 409
    assert len(_vehicles(db)) == 1
    assert storage.deleted == []


def test_delete_is_refused_with_409_while_a_shared_trip_references_the_vehicle(api, db: Session, fleet, storage):
    vehicle_id = api.create(as_auth_id=OWNER_AUTH).json()["vehicleId"]
    driver = db.query(Conductor).one()
    trip = Viaje(id=uuid4(), profile_id=fleet.company.id, origin="Santiago", destination="Valparaíso", status="published")
    db.add(trip)
    db.flush()
    db.add(ViajeVehiculo(trip_id=trip.id, vehicle_id=UUID(vehicle_id), driver_id=driver.id))
    db.commit()

    response = api.delete(vehicle_id, as_auth_id=OWNER_AUTH)

    assert response.status_code == 409
    assert len(_vehicles(db)) == 1
    assert storage.deleted == []


def test_an_unset_bucket_fails_closed_with_503_and_writes_nothing(api, db: Session, fleet, storage):
    # The real resolver must run here, so the fake storage from the fixture is removed for this test only.
    app.dependency_overrides.pop(get_vehicle_image_storage_resolver, None)
    api.configure(vehicle_images_bucket=None)

    response = api.create(as_auth_id=OWNER_AUTH)

    assert response.status_code == 503
    assert _vehicles(db) == []
    assert storage.uploads == {}


def test_a_failed_storage_upload_answers_502_and_writes_no_row(api, db: Session, fleet, storage):
    storage.fail_upload = True

    response = api.create(as_auth_id=OWNER_AUTH)

    assert response.status_code == 502
    assert _vehicles(db) == []
