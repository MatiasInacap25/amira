import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, Response
from sqlalchemy import UniqueConstraint

from amira_api import auth
from amira_api.account_routes import provision_account
from amira_api.account_schemas import AccountProvisionRequest
from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import RolUsuario, Usuario
from amira_api.settings import Settings, get_settings, warn_if_dev_sms_mfa_bypass_active


PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
USER_ID = "123e4567-e89b-12d3-a456-426614174000"
SESSION_ID = "123e4567-e89b-12d3-a456-426614174001"
ISSUER = "https://project-ref.supabase.co/auth/v1"


class FakeSigningKey:
    key = PRIVATE_KEY.public_key()
    algorithm_name = "RS256"


class FakeJwkClient:
    def __init__(self, *args, **kwargs):
        pass

    def get_signing_key_from_jwt(self, token):
        return FakeSigningKey()


def make_token(**overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "iss": ISSUER,
        "aud": "authenticated",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "sub": USER_ID,
        "session_id": SESSION_ID,
        "aal": "aal1",
        "role": "authenticated",
        "amr": [{"method": "password", "timestamp": int(now.timestamp())}],
        "email": "person@example.test",
        "is_anonymous": False,
    }
    claims.update(overrides)
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-key"})


def request_protected_route(monkeypatch, token: str, *, dev_skip: bool, app_env: str = "development"):
    monkeypatch.setattr(auth, "PyJWKClient", FakeJwkClient)
    auth._jwks_client.cache_clear()

    async def endpoint(current_user: AuthenticatedUser = Depends(get_current_user)):
        return {"user_id": str(current_user.id), "assurance": current_user.assurance}

    app.add_api_route("/auth-test", endpoint, methods=["GET"])
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        supabase_jwt_issuer=ISSUER,
        dev_skip_sms_mfa=dev_skip,
        app_env=app_env,
    )
    app.dependency_overrides[get_db_session] = lambda: object()

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/auth-test", headers={"Authorization": f"Bearer {token}"})

    try:
        return asyncio.run(request())
    finally:
        app.dependency_overrides.clear()
        auth._jwks_client.cache_clear()
        app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) != "/auth-test"]


def test_bypass_is_off_by_default(monkeypatch):
    monkeypatch.delenv("DEV_SKIP_SMS_MFA", raising=False)

    assert Settings(_env_file=None).dev_skip_sms_mfa is False


def test_bypass_reads_dev_skip_sms_mfa_environment_variable(monkeypatch):
    monkeypatch.setenv("DEV_SKIP_SMS_MFA", "true")
    monkeypatch.setenv("APP_ENV", "development")

    assert Settings(_env_file=None).dev_skip_sms_mfa is True


def test_bypass_on_with_app_env_unset_fails_closed(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(RuntimeError, match="set explicitly to development, local or test"):
        Settings(_env_file=None, dev_skip_sms_mfa=True)


def test_bypass_on_with_app_env_unset_fails_closed_even_though_default_is_allowlisted(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)

    assert Settings(_env_file=None).app_env == "development"
    with pytest.raises(RuntimeError, match="set explicitly"):
        Settings(_env_file=None, dev_skip_sms_mfa=True)


def test_bypass_on_with_app_env_explicitly_development_works(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)

    assert Settings(_env_file=None, app_env="development", dev_skip_sms_mfa=True).dev_sms_mfa_bypass_active is True


def test_bypass_on_with_app_env_from_environment_variable_works(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")

    assert Settings(_env_file=None, dev_skip_sms_mfa=True).dev_sms_mfa_bypass_active is True


def test_bypass_off_with_app_env_unset_works(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)

    settings = Settings(_env_file=None, dev_skip_sms_mfa=False)

    assert settings.app_env == "development"
    assert settings.dev_sms_mfa_bypass_active is False


def test_bypass_off_rejects_aal1_password_session_without_proof(monkeypatch):
    response = request_protected_route(monkeypatch, make_token(), dev_skip=False)

    assert response.status_code == 403


def test_bypass_on_accepts_aal1_password_session(monkeypatch):
    response = request_protected_route(monkeypatch, make_token(), dev_skip=True)

    assert response.status_code == 200
    assert response.json() == {"user_id": USER_ID, "assurance": "dev_password_bypass"}


def test_bypass_on_accepts_aal1_password_session_in_allowed_environment(monkeypatch):
    response = request_protected_route(monkeypatch, make_token(), dev_skip=True, app_env="local")

    assert response.status_code == 200
    assert response.json()["assurance"] == "dev_password_bypass"


def test_bypass_on_rejects_anonymous_aal1_session(monkeypatch):
    response = request_protected_route(monkeypatch, make_token(is_anonymous=True), dev_skip=True)

    assert response.status_code == 401


def test_bypass_on_rejects_aal1_session_without_password_method(monkeypatch):
    token = make_token(amr=[{"method": "otp", "timestamp": 1}])

    response = request_protected_route(monkeypatch, token, dev_skip=True)

    assert response.status_code == 403


def test_bypass_on_rejects_aal1_session_without_email(monkeypatch):
    # Supabase access tokens carry no email_confirmed claim; the API can only verify
    # the email it receives, and Supabase withholds sessions from unconfirmed users.
    token = make_token(email="")

    response = request_protected_route(monkeypatch, token, dev_skip=True)

    assert response.status_code == 401


def test_bypass_on_rejects_aal1_session_with_wrong_issuer(monkeypatch):
    token = make_token(iss="https://attacker.example/auth/v1")

    response = request_protected_route(monkeypatch, token, dev_skip=True)

    assert response.status_code == 401


def test_bypass_on_rejects_aal1_session_with_wrong_role(monkeypatch):
    response = request_protected_route(monkeypatch, make_token(role="anon"), dev_skip=True)

    assert response.status_code == 401


@pytest.mark.parametrize("app_env", ["development", "local", "test", " Development ", "LOCAL", "Test\n"])
def test_bypass_activates_only_for_allowlisted_environments(app_env):
    settings = Settings(_env_file=None, app_env=app_env, dev_skip_sms_mfa=True)

    assert settings.dev_sms_mfa_bypass_active is True


@pytest.mark.parametrize("app_env", ["production", "prod", "staging", "preview", "developmnet", "", "   "])
def test_bypass_on_outside_allowlist_fails_closed_at_settings_construction(app_env):
    with pytest.raises(RuntimeError, match="development, local, test"):
        Settings(_env_file=None, app_env=app_env, dev_skip_sms_mfa=True)


@pytest.mark.parametrize("app_env", ["production", "prod", "staging", "preview", "developmnet", "", "development"])
def test_bypass_off_works_in_any_environment(app_env):
    settings = Settings(_env_file=None, app_env=app_env, dev_skip_sms_mfa=False)

    assert settings.dev_sms_mfa_bypass_active is False


def test_fail_closed_error_does_not_echo_other_settings():
    secret_url = "postgresql://user:hunter2-secret@db.example.test/amira"

    with pytest.raises(RuntimeError) as excinfo:
        Settings(_env_file=None, app_env="production", dev_skip_sms_mfa=True, database_url=secret_url)

    message = str(excinfo.value)
    assert "hunter2-secret" not in message
    assert secret_url not in message
    assert "DEV_SKIP_SMS_MFA" in message


def test_startup_warning_is_logged_only_when_bypass_is_active(caplog):
    with caplog.at_level(logging.WARNING, logger="amira_api.settings"):
        warn_if_dev_sms_mfa_bypass_active(Settings(_env_file=None, dev_skip_sms_mfa=False))
    assert caplog.records == []

    with caplog.at_level(logging.WARNING, logger="amira_api.settings"):
        warn_if_dev_sms_mfa_bypass_active(Settings(_env_file=None, app_env="development", dev_skip_sms_mfa=True))
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "DEV_SKIP_SMS_MFA" in caplog.records[0].getMessage()


def test_provisioning_accepts_aal1_password_session_under_bypass():
    identity = AuthenticatedUser(
        id=UUID(USER_ID),
        email="person@example.test",
        session_id=UUID(SESSION_ID),
        assurance="aal1",
        authentication_methods=frozenset({"password"}),
    )
    settings = Settings(_env_file=None, app_env="development", dev_skip_sms_mfa=True)
    current_user = get_current_user(current_user=identity, settings=settings, session=object(), fallback_proof=None)
    session = FakeProvisioningSession(
        [
            RolUsuario(id=CLIENT_ROLE_ID, code="client", name="client"),
            None,
        ]
    )
    payload = AccountProvisionRequest(
        role="client",
        first_name="Casey",
        last_name="Customer",
        national_id="12345678-5",
        birth_date=date(1990, 1, 1),
        phone="+56912345678",
    )

    response = provision_account(payload, current_user, session, settings, Response())

    assert response.role == "client"
    assert [type(item) for item in session.added] == [Usuario]
    assert session.commits == 1


def test_usuario_phone_has_no_uniqueness_constraint():
    table = Usuario.__table__
    phone_column = table.c["Telefono"]

    assert not phone_column.unique
    assert not any(
        isinstance(constraint, UniqueConstraint) and [column.name for column in constraint.columns] == ["Telefono"]
        for constraint in table.constraints
    )
    assert not any(index.unique and [column.name for column in index.columns] == ["Telefono"] for index in table.indexes)


CLIENT_ROLE_ID = UUID("b2000000-0000-4000-8000-000000000001")


class Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeProvisioningSession:
    def __init__(self, values):
        self.values = list(values)
        self.added = []
        self.commits = 0

    def execute(self, statement):
        return Result(self.values.pop(0))

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = UUID("123e4567-e89b-12d3-a456-426614174999")

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass
