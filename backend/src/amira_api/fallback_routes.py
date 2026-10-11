"""Server-side email fallback challenge and one-use session proof endpoints."""

import hashlib
import hmac
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Iterator, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_verified_user
from amira_api.db import get_db_session
from amira_api.models import EmailFallbackChallenge
from amira_api.settings import Settings, get_settings

router = APIRouter(prefix="/api/account/email-fallback", tags=["account security"])

# Safe local defaults: six-digit codes expire in 10 minutes, allow 5 guesses,
# and at most 3 sends per 15 minutes; resulting 256-bit proofs last 5 minutes.
CODE_TTL = timedelta(minutes=10)
PROOF_TTL = timedelta(minutes=5)
ISSUE_WINDOW = timedelta(minutes=15)
MAX_CHALLENGES_PER_WINDOW = 3
MAX_CODE_ATTEMPTS = 5


class EmailFallbackSender(Protocol):
    """Transport port; T4 supplies configured delivery, tests use a fake."""

    def send_code(self, email: str, code: str) -> bool: ...


def get_email_fallback_sender() -> EmailFallbackSender | None:
    """No production sender is configured until T4 supplies its adapter."""
    return None


class EmailCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[0-9]{6}$")


class ChallengeResponse(BaseModel):
    expires_in_seconds: int
    delivery: str = "email"


class ProofResponse(BaseModel):
    proof: str
    expires_in_seconds: int
    assurance: str = "email_fallback"


def _key(settings: Settings) -> bytes:
    secret = settings.email_fallback_secret
    if secret is None:
        raise HTTPException(status_code=503, detail="Email fallback is not configured.")
    key = secret.get_secret_value().encode("utf-8")
    if len(key) < 32:
        raise HTTPException(status_code=503, detail="Email fallback is not configured.")
    return key


def _code_hash(challenge_id: UUID, code: str, key: bytes) -> str:
    material = b"email-code:" + challenge_id.bytes + b":" + code.encode("ascii")
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def _proof_hash(proof: str, key: bytes) -> str:
    return hmac.new(key, b"email-proof:" + proof.encode("ascii"), hashlib.sha256).hexdigest()


def _require_password_session(user: AuthenticatedUser) -> None:
    if user.assurance != "aal1" or "password" not in user.authentication_methods:
        raise HTTPException(status_code=403, detail="Email fallback requires an AAL1 password session.")


@contextmanager
def _issuance_lock(session: Session, user: AuthenticatedUser) -> Iterator[None]:
    """Serialize a user's complete issue/send/activate sequence on PostgreSQL."""
    if session.get_bind().dialect.name == "postgresql":
        lock_key = f"amira-email-fallback-issuance:{user.id}"
        # Keep a dedicated connection checked out across the ORM commits so the
        # session-level lock covers the provider call and activation ordering.
        with session.get_bind().connect() as lock_connection:
            lock_connection.execute(select(func.pg_advisory_lock(func.hashtextextended(lock_key, 0))))
            lock_connection.commit()
            try:
                yield
            finally:
                lock_connection.execute(select(func.pg_advisory_unlock(func.hashtextextended(lock_key, 0))))
                lock_connection.commit()
    else:
        yield


def _database_now(session: Session) -> datetime:
    value = session.execute(select(func.now())).scalar_one()
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _invalidate_previous_challenges(session: Session, user: AuthenticatedUser, except_id: UUID) -> None:
    scope = (
        EmailFallbackChallenge.auth_user_id == user.id,
        EmailFallbackChallenge.auth_session_id == str(user.session_id),
    )
    session.execute(
        update(EmailFallbackChallenge)
        .where(*scope, EmailFallbackChallenge.id != except_id, EmailFallbackChallenge.consumed_at.is_(None))
        .values(consumed_at=func.now())
    )
    session.execute(
        update(EmailFallbackChallenge)
        .where(
            *scope,
            EmailFallbackChallenge.id != except_id,
            EmailFallbackChallenge.proof_hash.is_not(None),
            EmailFallbackChallenge.proof_consumed_at.is_(None),
        )
        .values(proof_consumed_at=func.now())
    )


@router.post("/challenge", response_model=ChallengeResponse, status_code=202)
def issue_email_code(
    user: Annotated[AuthenticatedUser, Depends(get_verified_user)],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    sender: Annotated[EmailFallbackSender | None, Depends(get_email_fallback_sender)],
) -> ChallengeResponse:
    _require_password_session(user)
    key = _key(settings)
    if sender is None:
        raise HTTPException(status_code=503, detail="Email fallback delivery is not configured.")

    with _issuance_lock(session, user):
        now = _database_now(session)
        recent_count = session.execute(
            select(func.count())
            .select_from(EmailFallbackChallenge)
            .where(
                EmailFallbackChallenge.auth_user_id == user.id,
                EmailFallbackChallenge.created_at >= now - ISSUE_WINDOW,
            )
        ).scalar_one()
        if recent_count >= MAX_CHALLENGES_PER_WINDOW:
            raise HTTPException(status_code=429, detail="Email fallback rate limit exceeded.")

        challenge_id = UUID(bytes=secrets.token_bytes(16), version=4)
        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge = EmailFallbackChallenge(
            id=challenge_id,
            user_id=None,
            auth_user_id=user.id,
            auth_session_id=str(user.session_id),
            code_hash=_code_hash(challenge_id, code, key),
            expires_at=now + CODE_TTL,
            attempt_count=0,
        )
        # Pending rows count against abuse limits, but are not verifiable until
        # the sender explicitly confirms delivery.
        session.add(challenge)
        session.commit()
        try:
            delivered = sender.send_code(user.email, code)
        except Exception:
            # Exceptions can contain PII and may represent an unknown provider outcome.
            raise HTTPException(status_code=503, detail="Email fallback delivery failed.") from None
        if delivered is not True:
            raise HTTPException(status_code=503, detail="Email fallback delivery failed.")

        _invalidate_previous_challenges(session, user, challenge_id)
        activated = session.execute(
            update(EmailFallbackChallenge)
            .where(
                EmailFallbackChallenge.id == challenge_id,
                EmailFallbackChallenge.auth_user_id == user.id,
                EmailFallbackChallenge.auth_session_id == str(user.session_id),
                EmailFallbackChallenge.activated_at.is_(None),
                EmailFallbackChallenge.consumed_at.is_(None),
            )
            .values(activated_at=func.now())
            .returning(EmailFallbackChallenge.id)
        ).scalar_one_or_none()
        if activated is None:
            session.rollback()
            raise HTTPException(status_code=503, detail="Email fallback delivery failed.")
        session.commit()
    return ChallengeResponse(expires_in_seconds=int(CODE_TTL.total_seconds()))


@router.post("/verify", response_model=ProofResponse)
def verify_email_code(
    payload: EmailCodeRequest,
    user: Annotated[AuthenticatedUser, Depends(get_verified_user)],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProofResponse:
    _require_password_session(user)
    key = _key(settings)
    challenge = session.execute(
        select(EmailFallbackChallenge)
        .where(
            EmailFallbackChallenge.auth_user_id == user.id,
            EmailFallbackChallenge.auth_session_id == str(user.session_id),
            EmailFallbackChallenge.activated_at.is_not(None),
            EmailFallbackChallenge.consumed_at.is_(None),
            EmailFallbackChallenge.expires_at > func.now(),
        )
        .order_by(EmailFallbackChallenge.created_at.desc(), EmailFallbackChallenge.id.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    if challenge is None:
        raise HTTPException(status_code=400, detail="Email fallback code is invalid or expired.")
    if challenge.attempt_count >= MAX_CODE_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Email fallback attempt limit exceeded.")

    expected_hash = _code_hash(challenge.id, payload.code, key)
    if not hmac.compare_digest(challenge.code_hash, expected_hash):
        attempts = session.execute(
            update(EmailFallbackChallenge)
            .where(
                EmailFallbackChallenge.id == challenge.id,
                EmailFallbackChallenge.auth_user_id == user.id,
                EmailFallbackChallenge.auth_session_id == str(user.session_id),
                EmailFallbackChallenge.activated_at.is_not(None),
                EmailFallbackChallenge.consumed_at.is_(None),
                EmailFallbackChallenge.expires_at > func.now(),
                EmailFallbackChallenge.attempt_count < MAX_CODE_ATTEMPTS,
            )
            .values(attempt_count=EmailFallbackChallenge.attempt_count + 1)
            .returning(EmailFallbackChallenge.attempt_count)
        ).scalar_one_or_none()
        session.commit()
        if attempts is None or attempts >= MAX_CODE_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Email fallback attempt limit exceeded.")
        raise HTTPException(status_code=400, detail="Email fallback code is invalid or expired.")

    proof = secrets.token_urlsafe(32)
    proof_expires_at = _database_now(session) + PROOF_TTL
    consumed = session.execute(
        update(EmailFallbackChallenge)
        .where(
            EmailFallbackChallenge.id == challenge.id,
            EmailFallbackChallenge.auth_user_id == user.id,
            EmailFallbackChallenge.auth_session_id == str(user.session_id),
            EmailFallbackChallenge.activated_at.is_not(None),
            EmailFallbackChallenge.code_hash == expected_hash,
            EmailFallbackChallenge.consumed_at.is_(None),
            EmailFallbackChallenge.expires_at > func.now(),
            EmailFallbackChallenge.attempt_count < MAX_CODE_ATTEMPTS,
        )
        .values(
            consumed_at=func.now(),
            proof_hash=_proof_hash(proof, key),
            proof_expires_at=proof_expires_at,
            proof_consumed_at=None,
        )
        .returning(EmailFallbackChallenge.id)
    ).scalar_one_or_none()
    if consumed is None:
        session.rollback()
        raise HTTPException(status_code=400, detail="Email fallback code is invalid or expired.")
    session.commit()
    return ProofResponse(proof=proof, expires_in_seconds=int(PROOF_TTL.total_seconds()))
