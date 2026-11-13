"""Shared trips: a provider publishes a paid, shareable service as a trip, closes it, lists it and receives joins.

Publishing needs a vehicle and a driver of the caller's own provider profile, because the schema links every service
on a trip to a trip vehicle with its driver. Another provider's vehicle or driver answers 404, like any resource the
caller cannot see. A customer account gets 403 on provider routes, as the other provider routes do.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import (
    Base,
    Chat,
    Commune,
    Conductor,
    Cotizacion,
    FormularioServicio,
    Perfil,
    ParadaViaje,
    RolPerfil,
    RolUsuario,
    Servicio,
    ServicioDisponible,
    TipoConductor,
    TipoServicio,
    Usuario,
    Vehiculo,
    Viaje,
    ViajeVehiculo,
)
from chat_support import _register_btrim
from driver_verification_support import unverify_driver, verify_driver

CUSTOMER_AUTH = UUID("7c2e0a10-0000-4000-8000-000000000001")
OTHER_CUSTOMER_AUTH = UUID("7c2e0a10-0000-4000-8000-000000000002")
OWNER_AUTH = UUID("7c2e0a10-0000-4000-8000-000000000003")
OTHER_OWNER_AUTH = UUID("7c2e0a10-0000-4000-8000-000000000004")
EMPLOYED_DRIVER_AUTH = UUID("7c2e0a10-0000-4000-8000-000000000005")
OTHER_EMPLOYED_DRIVER_AUTH = UUID("7c2e0a10-0000-4000-8000-000000000006")
INDEPENDENT_AUTH = UUID("7c2e0a10-0000-4000-8000-000000000007")

# Comunas and Tipos_Servicio carry PostgreSQL regex checks, so they are created raw, as in the other SQLite fixtures.
TABLES = (
    "Rol_Usuario", "Rol_Perfil", "Usuario", "Perfil", "Tipo_Conductor", "Conductor", "Vehiculo",
    "Servicios_Disponibles", "Formulario_servicio", "Chat", "Cotizacion",
    "Servicio", "Servicio_Asignacion", "Viaje", "Viaje_Vehiculo", "Parada_Viaje", "Verificacion_Identidad",
)
JOIN_REQUEST_DATE = "2030-10-20T09:00:00-03:00"


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _register_btrim)
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in TABLES])
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE "Comunas" ("Codigo" VARCHAR(5) PRIMARY KEY, "Codigo_Region" VARCHAR(2) NOT NULL, "Nombre" VARCHAR(120) NOT NULL)'
        ))
        connection.execute(text(
            'CREATE TABLE "Tipos_Servicio" ("ID" CHAR(32) PRIMARY KEY, "Nombre_servicio" VARCHAR(120) NOT NULL, "Slug" VARCHAR(120) NOT NULL)'
        ))
        connection.execute(text(
            'CREATE TABLE "Regiones" ("Codigo" VARCHAR(2) PRIMARY KEY, "Nombre" VARCHAR(120) NOT NULL, "Orden" SMALLINT NOT NULL)'
        ))
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def api(db):
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app)

    def call(method: str, path: str, *, as_auth_id: UUID, json=None):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=as_auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
        return client.request(method, path, json=json)

    yield call
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@dataclass
class Scenario:
    customer: Usuario
    other_customer: Usuario
    company: Perfil
    other_company: Perfil
    solo: Perfil
    vehicle: Vehiculo
    other_vehicle: Vehiculo
    driver: Conductor
    other_driver: Conductor
    solo_driver: Conductor
    service_type: TipoServicio
    shareable: Servicio  # paid, company profile, customer accepted sharing, dated
    exclusive: Servicio  # paid, customer refused sharing
    undated: Servicio  # paid, shareable, no requested date


def _user(db: Session, *, auth_id: UUID, first: str, role_code: str, roles: dict) -> Usuario:
    row = Usuario(
        id=uuid4(), auth_user_id=auth_id, first_name=first, last_name="Test", email=f"{first.lower()}@example.test",
        role_id=roles[role_code].id,
    )
    db.add(row)
    return row


def _paid_service(db: Session, *, profile: Perfil, customer: Usuario, service_type: TipoServicio,
                  is_exclusive: bool, requested_at: datetime | None) -> Servicio:
    created = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    form = FormularioServicio(
        id=uuid4(), profile_id=profile.id, service_type_id=service_type.id, status="accepted",
        customer_id=customer.id, origin="Av. Origen 100", destination="Calle Destino 200",
        origin_commune_code="13101", destination_commune_code="05101", is_exclusive=is_exclusive,
        requested_at=requested_at, created_at=created,
    )
    chat = Chat(id=uuid4(), form_id=form.id, created_at=created)
    quote = Cotizacion(
        id=uuid4(), chat_id=chat.id, status="paid", amount=Decimal("150000"), origin=form.origin,
        destination=form.destination, service_type_id=service_type.id, service_at=requested_at, created_at=created,
        currency="CLP",
    )
    service = Servicio(
        id=uuid4(), profile_id=profile.id, customer_id=customer.id, status="confirmed",
        is_exclusive=is_exclusive, service_at=requested_at, created_at=created, amount=Decimal("150000"),
        form_id=form.id, accepted_quotation_id=quote.id,
    )
    db.add_all([form, chat, quote, service])
    db.flush()
    return service


def _trip(db: Session, *, profile: Perfil, vehicle: Vehiculo, driver: Conductor, accepts: bool = True,
          published: bool = True, departure: datetime | None = None) -> Viaje:
    trip = Viaje(
        id=uuid4(), profile_id=profile.id, origin="Av. Origen 100", destination="Calle Destino 200",
        origin_commune_code="13101", destination_commune_code="05101", status="scheduled",
        departure_at=departure or datetime(2030, 10, 20, 9, tzinfo=timezone.utc),
        is_published=published, accepts_requests=accepts,
    )
    db.add(trip)
    db.flush()
    db.add(ViajeVehiculo(trip_id=trip.id, vehicle_id=vehicle.id, driver_id=driver.id))
    db.add_all([
        ParadaViaje(id=uuid4(), trip_id=trip.id, order=1, address="Av. Origen 100"),
        ParadaViaje(id=uuid4(), trip_id=trip.id, order=2, address="Calle Destino 200"),
    ])
    db.flush()
    return trip


@pytest.fixture
def scenario(db: Session) -> Scenario:
    roles_usuario = {code: RolUsuario(id=uuid4(), name=code, code=code)
                     for code in ("client", "company_owner", "company_driver", "independent_driver")}
    roles_perfil = {code: RolPerfil(id=uuid4(), name=code, code=code) for code in ("company", "independent_driver")}
    db.add_all([*roles_usuario.values(), *roles_perfil.values(), TipoConductor(id=uuid4(), name="Liviano")])
    db.flush()
    driver_type = db.query(TipoConductor).one()

    customer = _user(db, auth_id=CUSTOMER_AUTH, first="Casey", role_code="client", roles=roles_usuario)
    other_customer = _user(db, auth_id=OTHER_CUSTOMER_AUTH, first="Xavi", role_code="client", roles=roles_usuario)
    owner = _user(db, auth_id=OWNER_AUTH, first="Pat", role_code="company_owner", roles=roles_usuario)
    other_owner = _user(db, auth_id=OTHER_OWNER_AUTH, first="Ola", role_code="company_owner", roles=roles_usuario)
    employee = _user(db, auth_id=EMPLOYED_DRIVER_AUTH, first="Eli", role_code="company_driver", roles=roles_usuario)
    other_employee = _user(db, auth_id=OTHER_EMPLOYED_DRIVER_AUTH, first="Ivo", role_code="company_driver",
                           roles=roles_usuario)
    independent = _user(db, auth_id=INDEPENDENT_AUTH, first="Dana", role_code="independent_driver", roles=roles_usuario)
    db.flush()

    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    company = Perfil(id=uuid4(), owner_user_id=owner.id, name="Transportes Norte", kind="company",
                     role_id=roles_perfil["company"].id, public_activated_at=now)
    other_company = Perfil(id=uuid4(), owner_user_id=other_owner.id, name="Otra Empresa", kind="company",
                           role_id=roles_perfil["company"].id, public_activated_at=now)
    solo = Perfil(id=uuid4(), owner_user_id=independent.id, name="Dana Fletes", kind="independent_driver",
                  role_id=roles_perfil["independent_driver"].id, public_activated_at=now)
    db.add_all([company, other_company, solo])
    db.flush()

    driver = Conductor(id=uuid4(), user_id=employee.id, employer_profile_id=company.id,
                       driver_type_id=driver_type.id, registered_at=now)
    other_driver = Conductor(id=uuid4(), user_id=other_employee.id, employer_profile_id=other_company.id,
                             driver_type_id=driver_type.id, registered_at=now)
    solo_driver = Conductor(id=uuid4(), user_id=independent.id, employer_profile_id=None,
                            driver_type_id=driver_type.id, registered_at=now)
    vehicle = Vehiculo(id=uuid4(), profile_id=company.id, plate="AB1234", brand="Ford", model="Transit",
                       image_storage_key="vehicles/1.jpg")
    other_vehicle = Vehiculo(id=uuid4(), profile_id=other_company.id, plate="CD5678", brand="Iveco", model="Daily",
                             image_storage_key="vehicles/2.jpg")
    service_type = TipoServicio(id=uuid4(), name="Mudanzas", slug="mudanzas")
    for verified_user in (employee, other_employee, independent):
        verify_driver(db, verified_user.id)
    db.add_all([driver, other_driver, solo_driver, vehicle, other_vehicle, service_type,
                Commune(code="13101", region_code="13", name="Santiago"),
                Commune(code="05101", region_code="05", name="Valparaíso")])
    db.add_all([
        ServicioDisponible(id=uuid4(), profile_id=company.id, service_type_id=service_type.id),
        ServicioDisponible(id=uuid4(), profile_id=other_company.id, service_type_id=service_type.id),
    ])
    db.flush()

    requested = datetime(2030, 10, 20, 9, tzinfo=timezone.utc)
    shareable = _paid_service(db, profile=company, customer=customer, service_type=service_type,
                              is_exclusive=False, requested_at=requested)
    exclusive = _paid_service(db, profile=company, customer=other_customer, service_type=service_type,
                              is_exclusive=True, requested_at=requested)
    undated = _paid_service(db, profile=company, customer=customer, service_type=service_type,
                            is_exclusive=False, requested_at=None)
    db.commit()
    return Scenario(customer, other_customer, company, other_company, solo, vehicle, other_vehicle, driver,
                    other_driver, solo_driver, service_type, shareable, exclusive, undated)


def _publish_body(scenario: Scenario, *, vehicle=None, driver=None) -> dict:
    return {
        "vehicleId": str((vehicle or scenario.vehicle).id),
        "driverId": str((driver or scenario.driver).id),
    }


# Publish

def test_owner_publishes_a_shareable_paid_service_as_a_trip(api, scenario: Scenario, db: Session):
    response = api(
        "POST", f"/api/provider/services/{scenario.shareable.id}/shared-trip",
        as_auth_id=OWNER_AUTH, json=_publish_body(scenario),
    )

    assert response.status_code == 201, response.text
    trip = db.query(Viaje).one()
    assert response.json()["tripId"] == str(trip.id)
    assert trip.profile_id == scenario.company.id
    assert (trip.origin, trip.destination) == ("Av. Origen 100", "Calle Destino 200")
    assert (trip.origin_commune_code, trip.destination_commune_code) == ("13101", "05101")
    assert trip.departure_at.replace(tzinfo=timezone.utc) == datetime(2030, 10, 20, 9, tzinfo=timezone.utc)
    assert trip.is_published is True and trip.accepts_requests is True

    assignment = db.query(ViajeVehiculo).one()
    assert (assignment.trip_id, assignment.vehicle_id, assignment.driver_id) == (
        trip.id, scenario.vehicle.id, scenario.driver.id,
    )

    stops = db.query(ParadaViaje).filter(ParadaViaje.trip_id == trip.id).order_by(ParadaViaje.order).all()
    assert [(stop.order, stop.address) for stop in stops] == [(1, "Av. Origen 100"), (2, "Calle Destino 200")]

    db.refresh(scenario.shareable)
    assert scenario.shareable.trip_id == trip.id
    assert scenario.shareable.vehicle_id == scenario.vehicle.id
    assert scenario.shareable.pickup_stop_id == stops[0].id
    assert scenario.shareable.delivery_stop_id == stops[1].id


def test_publish_refused_for_an_exclusive_service(api, scenario: Scenario, db: Session):
    response = api(
        "POST", f"/api/provider/services/{scenario.exclusive.id}/shared-trip",
        as_auth_id=OWNER_AUTH, json=_publish_body(scenario),
    )

    assert response.status_code == 409, response.text
    assert db.query(Viaje).count() == 0
    db.refresh(scenario.exclusive)
    assert scenario.exclusive.trip_id is None


def test_publish_refused_when_the_service_already_has_a_trip(api, scenario: Scenario, db: Session):
    first = api("POST", f"/api/provider/services/{scenario.shareable.id}/shared-trip",
                as_auth_id=OWNER_AUTH, json=_publish_body(scenario))
    second = api("POST", f"/api/provider/services/{scenario.shareable.id}/shared-trip",
                 as_auth_id=OWNER_AUTH, json=_publish_body(scenario))

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert db.query(Viaje).count() == 1


def test_publish_refused_for_a_service_without_a_date(api, scenario: Scenario, db: Session):
    response = api(
        "POST", f"/api/provider/services/{scenario.undated.id}/shared-trip",
        as_auth_id=OWNER_AUTH, json=_publish_body(scenario),
    )

    assert response.status_code == 409, response.text
    assert db.query(Viaje).count() == 0


def test_another_provider_gets_404_when_publishing(api, scenario: Scenario, db: Session):
    response = api(
        "POST", f"/api/provider/services/{scenario.shareable.id}/shared-trip",
        as_auth_id=OTHER_OWNER_AUTH, json={"vehicleId": str(scenario.other_vehicle.id),
                                           "driverId": str(scenario.other_driver.id)},
    )

    assert response.status_code == 404, response.text
    assert db.query(Viaje).count() == 0


def test_customer_gets_403_when_publishing(api, scenario: Scenario, db: Session):
    response = api(
        "POST", f"/api/provider/services/{scenario.shareable.id}/shared-trip",
        as_auth_id=CUSTOMER_AUTH, json=_publish_body(scenario),
    )

    assert response.status_code == 403, response.text
    assert db.query(Viaje).count() == 0


def test_publish_refused_for_a_vehicle_of_another_provider(api, scenario: Scenario, db: Session):
    response = api(
        "POST", f"/api/provider/services/{scenario.shareable.id}/shared-trip",
        as_auth_id=OWNER_AUTH, json=_publish_body(scenario, vehicle=scenario.other_vehicle),
    )

    assert response.status_code == 404, response.text
    assert db.query(Viaje).count() == 0


def test_publish_refused_for_a_driver_of_another_provider(api, scenario: Scenario, db: Session):
    response = api(
        "POST", f"/api/provider/services/{scenario.shareable.id}/shared-trip",
        as_auth_id=OWNER_AUTH, json=_publish_body(scenario, driver=scenario.other_driver),
    )

    assert response.status_code == 404, response.text
    assert db.query(Viaje).count() == 0


def test_independent_driver_publishes_with_their_own_driver_record(api, scenario: Scenario, db: Session):
    service = _paid_service(db, profile=scenario.solo, customer=scenario.customer, service_type=scenario.service_type,
                            is_exclusive=False, requested_at=datetime(2030, 10, 21, 9, tzinfo=timezone.utc))
    solo_vehicle = Vehiculo(id=uuid4(), profile_id=scenario.solo.id, plate="EF9012", brand="Kia", model="K2",
                            image_storage_key="vehicles/3.jpg")
    db.add(solo_vehicle)
    db.commit()

    response = api(
        "POST", f"/api/provider/services/{service.id}/shared-trip",
        as_auth_id=INDEPENDENT_AUTH,
        json={"vehicleId": str(solo_vehicle.id), "driverId": str(scenario.solo_driver.id)},
    )

    assert response.status_code == 201, response.text
    assert db.query(ViajeVehiculo).one().driver_id == scenario.solo_driver.id


def test_company_cannot_use_another_companys_driver_even_through_its_own_vehicle(api, scenario: Scenario, db: Session):
    response = api(
        "POST", f"/api/provider/services/{scenario.shareable.id}/shared-trip",
        as_auth_id=OWNER_AUTH, json=_publish_body(scenario, driver=scenario.solo_driver),
    )

    assert response.status_code == 404, response.text
    assert db.query(Viaje).count() == 0


# Close

def test_owner_closes_the_trip_and_its_services_stay_linked(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver)
    db.commit()

    response = api("POST", f"/api/provider/shared-trips/{trip.id}/close", as_auth_id=OWNER_AUTH)

    assert response.status_code == 200, response.text
    assert response.json() == {"tripId": str(trip.id), "acceptsRequests": False}
    db.refresh(trip)
    assert trip.accepts_requests is False
    assert trip.is_published is True


def test_another_provider_gets_404_when_closing(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver)
    db.commit()

    response = api("POST", f"/api/provider/shared-trips/{trip.id}/close", as_auth_id=OTHER_OWNER_AUTH)

    assert response.status_code == 404, response.text
    db.refresh(trip)
    assert trip.accepts_requests is True


# Provider list and drivers

def test_provider_lists_only_its_trips_with_the_joined_count(api, scenario: Scenario, db: Session):
    mine = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver,
                 accepts=False)
    _trip(db, profile=scenario.other_company, vehicle=scenario.other_vehicle, driver=scenario.other_driver)
    origin_stop, destination_stop = db.query(ParadaViaje).filter(ParadaViaje.trip_id == mine.id).order_by(
        ParadaViaje.order).all()
    for service in (scenario.shareable, _paid_service(db, profile=scenario.company, customer=scenario.other_customer,
                                                      service_type=scenario.service_type, is_exclusive=False,
                                                      requested_at=datetime(2030, 10, 20, 9, tzinfo=timezone.utc))):
        service.trip_id = mine.id
        service.vehicle_id = scenario.vehicle.id
        service.pickup_stop_id = origin_stop.id
        service.delivery_stop_id = destination_stop.id
    db.commit()

    response = api("GET", "/api/provider/shared-trips", as_auth_id=OWNER_AUTH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"] == [{
        "tripId": str(mine.id),
        "status": "closed",
        "origin": "Av. Origen 100",
        "destination": "Calle Destino 200",
        "departureAt": body["items"][0]["departureAt"],
        "joinedServices": 2,
    }]


def test_provider_drivers_list_is_limited_to_its_own_drivers(api, scenario: Scenario):
    response = api("GET", "/api/provider/drivers", as_auth_id=OWNER_AUTH)

    assert response.status_code == 200, response.text
    assert response.json()["items"] == [{
        "driverId": str(scenario.driver.id),
        "name": "Eli Test",
        "verified": True,
    }]


# Join

def _join_body(scenario: Scenario, trip: Viaje, **overrides) -> dict:
    body = {
        "profileId": str(scenario.company.id),
        "serviceTypeId": str(scenario.service_type.id),
        "originCommuneCode": "13101",
        "destinationCommuneCode": "05101",
        "origin": "Calle Retiro 5",
        "destination": "Calle Entrega 9",
        "requestedAt": JOIN_REQUEST_DATE,
        "acceptsSharing": True,
        "requestedTripId": str(trip.id),
    }
    body.update(overrides)
    return body


def test_join_accepted_for_an_open_trip(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver)
    db.commit()

    response = api("POST", "/api/service-requests", as_auth_id=CUSTOMER_AUTH, json=_join_body(scenario, trip))

    assert response.status_code == 201, response.text
    form = db.query(FormularioServicio).filter(FormularioServicio.origin == "Calle Retiro 5").one()
    assert form.requested_trip_id == trip.id
    assert form.profile_id == scenario.company.id


def test_join_refused_for_a_closed_trip(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver, accepts=False)
    db.commit()

    response = api("POST", "/api/service-requests", as_auth_id=CUSTOMER_AUTH, json=_join_body(scenario, trip))

    assert response.status_code == 409, response.text
    assert db.query(FormularioServicio).filter(FormularioServicio.origin == "Calle Retiro 5").count() == 0


def test_join_refused_for_an_unpublished_trip(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver, published=False)
    db.commit()

    response = api("POST", "/api/service-requests", as_auth_id=CUSTOMER_AUTH, json=_join_body(scenario, trip))

    assert response.status_code == 409, response.text
    assert db.query(FormularioServicio).filter(FormularioServicio.origin == "Calle Retiro 5").count() == 0


def test_join_refused_for_a_trip_of_another_provider(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.other_company, vehicle=scenario.other_vehicle, driver=scenario.other_driver)
    db.commit()

    response = api("POST", "/api/service-requests", as_auth_id=CUSTOMER_AUTH, json=_join_body(scenario, trip))

    assert response.status_code == 404, response.text
    assert db.query(FormularioServicio).filter(FormularioServicio.origin == "Calle Retiro 5").count() == 0


def test_join_refused_when_the_customer_does_not_accept_sharing(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver)
    db.commit()

    response = api("POST", "/api/service-requests", as_auth_id=CUSTOMER_AUTH,
                   json=_join_body(scenario, trip, acceptsSharing=False))

    assert response.status_code == 422, response.text
    assert db.query(FormularioServicio).filter(FormularioServicio.origin == "Calle Retiro 5").count() == 0


def test_join_refused_when_the_sharing_choice_is_missing(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver)
    body = _join_body(scenario, trip)
    body.pop("acceptsSharing")
    db.commit()

    response = api("POST", "/api/service-requests", as_auth_id=CUSTOMER_AUTH, json=body)

    assert response.status_code == 422, response.text
    assert db.query(FormularioServicio).filter(FormularioServicio.origin == "Calle Retiro 5").count() == 0


def test_request_without_a_trip_is_stored_without_one(api, scenario: Scenario, db: Session):
    body = _join_body(scenario, _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver))
    body.pop("requestedTripId")
    db.commit()

    response = api("POST", "/api/service-requests", as_auth_id=CUSTOMER_AUTH, json=body)

    assert response.status_code == 201, response.text
    form = db.query(FormularioServicio).filter(FormularioServicio.origin == "Calle Retiro 5").one()
    assert form.requested_trip_id is None


def test_provider_inbox_shows_the_trip_of_a_join_request(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver)
    db.commit()
    created = api("POST", "/api/service-requests", as_auth_id=CUSTOMER_AUTH, json=_join_body(scenario, trip))
    assert created.status_code == 201, created.text

    response = api("GET", "/api/provider/requests", as_auth_id=OWNER_AUTH)

    assert response.status_code == 200, response.text
    item = next(row for row in response.json()["items"] if row["origin"] == "Calle Retiro 5")
    assert item["requestedTripId"] == str(trip.id)


# Public shared routes

def test_shared_routes_return_the_trip_id_and_its_date(api, scenario: Scenario, db: Session):
    trip = _trip(db, profile=scenario.company, vehicle=scenario.vehicle, driver=scenario.driver)
    db.commit()

    response = api("GET", "/api/shared-routes", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["tripId"] == str(trip.id)
    assert item["departureAt"].startswith("2030-10-20T09:00:00")


# Driver verification (odd/tasks/verificacion-conductores-verifik.md, S3)

def test_publish_refused_for_an_unverified_driver(api, scenario: Scenario, db: Session):
    unverify_driver(db, scenario.driver.user_id)

    response = api(
        "POST", f"/api/provider/services/{scenario.shareable.id}/shared-trip",
        as_auth_id=OWNER_AUTH, json=_publish_body(scenario),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "El conductor debe tener sus certificados verificados para publicar el viaje."
    assert db.query(Viaje).count() == 0


def test_provider_drivers_list_marks_unverified_drivers(api, scenario: Scenario, db: Session):
    unverify_driver(db, scenario.driver.user_id)

    response = api("GET", "/api/provider/drivers", as_auth_id=OWNER_AUTH)

    assert response.json()["items"] == [{"driverId": str(scenario.driver.id), "name": "Eli Test", "verified": False}]
