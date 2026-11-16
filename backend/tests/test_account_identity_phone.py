"""Account identity readback and the SMS-verified phone change."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amira_api.account_routes import get_phone_factor_reader
from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.auth_phone_factors import AuthAdminUnavailable, PhoneFactor, SupabasePhoneFactorReader
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import Base, Perfil, RolPerfil, RolUsuario, Usuario
from chat_support import _register_btrim

OWNER_AUTH = UUID("6a2e0b33-0000-4000-8000-000000000001")
OTHER_AUTH = UUID("6a2e0b33-0000-4000-8000-000000000002")
OLD_PHONE = "+56911111111"
NEW_PHONE = "+56922222222"
NEW_FACTOR = UUID("6a2e0b33-0000-4000-8000-0000000000f2")
URL = "/api/account/phone"


class FakeFactors:
    def __init__(self) -> None:
        self.factors: list[PhoneFactor] = []
        self.error: Exception | None = None
        self.asked: list[UUID] = []

    def verified_phone_factors(self, auth_user_id: UUID) -> list[PhoneFactor]:
        self.asked.append(auth_user_id)
        if self.error:
            raise self.error
        return list(self.factors)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _register_btrim)
    tables = ("Rol_Usuario", "Rol_Perfil", "Usuario", "Perfil")
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in tables])
    with Session(engine) as session:
        role = RolUsuario(id=uuid4(), name="client", code="client")
        session.add(role)
        session.flush()
        for auth_id, rut in ((OWNER_AUTH, "12345678-5"), (OTHER_AUTH, "11111111-1")):
            session.add(Usuario(id=uuid4(), auth_user_id=auth_id, first_name="Camila", last_name="Rojas",
                                email=f"{auth_id}@example.test", national_id=rut, phone=OLD_PHONE, role_id=role.id))
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def factors() -> FakeFactors:
    return FakeFactors()


@pytest.fixture
def client(db, factors):
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_phone_factor_reader] = lambda: factors
    yield TestClient(app)
    app.dependency_overrides.clear()


def as_user(auth_id: UUID = OWNER_AUTH, assurance: str = "aal2") -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=auth_id, email="caller@example.test", session_id=uuid4(), assurance=assurance,
        authentication_methods=frozenset({"password", "phone"}),
    )


def stored_phones(db: Session) -> dict[UUID, str | None]:
    db.expire_all()
    return {user.auth_user_id: user.phone for user in db.execute(select(Usuario)).scalars()}


def test_me_returns_the_name_rut_and_phone(client) -> None:
    as_user()
    response = client.get("/api/account/me")
    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in ("role", "first_name", "last_name", "national_id", "phone")} == {
        "role": "client", "first_name": "Camila", "last_name": "Rojas", "national_id": "12345678-5", "phone": OLD_PHONE,
    }
    assert body["profile_id"] is None


def test_a_verified_sms_factor_changes_the_phone(client, db, factors) -> None:
    as_user()
    factors.factors = [PhoneFactor(id=uuid4(), phone="56911111111"), PhoneFactor(id=NEW_FACTOR, phone="56922222222")]
    response = client.put(URL, json={"factor_id": str(NEW_FACTOR), "phone": "+56 9 2222 2222"})
    assert response.status_code == 200
    assert response.json()["phone"] == NEW_PHONE
    assert stored_phones(db) == {OWNER_AUTH: NEW_PHONE, OTHER_AUTH: OLD_PHONE}
    assert factors.asked == [OWNER_AUTH]


@pytest.mark.parametrize("factor", [
    PhoneFactor(id=NEW_FACTOR, phone="56933333333"),  # the factor holds another number
    PhoneFactor(id=uuid4(), phone="56922222222"),  # the number is on another factor than the one sent
])
def test_a_phone_without_its_verified_factor_is_refused(client, db, factors, factor) -> None:
    as_user()
    factors.factors = [factor]
    response = client.put(URL, json={"factor_id": str(NEW_FACTOR), "phone": NEW_PHONE})
    assert response.status_code == 422
    assert response.json()["detail"] == "Verifica el número nuevo con el código SMS antes de guardarlo."
    assert stored_phones(db) == {OWNER_AUTH: OLD_PHONE, OTHER_AUTH: OLD_PHONE}


def test_a_session_without_sms_verification_cannot_change_the_phone(client, db, factors) -> None:
    as_user(assurance="aal1")
    factors.factors = [PhoneFactor(id=NEW_FACTOR, phone="56922222222")]
    response = client.put(URL, json={"factor_id": str(NEW_FACTOR), "phone": NEW_PHONE})
    assert response.status_code == 403
    assert response.json()["detail"] == "Verifica el número nuevo con el código SMS antes de guardarlo."
    assert stored_phones(db)[OWNER_AUTH] == OLD_PHONE
    assert factors.asked == []


def test_a_malformed_phone_is_rejected_before_asking_supabase(client, db, factors) -> None:
    as_user()
    response = client.put(URL, json={"factor_id": str(NEW_FACTOR), "phone": "912345678"})
    assert response.status_code == 422
    assert factors.asked == []
    assert stored_phones(db)[OWNER_AUTH] == OLD_PHONE


def test_an_account_that_is_not_provisioned_gets_404(client, factors) -> None:
    as_user(uuid4())
    factors.factors = [PhoneFactor(id=NEW_FACTOR, phone="56922222222")]
    response = client.put(URL, json={"factor_id": str(NEW_FACTOR), "phone": NEW_PHONE})
    assert response.status_code == 404


def test_supabase_unavailable_answers_503_and_keeps_the_phone(client, db, factors) -> None:
    as_user()
    factors.error = AuthAdminUnavailable("down")
    response = client.put(URL, json={"factor_id": str(NEW_FACTOR), "phone": NEW_PHONE})
    assert response.status_code == 503
    assert stored_phones(db)[OWNER_AUTH] == OLD_PHONE


def test_the_reader_dependency_fails_closed_without_supabase_admin_settings() -> None:
    from fastapi import HTTPException

    from amira_api.settings import Settings

    with pytest.raises(HTTPException) as caught:
        get_phone_factor_reader(Settings(_env_file=None, supabase_url=None, supabase_service_role_key=None))
    assert caught.value.status_code == 503


# Supabase admin adapter


def _reader(handler) -> SupabasePhoneFactorReader:
    return SupabasePhoneFactorReader(url="https://project.supabase.co", service_role_key="service-key",
                                     transport=httpx.MockTransport(handler))


def test_the_adapter_keeps_only_verified_phone_factors() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": str(OWNER_AUTH), "factors": [
            {"id": str(NEW_FACTOR), "factor_type": "phone", "status": "verified", "phone": "56922222222"},
            {"id": str(uuid4()), "factor_type": "phone", "status": "unverified", "phone": "56933333333"},
            {"id": str(uuid4()), "factor_type": "totp", "status": "verified"},
        ]})

    assert _reader(handler).verified_phone_factors(OWNER_AUTH) == [PhoneFactor(id=NEW_FACTOR, phone="56922222222")]
    assert seen[0].url.path == f"/auth/v1/admin/users/{OWNER_AUTH}"
    assert seen[0].headers["apikey"] == "service-key"
    assert seen[0].headers["authorization"] == "Bearer service-key"


def test_the_adapter_reads_a_user_without_factors_as_none() -> None:
    assert _reader(lambda request: httpx.Response(200, json={"id": str(OWNER_AUTH)})).verified_phone_factors(OWNER_AUTH) == []


@pytest.mark.parametrize("handler", [
    lambda request: httpx.Response(500, json={}),
    lambda request: httpx.Response(200, json={"factors": "nope"}),
    lambda request: httpx.Response(200, text="not json"),
])
def test_the_adapter_reports_failures_as_unavailable(handler) -> None:
    with pytest.raises(AuthAdminUnavailable):
        _reader(handler).verified_phone_factors(OWNER_AUTH)


def test_the_adapter_reports_a_network_error_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(AuthAdminUnavailable):
        _reader(handler).verified_phone_factors(OWNER_AUTH)
