from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user, verify_email_fallback_proof
from amira_api.fallback_routes import (
    CODE_TTL,
    MAX_CHALLENGES_PER_WINDOW,
    MAX_CODE_ATTEMPTS,
    ChallengeResponse,
    EmailCodeRequest,
    ProofResponse,
    issue_email_code,
    verify_email_code,
)
from amira_api.models import Base, EmailFallbackChallenge
from amira_api.settings import Settings


AUTH_USER_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
SESSION_ID = UUID("123e4567-e89b-12d3-a456-426614174001")
EMAIL = "person@example.test"
TEST_SECRET = "local-test-fallback-pepper-should-never-ship-000000000000"


class FakeSender:
    def __init__(self):
        self.sent = []

    def send_code(self, email, code):
        self.sent.append((email, code))
        return True


class FailingSender(FakeSender):
    def send_code(self, email, code):
        self.sent.append((email, code))
        return False


class InspectingSender(FakeSender):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.challenge_activation_states = []

    def send_code(self, email, code):
        self.sent.append((email, code))
        challenges = self.session.query(EmailFallbackChallenge).order_by(EmailFallbackChallenge.created_at).all()
        self.challenge_activation_states.append([item.activated_at for item in challenges])
        return True


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.create_function(
            "btrim", 1, lambda value: value.strip() if value else value, deterministic=True
        ),
    )
    Base.metadata.create_all(engine, tables=[Base.metadata.tables["Usuario"], EmailFallbackChallenge.__table__])
    with Session(engine) as db:
        yield db
    engine.dispose()


def settings(secret: str | None = TEST_SECRET) -> Settings:
    return Settings(_env_file=None, email_fallback_secret=SecretStr(secret) if secret is not None else None)


def user(*, user_id=AUTH_USER_ID, session_id=SESSION_ID, email=EMAIL, methods=frozenset({"password"}), assurance="aal1"):
    return AuthenticatedUser(
        id=user_id,
        email=email,
        session_id=session_id,
        assurance=assurance,
        authentication_methods=methods,
    )


def issue(session, sender, identity=None, config=None):
    return issue_email_code(
        identity or user(),
        session,
        config or settings(),
        sender,
    )


def verify(session, code, identity=None, config=None):
    return verify_email_code(
        EmailCodeRequest(code=code),
        identity or user(),
        session,
        config or settings(),
    )


def test_issue_and_verify_returns_short_lived_separate_proof(session):
    sender = FakeSender()

    issued = issue(session, sender)
    proof = verify(session, sender.sent[-1][1])

    challenge = session.query(EmailFallbackChallenge).one()
    assert isinstance(issued, ChallengeResponse)
    assert issued.expires_in_seconds == int(CODE_TTL.total_seconds())
    assert sender.sent[0][0] == EMAIL
    assert len(sender.sent[0][1]) == 6
    assert challenge.code_hash != sender.sent[0][1]
    assert len(challenge.code_hash) == 64
    assert challenge.proof_hash is not None and len(challenge.proof_hash) == 64
    assert challenge.proof_hash != proof.proof
    assert challenge.consumed_at is not None
    assert challenge.proof_expires_at is not None
    assert challenge.proof_consumed_at is None
    assert proof.assurance == "email_fallback"
    assert proof.assurance != "aal2"


def test_proof_is_same_user_session_bound_short_lived_and_single_use(session):
    sender = FakeSender()
    issue(session, sender)
    proof = verify(session, sender.sent[-1][1]).proof
    claims = {"sub": str(AUTH_USER_ID), "session_id": str(SESSION_ID), "aal": "aal1", "amr": [{"method": "password"}]}
    config = settings()

    assert not verify_email_fallback_proof({**claims, "sub": str(uuid4())}, proof, session, config)
    assert not verify_email_fallback_proof({**claims, "session_id": str(uuid4())}, proof, session, config)
    assert not verify_email_fallback_proof({**claims, "aal": "aal2"}, proof, session, config)
    assert not verify_email_fallback_proof({**claims, "amr": [{"method": "oauth"}]}, proof, session, config)
    assert not verify_email_fallback_proof(claims, proof + "é", session, config)
    assert verify_email_fallback_proof(claims, proof, session, config)
    assert not verify_email_fallback_proof(claims, proof, session, config)


def test_new_challenge_invalidates_previous_code_and_unspent_proof(session):
    sender = FakeSender()
    issue(session, sender)
    old_code = sender.sent[-1][1]
    old_proof = verify(session, old_code).proof

    issue(session, sender)
    new_code = sender.sent[-1][1]
    with pytest.raises(HTTPException) as old_code_error:
        verify(session, old_code)
    assert old_code_error.value.status_code == 400
    claims = {"sub": str(AUTH_USER_ID), "session_id": str(SESSION_ID), "aal": "aal1", "amr": [{"method": "password"}]}
    assert not verify_email_fallback_proof(claims, old_proof, session, settings())
    assert isinstance(verify(session, new_code), ProofResponse)


def test_failed_replacement_delivery_preserves_previous_proof(session):
    sender = FakeSender()
    issue(session, sender)
    old_proof = verify(session, sender.sent[-1][1]).proof
    claims = {"sub": str(AUTH_USER_ID), "session_id": str(SESSION_ID), "aal": "aal1", "amr": [{"method": "password"}]}

    with pytest.raises(HTTPException) as failed:
        issue(session, FailingSender())

    assert failed.value.status_code == 503
    assert verify_email_fallback_proof(claims, old_proof, session, settings())


def test_failed_replacement_code_is_inactive_and_old_code_remains_usable(session):
    sender = FakeSender()
    issue(session, sender)
    old_code = sender.sent[-1][1]
    failed_sender = FailingSender()

    with pytest.raises(HTTPException):
        issue(session, failed_sender)

    with pytest.raises(HTTPException) as replacement:
        verify(session, failed_sender.sent[-1][1])
    assert replacement.value.status_code == 400
    assert isinstance(verify(session, old_code), ProofResponse)


def test_failed_sends_consume_bounded_issue_budget(session):
    sender = FailingSender()
    for _ in range(MAX_CHALLENGES_PER_WINDOW):
        with pytest.raises(HTTPException) as failed:
            issue(session, sender)
        assert failed.value.status_code == 503

    with pytest.raises(HTTPException) as limited:
        issue(session, sender)
    assert limited.value.status_code == 429
    assert len(sender.sent) == MAX_CHALLENGES_PER_WINDOW


def test_replacement_is_pending_during_send_then_activates_after_confirmation(session):
    sender = FakeSender()
    issue(session, sender)
    old_code = sender.sent[-1][1]
    old_proof = verify(session, old_code).proof
    claims = {"sub": str(AUTH_USER_ID), "session_id": str(SESSION_ID), "aal": "aal1", "amr": [{"method": "password"}]}
    sender = InspectingSender(session)

    issue(session, sender)

    assert len(sender.challenge_activation_states) == 1
    assert sender.challenge_activation_states[0][0] is not None
    assert sender.challenge_activation_states[0][1] is None
    challenges = session.query(EmailFallbackChallenge).order_by(EmailFallbackChallenge.created_at).all()
    assert all(item.activated_at is not None for item in challenges)
    assert not verify_email_fallback_proof(claims, old_proof, session, settings())


def test_expired_proof_and_unconfigured_verifier_fail_closed(session):
    sender = FakeSender()
    issue(session, sender)
    proof = verify(session, sender.sent[-1][1]).proof
    challenge = session.query(EmailFallbackChallenge).one()
    challenge.proof_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    claims = {"sub": str(AUTH_USER_ID), "session_id": str(SESSION_ID), "aal": "aal1", "amr": [{"method": "password"}]}

    assert not verify_email_fallback_proof(claims, proof, session, settings())
    assert not verify_email_fallback_proof(claims, "proof", session, settings(None))


def test_auth_boundary_accepts_aal1_only_with_consumable_server_proof(session):
    sender = FakeSender()
    issue(session, sender)
    proof = verify(session, sender.sent[-1][1]).proof
    identity = user()

    accepted = get_current_user(identity, settings(), session, proof)
    assert accepted.assurance == "email_fallback"
    assert accepted.assurance != "aal2"
    with pytest.raises(HTTPException) as replay:
        get_current_user(identity, settings(), session, proof)
    assert replay.value.status_code == 403


def test_wrong_user_or_session_code_cannot_consume_challenge(session):
    sender = FakeSender()
    issue(session, sender)
    code = sender.sent[-1][1]

    for identity in (user(user_id=uuid4()), user(session_id=uuid4())):
        with pytest.raises(HTTPException) as error:
            verify(session, code, identity=identity)
        assert error.value.status_code == 400

    assert isinstance(verify(session, code), ProofResponse)


def test_expired_and_replayed_codes_are_rejected(session):
    sender = FakeSender()
    issue(session, sender)
    challenge = session.query(EmailFallbackChallenge).one()
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    with pytest.raises(HTTPException) as expired:
        verify(session, sender.sent[-1][1])
    assert expired.value.status_code == 400

    # A separately issued code can be consumed once and cannot be replayed.
    issue(session, sender)
    code = sender.sent[-1][1]
    verify(session, code)
    with pytest.raises(HTTPException) as replay:
        verify(session, code)
    assert replay.value.status_code == 400


def test_wrong_code_attempts_are_persisted_and_limited(session):
    sender = FakeSender()
    issue(session, sender)
    wrong_code = f"{(int(sender.sent[-1][1]) + 1) % 1_000_000:06d}"

    for attempt in range(MAX_CODE_ATTEMPTS):
        with pytest.raises(HTTPException) as error:
            verify(session, wrong_code)
        assert error.value.status_code == (429 if attempt == MAX_CODE_ATTEMPTS - 1 else 400)

    challenge = session.query(EmailFallbackChallenge).one()
    assert challenge.attempt_count == MAX_CODE_ATTEMPTS
    with pytest.raises(HTTPException) as locked:
        verify(session, sender.sent[-1][1])
    assert locked.value.status_code == 429


def test_challenge_issue_rate_is_limited_across_sessions_for_user(session):
    sender = FakeSender()
    for index in range(MAX_CHALLENGES_PER_WINDOW):
        issue(session, sender, identity=user(session_id=SESSION_ID if index % 2 == 0 else uuid4()))

    with pytest.raises(HTTPException) as limited:
        issue(session, sender, identity=user(session_id=uuid4()))
    assert limited.value.status_code == 429
    assert len(sender.sent) == MAX_CHALLENGES_PER_WINDOW


def test_missing_secret_or_sender_fails_closed(session):
    sender = FakeSender()
    with pytest.raises(HTTPException) as no_secret:
        issue(session, sender, config=settings(None))
    assert no_secret.value.status_code == 503
    with pytest.raises(HTTPException) as short_secret:
        issue(session, sender, config=settings("short"))
    assert short_secret.value.status_code == 503
    with pytest.raises(HTTPException) as no_sender:
        issue(session, None)
    assert no_sender.value.status_code == 503
    assert session.query(EmailFallbackChallenge).count() == 0


def test_challenge_requires_signed_in_password_aal1(session):
    sender = FakeSender()
    for identity in (
        user(assurance="aal2"),
        user(methods=frozenset({"oauth"})),
        user(methods=frozenset({"token_refresh"})),
    ):
        with pytest.raises(HTTPException) as rejected:
            issue(session, sender, identity=identity)
        assert rejected.value.status_code == 403
    assert not sender.sent
