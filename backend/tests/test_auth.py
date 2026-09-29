import asyncio
from datetime import datetime, timedelta, timezone
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.main import app
from amira_api.settings import Settings, get_settings


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
        "aal": "aal2",
        "role": "authenticated",
        "email": "person@example.test",
        "is_anonymous": False,
    }
    claims.update(overrides)
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-key"})


def auth_app(monkeypatch, token: str | None, *, fallback_verifier=None, proof: str | None = None):
    from amira_api import auth

    monkeypatch.setattr(auth, "PyJWKClient", FakeJwkClient)
    auth._jwks_client.cache_clear()
    if fallback_verifier is not None:
        monkeypatch.setattr(auth, "verify_email_fallback_proof", fallback_verifier)

    async def endpoint(current_user: AuthenticatedUser = Depends(get_current_user)):
        return {"user_id": str(current_user.id), "assurance": current_user.assurance}

    app.add_api_route("/auth-test", endpoint, methods=["GET"])
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, supabase_jwt_issuer=ISSUER)

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            if proof:
                headers["X-Amira-Email-Fallback-Proof"] = proof
            return await client.get("/auth-test", headers=headers)

    try:
        return asyncio.run(request())
    finally:
        app.dependency_overrides.clear()
        auth._jwks_client.cache_clear()
        app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) != "/auth-test"]


def test_signed_aal2_supabase_token_is_accepted(monkeypatch):
    response = auth_app(monkeypatch, make_token())

    assert response.status_code == 200
    assert response.json() == {"user_id": USER_ID, "assurance": "aal2"}


def test_invalid_bearer_is_rejected(monkeypatch):
    response = auth_app(monkeypatch, "not-a-jwt")

    assert response.status_code == 401


def test_missing_bearer_is_rejected(monkeypatch):
    response = auth_app(monkeypatch, None)

    assert response.status_code == 401


def test_forged_signature_is_rejected(monkeypatch):
    forged = jwt.encode(
        {"iss": ISSUER, "aud": "authenticated", "exp": datetime.now(timezone.utc) + timedelta(minutes=5), "sub": USER_ID, "aal": "aal2", "session_id": SESSION_ID},
        "attacker-secret-that-is-long-enough-for-hmac",
        algorithm="HS256",
    )
    response = auth_app(monkeypatch, forged)

    assert response.status_code == 401


def test_expired_wrong_issuer_and_wrong_audience_tokens_fail_closed(monkeypatch):
    now = datetime.now(timezone.utc)
    tokens = (
        make_token(exp=now - timedelta(seconds=1)),
        make_token(iss="https://attacker.example/auth/v1"),
        make_token(aud="some-other-audience"),
    )

    for token in tokens:
        assert auth_app(monkeypatch, token).status_code == 401


def test_aal1_requires_server_verified_fallback_proof(monkeypatch):
    token = make_token(aal="aal1")

    assert auth_app(monkeypatch, token).status_code == 403
    response = auth_app(monkeypatch, token, fallback_verifier=lambda claims, proof: proof == "verified", proof="verified")
    assert response.status_code == 200
    assert response.json()["assurance"] == "email_fallback"


def test_invalid_subject_or_missing_assurance_is_rejected(monkeypatch):
    for overrides in ({"sub": "not-a-uuid"}, {"aal": None}):
        assert auth_app(monkeypatch, make_token(**overrides)).status_code == 401


def test_session_id_must_be_a_non_nil_uuid(monkeypatch):
    invalid_sessions = (
        make_token(session_id="not-a-uuid"),
        make_token(session_id="00000000-0000-0000-0000-000000000000"),
        make_token(session_id=None),
        make_token(session_id=""),
        jwt.encode(
                {
                    key: value
                    for key, value in jwt.decode(
                        make_token(),
                        PRIVATE_KEY.public_key(),
                        algorithms=["RS256"],
                        options={"verify_exp": False, "verify_aud": False},
                    ).items()
                    if key != "session_id"
                },
            PRIVATE_KEY,
            algorithm="RS256",
            headers={"kid": "test-key"},
        ),
    )

    for token in invalid_sessions:
        assert auth_app(monkeypatch, token).status_code == 401
