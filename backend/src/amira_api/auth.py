"""Verify Supabase access tokens and enforce the API's assurance boundary."""

# Claim and JWKS behavior follows Supabase's official JWT references:
# https://supabase.com/docs/guides/auth/jwt-fields
# https://supabase.com/docs/guides/auth/jwts
# AAL values are not interchangeable with an email OTP:
# https://supabase.com/docs/guides/auth/auth-mfa
# Confirm-email signup returns no session until the user confirms:
# https://supabase.com/docs/reference/python/auth-signup

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import hmac
from typing import Annotated
from uuid import UUID

import jwt

from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from amira_api.db import get_db_session
from amira_api.models import EmailFallbackChallenge
from amira_api.settings import Settings, get_settings


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str
    session_id: UUID
    assurance: str
    authentication_methods: frozenset[str]


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, timeout=3, lifespan=300)


def _proof_hash(proof: str, settings: Settings) -> str | None:
    secret = settings.email_fallback_secret
    if secret is None:
        return None
    key = secret.get_secret_value().encode("utf-8")
    if len(key) < 32:
        return None
    try:
        encoded_proof = proof.encode("ascii")
    except UnicodeEncodeError:
        return None
    return hmac.new(key, b"email-proof:" + encoded_proof, hashlib.sha256).hexdigest()


def verify_email_fallback_proof(
    claims: dict,
    proof: str | None,
    session: Session,
    settings: Settings,
) -> bool:
    """Atomically consume a server-minted, one-use proof for its exact auth session."""
    if not proof or len(proof) > 128 or claims.get("aal") != "aal1":
        return False
    methods = claims.get("amr", [])
    if not isinstance(methods, list) or not any(
        isinstance(item, dict) and item.get("method") == "password" for item in methods
    ):
        return False
    proof_hash = _proof_hash(proof, settings)
    if proof_hash is None:
        return False
    try:
        auth_user_id = UUID(claims["sub"])
        session_id = UUID(claims["session_id"])
    except (KeyError, TypeError, ValueError):
        return False
    if auth_user_id.int == 0 or session_id.int == 0:
        return False

    consumed_id = session.execute(
        update(EmailFallbackChallenge)
        .where(
            EmailFallbackChallenge.auth_user_id == auth_user_id,
            EmailFallbackChallenge.auth_session_id == str(session_id),
            EmailFallbackChallenge.activated_at.is_not(None),
            EmailFallbackChallenge.proof_hash == proof_hash,
            EmailFallbackChallenge.proof_expires_at > func.now(),
            EmailFallbackChallenge.proof_consumed_at.is_(None),
        )
        .values(proof_consumed_at=func.now())
        .returning(EmailFallbackChallenge.id)
    ).scalar_one_or_none()
    if consumed_id is None:
        return False
    session.commit()
    return True


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Invalid authentication credentials.", headers={"WWW-Authenticate": "Bearer"})


def get_verified_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser:
    if not settings.supabase_jwt_issuer:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise _unauthorized()

    jwks_url = f"{settings.supabase_jwt_issuer.rstrip('/')}/.well-known/jwks.json"
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=[signing_key.algorithm_name],
            issuer=settings.supabase_jwt_issuer,
            audience=settings.supabase_jwt_audience,
            options={
                "require": ["iss", "aud", "exp", "iat", "sub", "aal", "session_id", "email", "role", "is_anonymous"],
            },
        )
        subject = UUID(claims["sub"])
        email = claims["email"].strip().lower()
        session_id = UUID(claims["session_id"])
        if not email or session_id.int == 0 or claims["role"] != "authenticated" or claims["is_anonymous"] is not False:
            raise _unauthorized()
        if claims["aal"] not in ("aal1", "aal2"):
            raise _unauthorized()
        raw_methods = claims.get("amr", [])
        if not isinstance(raw_methods, list):
            raise _unauthorized()
        methods = frozenset(
            method
            for item in raw_methods
            if isinstance(item, dict) and isinstance((method := item.get("method")), str)
        )
    except HTTPException:
        raise
    except (PyJWTError, ValueError, KeyError, TypeError):
        raise _unauthorized() from None
    except Exception:
        # JWKS transport/rotation failures never turn into an unverified request.
        raise _unauthorized() from None

    return AuthenticatedUser(
        id=subject,
        email=email,
        session_id=session_id,
        assurance=claims["aal"],
        authentication_methods=methods,
    )


def get_current_user(
    current_user: Annotated[AuthenticatedUser, Depends(get_verified_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
    fallback_proof: str | None = Header(default=None, alias="X-Amira-Email-Fallback-Proof"),
) -> AuthenticatedUser:
    if current_user.assurance == "aal2":
        return current_user
    if current_user.assurance == "aal1" and "password" in current_user.authentication_methods and verify_email_fallback_proof(
        {"sub": str(current_user.id), "session_id": str(current_user.session_id), "aal": "aal1", "amr": [{"method": method} for method in current_user.authentication_methods]},
        fallback_proof,
        session,
        settings,
    ):
        return AuthenticatedUser(
            id=current_user.id,
            email=current_user.email,
            session_id=current_user.session_id,
            assurance="email_fallback",
            authentication_methods=current_user.authentication_methods,
        )
    else:
        raise HTTPException(status_code=403, detail="Additional authentication assurance is required.")
