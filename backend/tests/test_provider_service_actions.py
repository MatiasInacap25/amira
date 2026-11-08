"""Provider assignment and start actions over an in-memory database.

Assignments are owner-only and need a confirmed service. Drivers must be employed by the profile (or be the
independent owner's own driver row) and vehicles must belong to the profile. A same-day conflict (a driver with
another unfinished service on the same calendar day in America/Santiago) answers 409 with the conflicts unless the
request confirms them. Start is open to the owner and to assigned drivers; a service the viewer cannot see is 404.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.evidence_storage import get_evidence_storage_resolver
from amira_api.main import app
from amira_api.models import (
    Chat,
    Commune,
    Conductor,
    Cotizacion,
    FormularioServicio,
    Perfil,
    RolUsuario,
    Servicio,
    ServicioAsignacion,
    ServicioUbicacion,
    TipoServicio,
    Usuario,
    Vehiculo,
)
from amira_api.settings import Settings, get_settings
from test_provider_service_routes import (  # noqa: F401  (pytest fixture re-export)
    CUSTOMER_AUTH,
    EMPLOYED_DRIVER_AUTH,
    INDEPENDENT_AUTH,
    OTHER_CUSTOMER_AUTH,
    OWNER_AUTH,
    db,
)

GUS_AUTH = UUID("5a0e0c3e-1b7a-4d0e-9a51-000000000007")
OUTSIDER_AUTH = UUID("5a0e0c3e-1b7a-4d0e-9a51-000000000008")
OUTSIDER_DRIVER_AUTH = UUID("5a0e0c3e-1b7a-4d0e-9a51-000000000009")


@pytest.fixture
def call(db: Session):
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app)

    def send(method: str, path: str, *, as_auth_id: UUID, json: dict | None = None):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=as_auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
        return client.request(method, path, json=json)

    yield send
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@dataclass
class Fleet:
    owner: Usuario
    eli_user: Usuario
    eli: Conductor
    gus: Conductor
    company: Perfil
    van: Vehiculo
    truck: Vehiculo
    dana: Conductor
    solo_van: Vehiculo
    solo_service: Servicio
    outsider_driver: Conductor
    outsider_van: Vehiculo
    service_a: Servicio  # company, confirmed, Oct 20 15:00 UTC, assigned to Eli and the van
    service_same_day: Servicio  # company, confirmed, Oct 21 01:00 UTC (Oct 20 in Santiago), assigned to Eli
    service_next_day: Servicio  # company, confirmed, Oct 21 15:00 UTC (Oct 21 in Santiago), unassigned


@pytest.fixture
def fleet(db: Session) -> Fleet:
    roles = {code: RolUsuario(id=uuid4(), name=code, code=code)
             for code in ("client", "company_owner", "company_driver", "independent_driver")}
    db.add_all(roles.values())

    def user(auth_id, first, last, role):
        row = Usuario(id=uuid4(), auth_user_id=auth_id, first_name=first, last_name=last,
                      email=f"{first.lower()}@example.test", role_id=roles[role].id)
        db.add(row)
        return row

    customer = user(CUSTOMER_AUTH, "Casey", "Customer", "client")
    owner = user(OWNER_AUTH, "Pat", "Owner", "company_owner")
    eli_user = user(EMPLOYED_DRIVER_AUTH, "Eli", "Employee", "company_driver")
    gus_user = user(GUS_AUTH, "Gus", "Second", "company_driver")
    dana_user = user(INDEPENDENT_AUTH, "Dana", "Driver", "independent_driver")
    outsider_owner = user(OUTSIDER_AUTH, "Ana", "Outsider", "company_owner")
    outsider_driver_user = user(OUTSIDER_DRIVER_AUTH, "Lu", "Outside", "company_driver")

    company = Perfil(id=uuid4(), owner_user_id=owner.id, name="Transportes Norte", kind="company", role_id=uuid4())
    solo = Perfil(id=uuid4(), owner_user_id=dana_user.id, name="Dana Fletes", kind="independent_driver", role_id=uuid4())
    outsider = Perfil(id=uuid4(), owner_user_id=outsider_owner.id, name="Otra Empresa", kind="company", role_id=uuid4())
    db.add_all([company, solo, outsider])
    db.flush()

    def conductor(user_row, employer):
        row = Conductor(id=uuid4(), user_id=user_row.id, employer_profile_id=employer.id if employer else None,
                        driver_type_id=uuid4())
        db.add(row)
        return row

    eli = conductor(eli_user, company)
    gus = conductor(gus_user, company)
    dana = conductor(dana_user, None)
    outsider_driver = conductor(outsider_driver_user, outsider)

    def vehicle(profile, plate, brand, model):
        row = Vehiculo(id=uuid4(), profile_id=profile.id, plate=plate, brand=brand, model=model,
                       image_storage_key=f"vehicles/{plate.lower()}.webp")
        db.add(row)
        return row

    van = vehicle(company, "ABCD12", "Hyundai", "Porter")
    truck = vehicle(company, "EFGH34", "Toyota", "Hiace")
    solo_van = vehicle(solo, "IJKL56", "Kia", "Frontier")
    outsider_van = vehicle(outsider, "MNOP78", "Ford", "Transit")
    mudanzas = TipoServicio(id=uuid4(), name="Mudanzas", slug="mudanzas")
    santiago = Commune(code="13101", region_code="13", name="Santiago")
    valparaiso = Commune(code="05101", region_code="05", name="Valparaíso")
    db.add_all([mudanzas, santiago, valparaiso])
    db.flush()

    def service(profile, service_at, status="confirmed"):
        created = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
        form = FormularioServicio(id=uuid4(), profile_id=profile.id, service_type_id=mudanzas.id, status="accepted",
                                  customer_id=customer.id, origin_commune_code="13101",
                                  destination_commune_code="05101", created_at=created)
        chat = Chat(id=uuid4(), form_id=form.id, created_at=created)
        quote = Cotizacion(id=uuid4(), chat_id=chat.id, status="paid", amount=Decimal("150000"), origin="A",
                           destination="B", service_type_id=mudanzas.id, currency="CLP", created_at=created)
        row = Servicio(id=uuid4(), profile_id=profile.id, customer_id=customer.id, status=status,
                       service_at=service_at, description="Mover un sofá", created_at=created,
                       amount=Decimal("150000"), form_id=form.id, accepted_quotation_id=quote.id)
        db.add_all([form, chat, quote, row])
        db.flush()
        return row

    service_a = service(company, datetime(2026, 10, 20, 15, tzinfo=timezone.utc))
    service_same_day = service(company, datetime(2026, 10, 21, 1, tzinfo=timezone.utc))
    service_next_day = service(company, datetime(2026, 10, 21, 15, tzinfo=timezone.utc))
    solo_service = service(solo, datetime(2026, 10, 20, 15, tzinfo=timezone.utc))
    db.add_all([
        ServicioAsignacion(id=uuid4(), service_id=service_a.id, driver_id=eli.id, vehicle_id=van.id,
                           assigned_by_user_id=owner.id),
        ServicioAsignacion(id=uuid4(), service_id=service_same_day.id, driver_id=eli.id, vehicle_id=van.id,
                           assigned_by_user_id=owner.id),
    ])
    db.commit()
    return Fleet(owner, eli_user, eli, gus, company, van, truck, dana, solo_van, solo_service,
                 outsider_driver, outsider_van, service_a, service_same_day, service_next_day)


def _assignments_url(service: Servicio) -> str:
    return f"/api/provider/services/{service.id}/assignments"


def _start_url(service: Servicio) -> str:
    return f"/api/provider/services/{service.id}/start"


def _pair(driver: Conductor, vehicle: Vehiculo) -> dict:
    return {"driverId": str(driver.id), "vehicleId": str(vehicle.id)}


def _put(call, fleet_service: Servicio, pairs: list[dict], *, auth=OWNER_AUTH, **extra):
    return call("PUT", _assignments_url(fleet_service), as_auth_id=auth, json={"assignments": pairs, **extra})


def _assignment_rows(db: Session, service: Servicio) -> list[ServicioAsignacion]:
    return list(db.execute(select(ServicioAsignacion).where(ServicioAsignacion.service_id == service.id)).scalars())


# --- T5: PUT /assignments ---------------------------------------------------------------------------------------------


def test_owner_assigns_a_driver_and_vehicle_and_records_who_assigned(call, db, fleet: Fleet):
    response = _put(call, fleet.service_a, [_pair(fleet.gus, fleet.truck)])

    assert response.status_code == 200
    body = response.json()
    assert body["canManage"] is True and body["status"] == "confirmed"
    assert body["assignments"] == [{
        "driverId": str(fleet.gus.id),
        "driverFirstName": "Gus",
        "vehicleId": str(fleet.truck.id),
        "vehicleLabel": "Toyota Hiace",
        "plate": "EFGH34",
    }]
    row = _assignment_rows(db, fleet.service_a)[0]
    assert row.assigned_by_user_id == fleet.owner.id
    assert row.assigned_at is not None


def test_put_replaces_every_existing_pair(call, db, fleet: Fleet):
    response = _put(call, fleet.service_a, [_pair(fleet.gus, fleet.truck)])

    assert response.status_code == 200
    assert [a["driverId"] for a in response.json()["assignments"]] == [str(fleet.gus.id)]
    assert [row.driver_id for row in _assignment_rows(db, fleet.service_a)] == [fleet.gus.id]


def test_independent_owner_can_assign_their_own_driver_row(call, fleet: Fleet):
    response = call("PUT", _assignments_url(fleet.solo_service), as_auth_id=INDEPENDENT_AUTH,
                    json={"assignments": [_pair(fleet.dana, fleet.solo_van)]})

    assert response.status_code == 200
    assert response.json()["assignments"][0]["driverId"] == str(fleet.dana.id)


def test_assigned_driver_gets_403_and_unseen_service_gets_404(call, fleet: Fleet):
    assigned = _put(call, fleet.service_a, [_pair(fleet.gus, fleet.truck)], auth=EMPLOYED_DRIVER_AUTH)
    unseen = _put(call, fleet.service_next_day, [_pair(fleet.gus, fleet.truck)], auth=EMPLOYED_DRIVER_AUTH)

    assert assigned.status_code == 403
    assert assigned.json()["detail"] == "Only the profile owner can manage this service."
    assert unseen.status_code == 404


def test_other_provider_and_customer_cannot_assign(call, fleet: Fleet):
    outsider = _put(call, fleet.service_a, [_pair(fleet.gus, fleet.truck)], auth=OUTSIDER_AUTH)
    customer = _put(call, fleet.service_a, [_pair(fleet.gus, fleet.truck)], auth=CUSTOMER_AUTH)

    assert outsider.status_code == 404
    assert customer.status_code == 403


def test_foreign_driver_or_vehicle_is_422(call, fleet: Fleet):
    foreign_driver = _put(call, fleet.service_a, [_pair(fleet.outsider_driver, fleet.truck)])
    foreign_vehicle = _put(call, fleet.service_a, [_pair(fleet.gus, fleet.outsider_van)])
    other_profile_vehicle = _put(call, fleet.service_a, [_pair(fleet.gus, fleet.solo_van)])
    company_driver_on_solo = call("PUT", _assignments_url(fleet.solo_service), as_auth_id=INDEPENDENT_AUTH,
                                  json={"assignments": [_pair(fleet.eli, fleet.solo_van)]})

    assert foreign_driver.status_code == 422
    assert foreign_vehicle.status_code == 422
    assert other_profile_vehicle.status_code == 422
    assert company_driver_on_solo.status_code == 422


@pytest.mark.parametrize("pairs_case", ["empty", "duplicate_driver", "duplicate_vehicle"])
def test_empty_or_duplicate_pairs_are_422(call, fleet: Fleet, pairs_case):
    pairs = {
        "empty": [],
        "duplicate_driver": [_pair(fleet.gus, fleet.van), _pair(fleet.gus, fleet.truck)],
        "duplicate_vehicle": [_pair(fleet.gus, fleet.truck), _pair(fleet.eli, fleet.truck)],
    }[pairs_case]

    assert _put(call, fleet.service_a, pairs).status_code == 422


def test_assignment_needs_a_confirmed_service(call, db, fleet: Fleet):
    fleet.service_a.status = "in_progress"
    db.commit()

    response = _put(call, fleet.service_a, [_pair(fleet.gus, fleet.truck)])

    assert response.status_code == 409
    assert response.json()["detail"] == "Only confirmed services can be assigned."


def test_same_day_conflict_is_409_with_the_conflicts_and_writes_nothing(call, db, fleet: Fleet):
    response = _put(call, fleet.service_a, [_pair(fleet.eli, fleet.truck)])

    assert response.status_code == 409
    body = response.json()
    assert body["detail"] == "Some drivers already have a service on the same day."
    assert body["conflicts"] == [{
        "driverId": str(fleet.eli.id),
        "serviceId": str(fleet.service_same_day.id),
        "serviceAt": body["conflicts"][0]["serviceAt"],
    }]
    assert body["conflicts"][0]["serviceAt"].startswith("2026-10-21T01:00:00")
    assert [row.driver_id for row in _assignment_rows(db, fleet.service_a)] == [fleet.eli.id]


def test_confirmed_same_day_conflict_is_saved(call, fleet: Fleet):
    response = _put(call, fleet.service_a, [_pair(fleet.eli, fleet.truck)], confirmSameDayConflicts=True)

    assert response.status_code == 200
    assert response.json()["assignments"][0]["vehicleId"] == str(fleet.truck.id)


def test_a_different_santiago_day_is_not_a_conflict(call, fleet: Fleet):
    response = _put(call, fleet.service_next_day, [_pair(fleet.eli, fleet.truck)])

    assert response.status_code == 200


def test_a_finished_service_on_the_same_day_is_not_a_conflict(call, db, fleet: Fleet):
    fleet.service_same_day.status = "completed"
    db.commit()

    response = _put(call, fleet.service_a, [_pair(fleet.eli, fleet.truck)])

    assert response.status_code == 200


# --- T6: POST /start --------------------------------------------------------------------------------------------------


LOCATION = {"latitude": -33.4489, "longitude": -70.6693, "accuracy": 12.5}
MOVED = {"latitude": -33.5, "longitude": -70.7, "accuracy": 8}


def _start(call, service: Servicio, *, auth, json=LOCATION):
    return call("POST", _start_url(service), as_auth_id=auth, json=json)


def _location_url(service: Servicio) -> str:
    return f"/api/provider/services/{service.id}/location"


def _customer_location_url(service: Servicio) -> str:
    return f"/api/customer/services/{service.id}/location"


def _complete_url(service: Servicio) -> str:
    return f"/api/provider/services/{service.id}/complete"


def _location_rows(db: Session, service: Servicio) -> list[ServicioUbicacion]:
    db.expire_all()
    return list(db.execute(select(ServicioUbicacion).where(ServicioUbicacion.service_id == service.id)).scalars())


class _PhotoStorage:
    def __init__(self) -> None:
        self.uploads: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        self.uploads[key] = (content, content_type)

    def delete(self, key: str) -> None:
        self.deleted.append(key)


@pytest.fixture
def photo_storage():
    storage = _PhotoStorage()
    app.dependency_overrides[get_evidence_storage_resolver] = lambda: (lambda: storage)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    yield storage
    app.dependency_overrides.pop(get_evidence_storage_resolver, None)
    app.dependency_overrides.pop(get_settings, None)


def _authenticate(auth_id: UUID) -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=auth_id,
        email="caller@example.test",
        session_id=uuid4(),
        assurance="aal2",
        authentication_methods=frozenset({"password", "phone"}),
    )


# --- T6: POST /start and the live location (S1) -----------------------------------------------------------------------


def test_assigned_driver_starts_the_service_and_is_recorded(call, db, fleet: Fleet):
    response = _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["startedAt"] is not None
    db.refresh(fleet.service_a)
    assert fleet.service_a.started_by_user_id == fleet.eli_user.id
    assert fleet.service_a.starts_at is not None


def test_owner_starts_the_service_and_is_recorded(call, db, fleet: Fleet):
    response = _start(call, fleet.service_a, auth=OWNER_AUTH)

    assert response.status_code == 200
    db.refresh(fleet.service_a)
    assert fleet.service_a.started_by_user_id == fleet.owner.id


def test_start_needs_at_least_one_assignment(call, db, fleet: Fleet):
    response = _start(call, fleet.service_next_day, auth=OWNER_AUTH)

    assert response.status_code == 409
    assert response.json()["detail"] == "Assign at least one driver and vehicle before starting."
    db.refresh(fleet.service_next_day)
    assert fleet.service_next_day.status == "confirmed"
    assert _location_rows(db, fleet.service_next_day) == []


def test_starting_twice_is_409(call, fleet: Fleet):
    assert _start(call, fleet.service_a, auth=OWNER_AUTH).status_code == 200

    response = _start(call, fleet.service_a, auth=OWNER_AUTH)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only confirmed services can be started."


def test_unassigned_employed_driver_cannot_see_or_start_the_service(call, fleet: Fleet):
    response = _start(call, fleet.service_a, auth=GUS_AUTH)

    assert response.status_code == 404


def test_customer_cannot_start_a_service(call, fleet: Fleet):
    response = _start(call, fleet.service_a, auth=CUSTOMER_AUTH)

    assert response.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"latitude": -33.4}],
    ids=["no-body", "empty-body", "missing-longitude"],
)
def test_start_without_coordinates_is_422_and_the_service_stays_confirmed(call, db, fleet: Fleet, payload):
    response = _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH, json=payload)

    assert response.status_code == 422
    db.refresh(fleet.service_a)
    assert fleet.service_a.status == "confirmed"
    assert fleet.service_a.starts_at is None
    assert _location_rows(db, fleet.service_a) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"latitude": 91, "longitude": -70.6},
        {"latitude": -90.5, "longitude": -70.6},
        {"latitude": -33.4, "longitude": 181},
        {"latitude": -33.4, "longitude": -180.01},
        {"latitude": -33.4, "longitude": -70.6, "accuracy": -1},
        {"latitude": -33.4, "longitude": -70.6, "accuracy": 100001},
        {"latitude": "north", "longitude": -70.6},
    ],
    ids=["latitude-high", "latitude-low", "longitude-high", "longitude-low",
         "accuracy-negative", "accuracy-too-large", "latitude-not-a-number"],
)
def test_invalid_coordinates_are_422_and_nothing_is_written(call, db, fleet: Fleet, payload):
    response = _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH, json=payload)

    assert response.status_code == 422
    db.refresh(fleet.service_a)
    assert fleet.service_a.status == "confirmed"
    assert _location_rows(db, fleet.service_a) == []


def test_start_with_coordinates_stores_the_location_in_the_same_transaction(call, db, fleet: Fleet):
    response = _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH)

    assert response.status_code == 200
    rows = _location_rows(db, fleet.service_a)
    assert len(rows) == 1
    assert float(rows[0].latitude) == pytest.approx(-33.4489)
    assert float(rows[0].longitude) == pytest.approx(-70.6693)
    assert float(rows[0].accuracy_meters) == pytest.approx(12.5)
    assert rows[0].updated_at is not None


def test_start_without_accuracy_stores_a_null_accuracy(call, db, fleet: Fleet):
    response = _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH, json={"latitude": -33.4, "longitude": -70.6})

    assert response.status_code == 200
    rows = _location_rows(db, fleet.service_a)
    assert len(rows) == 1 and rows[0].accuracy_meters is None


def test_existing_start_rule_still_requires_an_assignment_with_coordinates(call, db, fleet: Fleet):
    response = _start(call, fleet.service_next_day, auth=EMPLOYED_DRIVER_AUTH)

    assert response.status_code == 404
    db.refresh(fleet.service_next_day)
    assert fleet.service_next_day.status == "confirmed"
    assert _location_rows(db, fleet.service_next_day) == []


# --- PUT /location ----------------------------------------------------------------------------------------------------


def test_assigned_driver_updates_the_position_and_keeps_one_row(call, db, fleet: Fleet):
    assert _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH).status_code == 200

    response = call("PUT", _location_url(fleet.service_a), as_auth_id=EMPLOYED_DRIVER_AUTH, json=MOVED)

    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] == -33.5 and body["longitude"] == -70.7 and body["accuracy"] == 8
    assert body["updatedAt"] is not None
    rows = _location_rows(db, fleet.service_a)
    assert len(rows) == 1
    assert float(rows[0].latitude) == pytest.approx(-33.5)


@pytest.mark.parametrize(
    ("auth", "expected"),
    [(GUS_AUTH, 404), (OWNER_AUTH, 403), (OUTSIDER_AUTH, 404), (CUSTOMER_AUTH, 403)],
    ids=["unassigned-employed-driver", "owner-not-assigned", "owner-of-another-profile", "customer"],
)
def test_only_the_assigned_driver_can_update_the_position(call, db, fleet: Fleet, auth, expected):
    assert _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH).status_code == 200

    response = call("PUT", _location_url(fleet.service_a), as_auth_id=auth, json=MOVED)

    assert response.status_code == expected
    rows = _location_rows(db, fleet.service_a)
    assert len(rows) == 1 and float(rows[0].latitude) == pytest.approx(-33.4489)


def test_update_is_refused_when_the_service_is_not_in_progress(call, db, fleet: Fleet):
    response = call("PUT", _location_url(fleet.service_a), as_auth_id=EMPLOYED_DRIVER_AUTH, json=MOVED)

    assert response.status_code == 409
    assert _location_rows(db, fleet.service_a) == []


def test_update_with_invalid_coordinates_is_422(call, db, fleet: Fleet):
    assert _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH).status_code == 200

    response = call(
        "PUT", _location_url(fleet.service_a), as_auth_id=EMPLOYED_DRIVER_AUTH,
        json={"latitude": 95, "longitude": -70.7},
    )

    assert response.status_code == 422
    rows = _location_rows(db, fleet.service_a)
    assert len(rows) == 1 and float(rows[0].latitude) == pytest.approx(-33.4489)


# --- GET /location: provider and customer reads -----------------------------------------------------------------------


def test_owner_and_assigned_driver_read_the_position_while_in_progress(call, db, fleet: Fleet):
    assert _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH).status_code == 200

    for auth in (OWNER_AUTH, EMPLOYED_DRIVER_AUTH):
        response = call("GET", _location_url(fleet.service_a), as_auth_id=auth)

        assert response.status_code == 200
        body = response.json()
        assert body["latitude"] == -33.4489 and body["longitude"] == -70.6693 and body["accuracy"] == 12.5
        assert body["updatedAt"] is not None


def test_provider_location_read_is_404_before_start_and_for_viewers_who_cannot_see_the_service(call, fleet: Fleet):
    assert call("GET", _location_url(fleet.service_a), as_auth_id=EMPLOYED_DRIVER_AUTH).status_code == 404

    assert _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH).status_code == 200

    assert call("GET", _location_url(fleet.service_a), as_auth_id=GUS_AUTH).status_code == 404
    assert call("GET", _location_url(fleet.service_a), as_auth_id=OUTSIDER_AUTH).status_code == 404
    assert call("GET", _location_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH).status_code == 403


def test_customer_owner_reads_the_position_and_another_customer_gets_404(call, db, fleet: Fleet):
    assert _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH).status_code == 200
    client_role = db.execute(select(RolUsuario).where(RolUsuario.code == "client")).scalar_one()
    other = Usuario(id=uuid4(), auth_user_id=OTHER_CUSTOMER_AUTH, first_name="Otra", last_name="Clienta",
                    email="otra@example.test", role_id=client_role.id)
    db.add(other)
    db.commit()

    owner_read = call("GET", _customer_location_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH)
    other_read = call("GET", _customer_location_url(fleet.service_a), as_auth_id=OTHER_CUSTOMER_AUTH)

    assert owner_read.status_code == 200
    assert owner_read.json()["latitude"] == -33.4489
    assert other_read.status_code == 404


def test_customer_location_read_is_404_before_start(call, fleet: Fleet):
    response = call("GET", _customer_location_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 404


# --- POST /complete: the location is deleted ---------------------------------------------------------------------------


def test_completion_deletes_the_position_and_later_updates_and_reads_fail(call, db, fleet: Fleet, photo_storage):
    assert _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH).status_code == 200
    assert len(_location_rows(db, fleet.service_a)) == 1
    _authenticate(EMPLOYED_DRIVER_AUTH)

    completed = TestClient(app).post(
        _complete_url(fleet.service_a), files={"photo": ("evidence.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 64, "image/jpeg")}
    )

    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert _location_rows(db, fleet.service_a) == []
    assert call("PUT", _location_url(fleet.service_a), as_auth_id=EMPLOYED_DRIVER_AUTH, json=MOVED).status_code == 409
    assert call("GET", _location_url(fleet.service_a), as_auth_id=OWNER_AUTH).status_code == 404
    assert call("GET", _customer_location_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH).status_code == 404


def test_existing_completion_rules_still_need_an_assigned_driver_and_a_photo(call, db, fleet: Fleet, photo_storage):
    assert _start(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH).status_code == 200
    _authenticate(EMPLOYED_DRIVER_AUTH)

    without_photo = TestClient(app).post(_complete_url(fleet.service_a))

    assert without_photo.status_code == 422
    db.refresh(fleet.service_a)
    assert fleet.service_a.status == "in_progress"
    assert len(_location_rows(db, fleet.service_a)) == 1
    _authenticate(OWNER_AUTH)
    not_assigned = TestClient(app).post(
        _complete_url(fleet.service_a), files={"photo": ("evidence.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 64, "image/jpeg")}
    )
    assert not_assigned.status_code == 403


def test_requested_drivers_are_locked_in_id_order_before_the_same_day_check(call, db, fleet: Fleet):
    """SQLite ignores FOR UPDATE, so the statements are captured and compiled for PostgreSQL instead."""
    executed: list[str] = []

    def record(orm_execute_state) -> None:
        executed.append(str(orm_execute_state.statement.compile(dialect=postgresql.dialect())))

    event.listen(db, "do_orm_execute", record)
    try:
        response = _put(call, fleet.service_next_day, [_pair(fleet.eli, fleet.van)])
    finally:
        event.remove(db, "do_orm_execute", record)

    assert response.status_code == 200
    lock = next(sql for sql in executed if sql.startswith('SELECT "Conductor"."ID"') and "FOR UPDATE" in sql)
    conflict = next(sql for sql in executed if sql.startswith('SELECT "Servicio_Asignacion"."ID_Conductor"'))
    assert "ORDER BY" in lock and '"Conductor"."ID"' in lock.split("ORDER BY", 1)[1]
    assert executed.index(lock) < executed.index(conflict)
