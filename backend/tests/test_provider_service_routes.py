"""Provider and customer service queries over an in-memory database.

Visibility rules: a profile owner sees every service of the profile; a company-employed driver sees only the
services they are assigned to; any other account gets 403 on provider routes. A service the viewer cannot see
answers 404, never 403.
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
    RolUsuario,
    Servicio,
    ServicioAsignacion,
    TipoServicio,
    Usuario,
    Vehiculo,
)
from chat_support import _register_btrim  # also registers the SQLite JSONB compiler

CUSTOMER_AUTH = UUID("5a0e0c3e-1b7a-4d0e-9a51-000000000001")
OTHER_CUSTOMER_AUTH = UUID("5a0e0c3e-1b7a-4d0e-9a51-000000000002")
OWNER_AUTH = UUID("5a0e0c3e-1b7a-4d0e-9a51-000000000003")
EMPLOYED_DRIVER_AUTH = UUID("5a0e0c3e-1b7a-4d0e-9a51-000000000004")
INDEPENDENT_AUTH = UUID("5a0e0c3e-1b7a-4d0e-9a51-000000000005")
UNKNOWN_AUTH = UUID("5a0e0c3e-1b7a-4d0e-9a51-000000000006")
SECRET_CONTACT_VALUES = ("+56911112222", "casey@example.test", "12345678-5", "pat@example.test", "+56933334444")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _register_btrim)
    tables = (
        "Rol_Usuario", "Usuario", "Perfil", "Conductor", "Vehiculo", "Formulario_servicio", "Chat",
        "Cotizacion", "Servicio", "Servicio_Asignacion",
    )
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in tables])
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE "Comunas" ("Codigo" VARCHAR(5) PRIMARY KEY, "Codigo_Region" VARCHAR(2) NOT NULL, "Nombre" VARCHAR(120) NOT NULL)'
        ))
        connection.execute(text(
            'CREATE TABLE "Tipos_Servicio" ("ID" CHAR(32) PRIMARY KEY, "Nombre_servicio" VARCHAR(120) NOT NULL, "Slug" VARCHAR(120) NOT NULL)'
        ))
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def api(db):
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app)

    def get(path: str, *, as_auth_id: UUID):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=as_auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
        return client.get(path)

    yield get
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@dataclass
class Scenario:
    company_assigned: Servicio  # company profile, customer, assigned to the employed driver
    company_unassigned: Servicio  # company profile, other customer, no assignment
    independent: Servicio  # independent driver profile, customer
    employed_driver: Conductor
    vehicle: Vehiculo
    company_profile: Perfil


@pytest.fixture
def scenario(db: Session) -> Scenario:
    roles = {code: RolUsuario(id=uuid4(), name=code, code=code)
             for code in ("client", "company_owner", "company_driver", "independent_driver")}
    db.add_all(roles.values())

    def user(auth_id, first, last, email, role, phone=None, rut=None):
        row = Usuario(id=uuid4(), auth_user_id=auth_id, first_name=first, last_name=last, email=email,
                      phone=phone, national_id=rut, role_id=roles[role].id)
        db.add(row)
        return row

    customer = user(CUSTOMER_AUTH, "Casey", "Customer", "casey@example.test", "client", "+56911112222", "12345678-5")
    other_customer = user(OTHER_CUSTOMER_AUTH, "Xavi", "Other", "xavi@example.test", "client")
    owner = user(OWNER_AUTH, "Pat", "Owner", "pat@example.test", "company_owner", "+56933334444")
    employee = user(EMPLOYED_DRIVER_AUTH, "Eli", "Employee", "eli@example.test", "company_driver")
    independent = user(INDEPENDENT_AUTH, "Dana", "Driver", "dana@example.test", "independent_driver")
    company = Perfil(id=uuid4(), owner_user_id=owner.id, name="Transportes Norte", kind="company", role_id=uuid4())
    solo = Perfil(id=uuid4(), owner_user_id=independent.id, name="Dana Fletes", kind="independent_driver", role_id=uuid4())
    db.add_all([company, solo])
    db.flush()
    employed_driver = Conductor(id=uuid4(), user_id=employee.id, employer_profile_id=company.id, driver_type_id=uuid4())
    independent_driver = Conductor(id=uuid4(), user_id=independent.id, employer_profile_id=None, driver_type_id=uuid4())
    vehicle = Vehiculo(id=uuid4(), profile_id=company.id, plate="ABCD12", brand="Hyundai", model="Porter",
                       image_storage_key="vehicles/abcd12.webp")
    mudanzas = TipoServicio(id=uuid4(), name="Mudanzas", slug="mudanzas")
    santiago = Commune(code="13101", region_code="13", name="Santiago")
    valparaiso = Commune(code="05101", region_code="05", name="Valparaíso")
    db.add_all([employed_driver, independent_driver, vehicle, mudanzas, santiago, valparaiso])
    db.flush()

    def service(profile, client, created_day):
        created = datetime(2026, 10, created_day, 10, tzinfo=timezone.utc)
        form = FormularioServicio(id=uuid4(), profile_id=profile.id, service_type_id=mudanzas.id, status="accepted",
                                  customer_id=client.id, origin_commune_code="13101",
                                  destination_commune_code="05101", created_at=created)
        chat = Chat(id=uuid4(), form_id=form.id, created_at=created)
        quote = Cotizacion(id=uuid4(), chat_id=chat.id, status="paid", amount=Decimal("150000"), origin="A",
                           destination="B", service_type_id=mudanzas.id, currency="CLP", created_at=created)
        row = Servicio(id=uuid4(), profile_id=profile.id, customer_id=client.id, status="confirmed",
                       service_at=datetime(2026, 10, 20, 9, tzinfo=timezone.utc), description="Mover un sofá",
                       created_at=created, amount=Decimal("150000"), form_id=form.id,
                       accepted_quotation_id=quote.id)
        db.add_all([form, chat, quote, row])
        db.flush()
        return row

    company_assigned = service(company, customer, 1)
    company_unassigned = service(company, other_customer, 2)
    solo_service = service(solo, customer, 3)
    db.add(ServicioAsignacion(id=uuid4(), service_id=company_assigned.id, driver_id=employed_driver.id,
                              vehicle_id=vehicle.id, assigned_by_user_id=owner.id))
    db.commit()
    return Scenario(company_assigned, company_unassigned, solo_service, employed_driver, vehicle, company)


def _ids(body) -> list[str]:
    return [item["serviceId"] for item in body["items"]]


def test_owner_lists_every_service_of_the_profile_without_contact_details(api, scenario: Scenario):
    response = api("/api/provider/services", as_auth_id=OWNER_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 20 and body["offset"] == 0
    assert _ids(body) == [str(scenario.company_unassigned.id), str(scenario.company_assigned.id)]
    item = body["items"][1]
    assert item == {
        "serviceId": str(scenario.company_assigned.id),
        "status": "confirmed",
        "serviceTypeName": "Mudanzas",
        "serviceAt": item["serviceAt"],
        "amount": 150000,
        "currency": "CLP",
        "originCommune": "Santiago",
        "destinationCommune": "Valparaíso",
        "isExclusive": False,
        "counterpartName": "Casey",
        "assignmentCount": 1,
    }
    assert body["items"][0]["assignmentCount"] == 0
    for secret in SECRET_CONTACT_VALUES:
        assert secret not in response.text


def test_employed_driver_lists_only_assigned_services(api, scenario: Scenario):
    response = api("/api/provider/services", as_auth_id=EMPLOYED_DRIVER_AUTH)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert _ids(response.json()) == [str(scenario.company_assigned.id)]


def test_independent_driver_lists_own_profile_services(api, scenario: Scenario):
    response = api("/api/provider/services", as_auth_id=INDEPENDENT_AUTH)

    assert response.status_code == 200
    assert _ids(response.json()) == [str(scenario.independent.id)]


def test_status_filter_and_page_caps(api, scenario: Scenario):
    filtered = api("/api/provider/services?status=in_progress", as_auth_id=OWNER_AUTH)
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 0 and filtered.json()["items"] == []

    assert api("/api/provider/services?status=bogus", as_auth_id=OWNER_AUTH).status_code == 422
    assert api("/api/provider/services?limit=51", as_auth_id=OWNER_AUTH).status_code == 422
    assert api("/api/provider/services?offset=5001", as_auth_id=OWNER_AUTH).status_code == 422


@pytest.mark.parametrize("auth_id", [CUSTOMER_AUTH, UNKNOWN_AUTH])
def test_non_provider_accounts_get_403_on_provider_routes(api, scenario: Scenario, auth_id):
    listing = api("/api/provider/services", as_auth_id=auth_id)
    detail = api(f"/api/provider/services/{scenario.company_assigned.id}", as_auth_id=auth_id)

    assert listing.status_code == 403
    assert detail.status_code == 403
    if auth_id == CUSTOMER_AUTH:
        assert listing.json()["detail"] == "Only provider accounts can access provider services."


def test_owner_reads_detail_with_assignments_and_can_manage(api, scenario: Scenario):
    response = api(f"/api/provider/services/{scenario.company_assigned.id}", as_auth_id=OWNER_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["viewerRole"] == "provider"
    assert body["canManage"] is True
    assert body["counterpartName"] == "Casey"
    assert body["description"] == "Mover un sofá"
    assert body["startedAt"] is None and body["completedAt"] is None and body["payoutDeadlineAt"] is None
    assert body["chatId"]
    assert body["assignments"] == [{
        "driverId": str(scenario.employed_driver.id),
        "driverFirstName": "Eli",
        "vehicleId": str(scenario.vehicle.id),
        "vehicleLabel": "Hyundai Porter",
        "plate": "ABCD12",
    }]
    for secret in SECRET_CONTACT_VALUES:
        assert secret not in response.text


def test_employed_driver_reads_assigned_detail_but_not_others(api, scenario: Scenario):
    assigned = api(f"/api/provider/services/{scenario.company_assigned.id}", as_auth_id=EMPLOYED_DRIVER_AUTH)
    unassigned = api(f"/api/provider/services/{scenario.company_unassigned.id}", as_auth_id=EMPLOYED_DRIVER_AUTH)

    assert assigned.status_code == 200
    assert assigned.json()["canManage"] is False
    assert unassigned.status_code == 404


def test_another_provider_gets_404_for_a_foreign_service(api, scenario: Scenario):
    response = api(f"/api/provider/services/{scenario.company_assigned.id}", as_auth_id=INDEPENDENT_AUTH)
    missing = api(f"/api/provider/services/{uuid4()}", as_auth_id=OWNER_AUTH)

    assert response.status_code == 404
    assert missing.status_code == 404


def test_customer_reads_own_service_detail(api, scenario: Scenario):
    response = api(f"/api/customer/services/{scenario.company_assigned.id}", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["viewerRole"] == "customer"
    assert body["canManage"] is False
    assert body["counterpartName"] == "Transportes Norte"
    assert body["status"] == "confirmed"
    assert len(body["assignments"]) == 1
    assert "+56933334444" not in response.text and "pat@example.test" not in response.text


def test_customer_cannot_read_another_customers_service(api, scenario: Scenario):
    response = api(f"/api/customer/services/{scenario.company_unassigned.id}", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 404


def test_independent_driver_counterpart_name_uses_the_real_name(api, scenario: Scenario):
    response = api(f"/api/customer/services/{scenario.independent.id}", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    assert response.json()["counterpartName"] == "Dana Driver"


def test_provider_account_gets_403_on_customer_detail(api, scenario: Scenario):
    response = api(f"/api/customer/services/{scenario.company_assigned.id}", as_auth_id=OWNER_AUTH)

    assert response.status_code == 403
