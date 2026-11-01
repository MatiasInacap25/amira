"""Provider profile settings over an in-memory database.

Only the owner of a provider ``Perfil`` (company owner or independent driver) may read or change it. Clients,
company-employed drivers, and accounts without a profile get 403 on every profile route.
"""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amira_api.auth import AuthenticatedUser, get_current_user, get_verified_user
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.settings import Settings, get_settings
from amira_api.models import Base, Perfil, RolPerfil, RolUsuario, ServicioDisponible, TipoServicio, Usuario
from chat_support import _register_btrim

CLIENT_AUTH = UUID("7c2f4a10-5d1e-4b8a-9f3c-000000000001")
OWNER_AUTH = UUID("7c2f4a10-5d1e-4b8a-9f3c-000000000002")
COMPANY_DRIVER_AUTH = UUID("7c2f4a10-5d1e-4b8a-9f3c-000000000003")
INDEPENDENT_AUTH = UUID("7c2f4a10-5d1e-4b8a-9f3c-000000000004")
UNKNOWN_AUTH = UUID("7c2f4a10-5d1e-4b8a-9f3c-000000000005")

COMMUNE_SANTIAGO = "13101"
COMMUNE_PROVIDENCIA = "13123"
SERVICE_MOVING = UUID("9e1b6c42-0a7d-4f3e-8b51-000000000001")
SERVICE_FLATBED = UUID("9e1b6c42-0a7d-4f3e-8b51-000000000002")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _register_btrim)
    tables = ("Rol_Usuario", "Usuario", "Rol_Perfil", "Perfil", "Servicios_Disponibles")
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in tables])
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE "Comunas" ("Codigo" VARCHAR(5) PRIMARY KEY, "Codigo_Region" VARCHAR(2) NOT NULL, "Nombre" VARCHAR(120) NOT NULL)'
        ))
        connection.execute(text(
            'CREATE TABLE "Tipos_Servicio" ("ID" CHAR(32) PRIMARY KEY, "Nombre_servicio" VARCHAR(120) NOT NULL, "Slug" VARCHAR(120) NOT NULL)'
        ))
        connection.execute(text(
            f"INSERT INTO \"Comunas\" VALUES ('{COMMUNE_SANTIAGO}', '13', 'Santiago'), "
            f"('{COMMUNE_PROVIDENCIA}', '13', 'Providencia')"
        ))
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def call(db):
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app)

    def request(method: str, path: str, *, as_auth_id: UUID, json: dict | None = None):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=as_auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
        return client.request(method, path, json=json)

    yield request
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def scenario(db: Session):
    roles = {code: RolUsuario(id=uuid4(), name=code, code=code)
             for code in ("client", "company_owner", "company_driver", "independent_driver")}
    profile_roles = {code: RolPerfil(id=uuid4(), name=code, code=code) for code in ("company", "independent_driver")}
    db.add_all([*roles.values(), *profile_roles.values()])

    def user(auth_id: UUID, first: str, role: str) -> Usuario:
        row = Usuario(id=uuid4(), auth_user_id=auth_id, first_name=first, last_name="Test",
                      email=f"{first.lower()}@example.test", role_id=roles[role].id)
        db.add(row)
        return row

    owner = user(OWNER_AUTH, "Pat", "company_owner")
    independent = user(INDEPENDENT_AUTH, "Dana", "independent_driver")
    user(CLIENT_AUTH, "Casey", "client")
    user(COMPANY_DRIVER_AUTH, "Eli", "company_driver")
    company = Perfil(id=uuid4(), owner_user_id=owner.id, name="Transportes Norte", kind="company",
                     role_id=profile_roles["company"].id)
    solo = Perfil(id=uuid4(), owner_user_id=independent.id, name="Dana Fletes", kind="independent_driver",
                  role_id=profile_roles["independent_driver"].id)
    db.add_all([company, solo])
    db.add_all([
        TipoServicio(id=SERVICE_MOVING, name="Mudanza", slug="mudanza"),
        TipoServicio(id=SERVICE_FLATBED, name="Camion plataforma", slug="camion-plataforma"),
    ])
    db.commit()
    return {"company": company, "solo": solo}


def _service_ids(db: Session, profile: Perfil) -> set[UUID]:
    rows = db.execute(select(ServicioDisponible.service_type_id).where(ServicioDisponible.profile_id == profile.id))
    return set(rows.scalars())


def _profile_body(**overrides) -> dict:
    # Every field is sent explicitly, as the form does; name is only valid for company profiles.
    body = {
        "name": "Transportes Norte",
        "description": "Fletes en Santiago",
        "commune_code": COMMUNE_SANTIAGO,
        "service_type_ids": [str(SERVICE_MOVING)],
    }
    body.update(overrides)
    return body


def _without(body: dict, *fields: str) -> dict:
    return {key: value for key, value in body.items() if key not in fields}


def _save_and_publish_company(call):
    assert call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body()).status_code == 200
    assert call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH).status_code == 200


@pytest.mark.parametrize("auth_id", [CLIENT_AUTH, COMPANY_DRIVER_AUTH, UNKNOWN_AUTH])
@pytest.mark.parametrize(("method", "path", "body"), [
    ("GET", "/api/provider/profile", None),
    ("PUT", "/api/provider/profile", _profile_body()),
    ("POST", "/api/provider/profile/publish", None),
    ("POST", "/api/provider/profile/unpublish", None),
])
def test_profile_routes_reject_non_owners_with_403(call, scenario, auth_id, method, path, body):
    response = call(method, path, as_auth_id=auth_id, json=body)

    assert response.status_code == 403


def test_get_profile_returns_shape_and_every_missing_item_for_a_new_company(call, scenario):
    response = call("GET", "/api/provider/profile", as_auth_id=OWNER_AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "name": "Transportes Norte",
        "kind": "company",
        "description": None,
        "commune_code": None,
        "service_type_ids": [],
        "published": False,
        "missing": ["description", "commune", "service_types"],
    }


def test_put_profile_saves_fields_and_replaces_service_rows(call, db, scenario):
    company = scenario["company"]

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(
        name="Transportes Sur",
        service_type_ids=[str(SERVICE_MOVING), str(SERVICE_FLATBED), str(SERVICE_MOVING)],
    ))

    assert response.status_code == 200
    assert response.json()["service_type_ids"] == [str(SERVICE_MOVING), str(SERVICE_FLATBED)]
    assert response.json()["missing"] == []
    db.refresh(company)
    assert company.name == "Transportes Sur"
    assert company.description == "Fletes en Santiago"
    assert company.commune_code == COMMUNE_SANTIAGO
    assert _service_ids(db, company) == {SERVICE_MOVING, SERVICE_FLATBED}

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(
        service_type_ids=[str(SERVICE_FLATBED)],
    ))

    assert response.status_code == 200
    assert _service_ids(db, company) == {SERVICE_FLATBED}


@pytest.mark.parametrize("omitted", ["description", "commune_code", "service_type_ids", "name"])
def test_put_profile_rejects_an_omitted_field_without_clearing_saved_data(call, db, scenario, omitted):
    company = scenario["company"]
    _save_and_publish_company(call)

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_without(_profile_body(), omitted))

    assert response.status_code == 422
    db.refresh(company)
    assert company.name == "Transportes Norte"
    assert company.description == "Fletes en Santiago"
    assert company.commune_code == COMMUNE_SANTIAGO
    assert _service_ids(db, company) == {SERVICE_MOVING}
    assert company.public_activated_at is not None


def test_put_profile_saves_an_independent_driver_without_a_name(call, db, scenario):
    solo = scenario["solo"]

    response = call("PUT", "/api/provider/profile", as_auth_id=INDEPENDENT_AUTH,
                    json=_without(_profile_body(), "name"))

    assert response.status_code == 200
    assert response.json()["name"] == "Dana Fletes"
    db.refresh(solo)
    assert solo.description == "Fletes en Santiago"


def test_explicit_nulls_and_empty_service_list_still_save_as_a_draft(call, db, scenario):
    company = scenario["company"]
    _save_and_publish_company(call)

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(
        description=None,
        commune_code=None,
        service_type_ids=[],
    ))

    assert response.status_code == 200
    assert response.json()["published"] is False
    assert response.json()["missing"] == ["description", "commune", "service_types"]
    db.refresh(company)
    assert company.name == "Transportes Norte"
    assert company.description is None
    assert company.commune_code is None
    assert _service_ids(db, company) == set()


def test_put_profile_rejects_unknown_commune_without_writing(call, db, scenario):
    company = scenario["company"]

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(
        commune_code="99999",
    ))

    assert response.status_code == 422
    db.refresh(company)
    assert company.commune_code is None
    assert _service_ids(db, company) == set()


@pytest.mark.parametrize("commune_code", ["1310", "131011", "13l01", " 13101"])
def test_put_profile_rejects_commune_codes_that_are_not_five_digits(call, db, scenario, commune_code):
    company = scenario["company"]

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(
        commune_code=commune_code,
    ))

    assert response.status_code == 422
    db.refresh(company)
    assert company.commune_code is None


def test_put_profile_rejects_unknown_service_type_without_writing(call, db, scenario):
    company = scenario["company"]

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(
        service_type_ids=[str(uuid4())],
    ))

    assert response.status_code == 422
    db.refresh(company)
    assert company.commune_code is None
    assert _service_ids(db, company) == set()


@pytest.mark.parametrize("name", ["Dana Fletes", "   "])
def test_put_profile_rejects_name_for_independent_driver(call, db, scenario, name):
    solo = scenario["solo"]

    response = call("PUT", "/api/provider/profile", as_auth_id=INDEPENDENT_AUTH, json=_profile_body(name=name))

    assert response.status_code == 422
    db.refresh(solo)
    assert solo.name == "Dana Fletes"


@pytest.mark.parametrize("name", ["", "   ", "x" * 161])
def test_put_profile_rejects_blank_or_oversized_company_name(call, scenario, name):
    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(name=name))

    assert response.status_code == 422


def test_put_profile_rejects_oversized_description(call, scenario):
    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(description="d" * 2001))

    assert response.status_code == 422


def test_publish_reports_every_missing_item_in_order(call, db, scenario):
    response = call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH)

    assert response.status_code == 422
    assert response.json()["detail"]["missing"] == ["description", "commune", "service_types"]
    db.refresh(scenario["company"])
    assert scenario["company"].public_activated_at is None


def test_publish_reports_only_the_missing_commune(call, db, scenario):
    call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(commune_code=None))

    response = call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH)

    assert response.status_code == 422
    assert response.json()["detail"]["missing"] == ["commune"]


def test_publish_sets_activation_once_and_keeps_the_original_timestamp(call, db, scenario):
    assert call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body()).status_code == 200

    first = call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH)
    db.refresh(scenario["company"])
    activated_at = scenario["company"].public_activated_at
    second = call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH)

    assert first.status_code == 200
    assert first.json()["published"] is True
    assert first.json()["missing"] == []
    assert activated_at is not None
    assert second.status_code == 200
    db.refresh(scenario["company"])
    assert scenario["company"].public_activated_at == activated_at


def test_publish_requires_a_description(call, db, scenario):
    call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(description=None))

    response = call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH)

    assert response.status_code == 422
    assert response.json()["detail"]["missing"] == ["description"]


def test_whitespace_only_description_counts_as_missing(call, db, scenario):
    saved = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(description="   "))

    response = call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH)

    assert saved.status_code == 200
    assert saved.json()["description"] is None
    assert response.status_code == 422
    assert response.json()["detail"]["missing"] == ["description"]


def test_publish_requires_at_least_one_service_type(call, db, scenario):
    call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(service_type_ids=[]))

    response = call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH)

    assert response.status_code == 422
    assert response.json()["detail"]["missing"] == ["service_types"]


@pytest.mark.parametrize("incomplete_body", [
    _profile_body(description=None),
    _profile_body(commune_code=None),
    _profile_body(service_type_ids=[]),
])
def test_put_that_leaves_published_profile_incomplete_unpublishes_it(call, db, scenario, incomplete_body):
    assert call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body()).status_code == 200
    assert call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH).status_code == 200

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=incomplete_body)

    assert response.status_code == 200
    assert response.json()["published"] is False
    assert response.json()["missing"]
    db.refresh(scenario["company"])
    assert scenario["company"].public_activated_at is None


def test_complete_put_keeps_a_published_profile_published_with_its_timestamp(call, db, scenario):
    call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body())
    call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH)
    db.refresh(scenario["company"])
    activated_at = scenario["company"].public_activated_at

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(description="Nuevo texto"))

    assert response.status_code == 200
    assert response.json()["published"] is True
    assert response.json()["missing"] == []
    db.refresh(scenario["company"])
    assert scenario["company"].public_activated_at == activated_at


def test_unknown_service_type_mid_list_leaves_profile_and_services_unchanged(call, db, scenario):
    call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body())
    company = scenario["company"]

    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(
        description="Cambio que no debe guardarse",
        service_type_ids=[str(SERVICE_FLATBED), str(uuid4()), str(SERVICE_MOVING)],
    ))

    assert response.status_code == 422
    db.refresh(company)
    assert company.description == "Fletes en Santiago"
    assert _service_ids(db, company) == {SERVICE_MOVING}


def test_profile_id_in_body_is_rejected(call, db, scenario):
    response = call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body(
        profile_id=str(uuid4()),
    ))

    assert response.status_code == 422


@pytest.mark.parametrize(("method", "path", "body"), [
    ("GET", "/api/provider/profile", None),
    ("PUT", "/api/provider/profile", _profile_body()),
    ("POST", "/api/provider/profile/publish", None),
    ("POST", "/api/provider/profile/unpublish", None),
])
def test_aal1_session_is_forbidden_on_every_profile_route(db, scenario, method, path, body):
    # Overrides only the token check so the real assurance boundary in get_current_user runs.
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_verified_user] = lambda: AuthenticatedUser(
        id=OWNER_AUTH,
        email="owner@example.test",
        session_id=uuid4(),
        assurance="aal1",
        authentication_methods=frozenset({"password"}),
    )
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    try:
        response = TestClient(app).request(method, path, json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_unpublish_clears_activation(call, db, scenario):
    call("PUT", "/api/provider/profile", as_auth_id=OWNER_AUTH, json=_profile_body())
    call("POST", "/api/provider/profile/publish", as_auth_id=OWNER_AUTH)

    response = call("POST", "/api/provider/profile/unpublish", as_auth_id=OWNER_AUTH)

    assert response.status_code == 200
    assert response.json()["published"] is False
    db.refresh(scenario["company"])
    assert scenario["company"].public_activated_at is None
