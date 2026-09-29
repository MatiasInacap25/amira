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
from typing import Annotated
from uuid import UUID

import jwt

from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from amira_api.settings import Settings, get_settings


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str
    session_id: UUID
    assurance: str


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, timeout=3, lifespan=300)


def verify_email_fallback_proof(claims: dict, proof: str | None) -> bool:
    """Fail-closed seam for the separately implemented email challenge flow.

    T4/T5 own issuance and verification of the short-lived, single-use,
    session-bound proof. An arbitrary header or Supabase email OTP is never
    accepted as proof of AAL2 here.
    """
    return False


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Invalid authentication credentials.", headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: str | None = Header(default=None),
    fallback_proof: str | None = Header(default=None, alias="X-Amira-Email-Fallback-Proof"),
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
    except HTTPException:
        raise
    except (PyJWTError, ValueError, KeyError, TypeError):
        raise _unauthorized() from None
    except Exception:
        # JWKS transport/rotation failures never turn into an unverified request.
        raise _unauthorized() from None

    if claims["aal"] == "aal2":
        assurance = "aal2"
    elif claims["aal"] == "aal1" and verify_email_fallback_proof(claims, fallback_proof):
        assurance = "email_fallback"
    else:
        raise HTTPException(status_code=403, detail="Additional authentication assurance is required.")

    return AuthenticatedUser(id=subject, email=email, session_id=session_id, assurance=assurance)
