from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from amira_api.auth import AuthenticatedUser
from amira_api.invitation_routes import (
    INVALID_INVITATION,
    InvitationAccept,
    InvitationCreate,
    accept_invitation,
    create_invitation,
    get_email_confirmation_verifier,
    reissue_invitation,
    SupabaseEmailConfirmationVerifier,
)
from amira_api.models import Conductor, DriverInvitation
from amira_api.settings import Settings

AUTH_ID = UUID("2a45e1d3-243f-4f24-8a4b-37c33f404e97")
USER_ID = UUID("59f7cf6f-4d38-4c9c-96e7-62f354874d1d")
PROFILE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e32")
DRIVER_ROLE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e36")
DRIVER_TYPE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e37")
TOKEN = "a" * 43


class Result:
    def __init__(self, *, row=None, scalar=None):
        self.row = row
        self.scalar = scalar

    def one_or_none(self):
        return self.row

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar

    def scalars(self):
        return self

    def all(self):
        return self.scalar or []


class Session:
    def __init__(self, results, *, fail_commit=False):
        self.results = iter(results)
        self.added = []
        self.statements = []
        self.committed = False
        self.rolled_back = False
        self.fail_commit = fail_commit
        self.commits = 0

    def execute(self, statement):
        self.statements.append(statement)
        return next(self.results)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if isinstance(value, DriverInvitation) and value.id is None:
                value.id = uuid4()

    def commit(self):
        self.commits += 1
        if self.fail_commit and self.commits > 1:
            raise RuntimeError("database write failed")
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeSender:
    def __init__(self, delivered=True):
        self.delivered = delivered
        self.sent = []

    def send_invitation(self, email, link):
        self.sent.append((email, link))
        return self.delivered


class FakeEmailVerifier:
    def __init__(self, confirmed=True):
        self.confirmed = confirmed
        self.calls = []

    def is_confirmed(self, access_token, user_id, email):
        self.calls.append((access_token, user_id, email))
        return self.confirmed


def auth(email="driver@example.test"):
    return AuthenticatedUser(
        id=AUTH_ID,
        email=email,
        session_id=UUID("ecbe55b7-105f-44a1-b887-dfeef13c19d5"),
        assurance="aal2",
        authentication_methods=frozenset({"password", "phone"}),
    )


def acceptance_session(*, email="DRIVER@example.test", role="client", expires=None, accepted=None, fail_commit=False, independent=False):
    now = datetime.now(timezone.utc)
    invite = DriverInvitation(
        id=uuid4(), company_profile_id=PROFILE_ID, target_email="driver@example.test",
        token_hash=sha256(TOKEN.encode("ascii")).hexdigest(), created_by_user_id=uuid4(),
        created_at=now, expires_at=expires or now + timedelta(days=7), accepted_at=accepted,
    )
    profile = SimpleNamespace(
        id=PROFILE_ID,
        kind="independent_driver" if independent else "company",
        role_id=UUID("6633368a-3f77-4569-b203-57a1622d5852"),
        company_tax_id="76123456-0" if independent else None,
    )
    owner = SimpleNamespace(id=uuid4(), role_id=UUID("6633368a-3f77-4569-b203-57a1622d5853"))
    owner_driver = SimpleNamespace(id=uuid4(), user_id=owner.id, employer_profile_id=None)
    user = SimpleNamespace(id=USER_ID, email=email, role_id=UUID("6633368a-3f77-4569-b203-57a1622d5851"))
    driver_role = SimpleNamespace(id=DRIVER_ROLE_ID)
    driver_type = SimpleNamespace(id=DRIVER_TYPE_ID)
    results = [
        Result(), Result(), Result(scalar=0),
        Result(scalar=PROFILE_ID), Result(row=(profile, "independent_driver" if independent else "company", owner, "independent_driver" if independent else "company_owner")),
        Result(scalar=invite), Result(row=(user, role)),
        Result(scalar=None), Result(scalar=None), Result(scalar=driver_role), Result(scalar=driver_type),
    ]
    if independent:
        results.extend([Result(scalar=owner_driver), Result(scalar=SimpleNamespace(id=uuid4())), Result(scalar=SimpleNamespace(id=uuid4()))])
    return Session(results, fail_commit=fail_commit), invite, profile, user, owner, owner_driver


def test_invitation_creation_normalizes_email_and_persists_only_token_hash():
    owner = SimpleNamespace(id=USER_ID, role_id=DRIVER_ROLE_ID)
    profile = SimpleNamespace(id=PROFILE_ID, kind="company", role_id=DRIVER_ROLE_ID, company_tax_id=None)
    session = Session([Result(row=(owner, profile, "company_owner", "company")), Result(scalar=0), Result()])
    sender = FakeSender()

    result = create_invitation(
        InvitationCreate(email=" Driver@Example.Test "), auth("owner@example.test"), session,
        Settings(_env_file=None, frontend_base_url="https://amira.example"), sender,
    )

    invite = next(item for item in session.added if isinstance(item, DriverInvitation))
    email, link = sender.sent[0]
    token = link.split("#token=", 1)[1]
    assert email == invite.target_email == "driver@example.test"
    assert result.email == "driver@example.test"
    assert invite.expires_at - invite.created_at >= timedelta(days=7) if invite.created_at else invite.expires_at > datetime.now(timezone.utc)
    assert invite.token_hash == sha256(token.encode("ascii")).hexdigest()
    assert token not in invite.token_hash
    assert "?" not in link and "/" not in link.split("#", 1)[1]
    assert session.committed


def test_unconfigured_delivery_fails_before_writing_invitation():
    owner = SimpleNamespace(id=USER_ID, role_id=DRIVER_ROLE_ID)
    profile = SimpleNamespace(id=PROFILE_ID, kind="company", role_id=DRIVER_ROLE_ID, company_tax_id=None)
    session = Session([Result(row=(owner, profile, "company_owner", "company")), Result(scalar=0), Result()])
    sender = FakeSender(delivered=False)

    with pytest.raises(HTTPException) as error:
        create_invitation(
            InvitationCreate(email="driver@example.test"), auth("owner@example.test"), session,
            Settings(_env_file=None, frontend_base_url="https://amira.example"), sender,
        )

    assert error.value.status_code == 503
    assert not session.committed and session.rolled_back


def test_reissue_replaces_pending_token_and_revokes_old_invitation():
    owner = SimpleNamespace(id=USER_ID, role_id=DRIVER_ROLE_ID)
    profile = SimpleNamespace(id=PROFILE_ID, kind="company", role_id=DRIVER_ROLE_ID, company_tax_id=None)
    previous = DriverInvitation(
        id=uuid4(), company_profile_id=PROFILE_ID, target_email="driver@example.test",
        token_hash=sha256(b"older-token-value-which-is-long-enough").hexdigest(),
        created_by_user_id=USER_ID, created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    session = Session([
        Result(row=(owner, profile, "company_owner", "company")), Result(scalar=previous), Result(scalar=0), Result(),
    ])
    sender = FakeSender()

    result = reissue_invitation(
        previous.id, auth("owner@example.test"), session,
        Settings(_env_file=None, frontend_base_url="https://amira.example"), sender,
    )

    replacement = next(row for row in session.added if isinstance(row, DriverInvitation))
    assert previous.revoked_at is not None
    assert replacement.token_hash != previous.token_hash
    assert result.id == replacement.id
    assert sender.sent[0][0] == "driver@example.test"
    assert session.committed


def test_acceptance_consumes_invite_and_creates_one_company_driver_without_profile():
    session, invitation, profile, user, _, _ = acceptance_session()

    result = accept_invitation(
        InvitationAccept(token=TOKEN), auth(), session,
        Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID), "Bearer verified-session-token", FakeEmailVerifier(),
    )

    assert result.user_id == USER_ID and result.profile_id == PROFILE_ID
    assert user.role_id == DRIVER_ROLE_ID
    assert invitation.accepted_at is not None
    assert len([row for row in session.added if isinstance(row, Conductor)]) == 1
    assert not any(isinstance(row, SimpleNamespace) and row is profile for row in session.added)
    assert session.committed
    assert sum("FOR UPDATE" in str(statement.compile(dialect=__import__("sqlalchemy.dialects.postgresql", fromlist=["dialect"]).dialect())) for statement in session.statements) >= 4


def test_first_acceptance_atomically_converts_same_profile_and_reuses_owner_driver():
    session, invitation, profile, user, owner, owner_driver = acceptance_session(independent=True)
    company_role_id = UUID("6f87b410-07c0-4bdd-9458-bf34060810b1")
    company_owner_role_id = UUID("6f87b410-07c0-4bdd-9458-bf34060810b2")
    session.results = iter([
        Result(), Result(), Result(scalar=0),
        Result(scalar=PROFILE_ID), Result(row=(profile, "independent_driver", owner, "independent_driver")),
        Result(scalar=invitation), Result(row=(user, "client")), Result(scalar=None), Result(scalar=None),
        Result(scalar=SimpleNamespace(id=DRIVER_ROLE_ID)), Result(scalar=SimpleNamespace(id=DRIVER_TYPE_ID)),
        Result(scalar=owner_driver), Result(scalar=SimpleNamespace(id=company_role_id)),
        Result(scalar=SimpleNamespace(id=company_owner_role_id)),
    ])

    result = accept_invitation(
        InvitationAccept(token=TOKEN), auth(), session,
        Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID),
        "Bearer verified-session-token", FakeEmailVerifier(),
    )

    assert result.profile_id == profile.id
    assert profile.kind == "company" and profile.role_id == company_role_id
    assert profile.company_tax_id == "76123456-0"
    assert owner.role_id == company_owner_role_id
    assert owner_driver.employer_profile_id == profile.id
    assert user.role_id == DRIVER_ROLE_ID
    assert invitation.accepted_at is not None
    assert sum(isinstance(row, Conductor) for row in session.added) == 1
    assert session.commits == 2


def test_invite_issue_does_not_convert_independent_owner_before_acceptance():
    owner = SimpleNamespace(id=USER_ID, role_id="independent-role")
    profile = SimpleNamespace(id=PROFILE_ID, kind="independent_driver", role_id="independent-role", company_tax_id=None)
    session = Session([Result(row=(owner, profile, "independent_driver", "independent_driver")), Result(scalar=0), Result()])

    create_invitation(
        InvitationCreate(email="driver@example.test", company_tax_id="76.123.456-0"), auth("owner@example.test"), session,
        Settings(_env_file=None, frontend_base_url="https://amira.example"), FakeSender(),
    )

    assert profile.kind == "independent_driver"
    assert owner.role_id == "independent-role"
    assert profile.company_tax_id == "76123456-0"
    assert session.committed


@pytest.mark.parametrize("case", ["expired", "accepted", "wrong_email", "wrong_profile_email"])
def test_invalid_invitation_or_recipient_fails_closed(case):
    kwargs = {}
    identity_email = "driver@example.test"
    if case == "expired":
        kwargs["expires"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif case == "accepted":
        kwargs["accepted"] = datetime.now(timezone.utc)
    elif case == "wrong_email":
        identity_email = "other@example.test"
    elif case == "wrong_profile_email":
        kwargs["email"] = "other@example.test"
    independent = case == "expired"
    session, _, profile, _, owner, _ = acceptance_session(**kwargs, independent=independent)

    with pytest.raises(HTTPException) as error:
        accept_invitation(
            InvitationAccept(token=TOKEN), auth(identity_email), session,
            Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID), "Bearer verified-session-token", FakeEmailVerifier(),
        )

    assert error.value.status_code == 400
    assert error.value.detail == INVALID_INVITATION
    assert session.commits == 1
    if independent:
        assert profile.kind == "independent_driver"
        assert owner.role_id != DRIVER_ROLE_ID


def test_acceptance_rolls_back_role_and_invite_when_commit_fails():
    session, invitation, _, user, _, _ = acceptance_session(fail_commit=True)

    with pytest.raises(RuntimeError, match="database write failed"):
        accept_invitation(
            InvitationAccept(token=TOKEN), auth(), session,
            Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID), "Bearer verified-session-token", FakeEmailVerifier(),
        )

    assert user.role_id == DRIVER_ROLE_ID
    assert invitation.accepted_at is not None
    assert session.rolled_back
    assert session.commits == 2


def test_failed_first_acceptance_commit_rolls_back_transition_and_invitation():
    session, invitation, profile, user, owner, owner_driver = acceptance_session(independent=True, fail_commit=True)

    with pytest.raises(RuntimeError, match="database write failed"):
        accept_invitation(
            InvitationAccept(token=TOKEN), auth(), session,
            Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID),
            "Bearer verified-session-token", FakeEmailVerifier(),
        )

    assert profile.kind == "company"
    assert owner.role_id != UUID("6633368a-3f77-4569-b203-57a1622d5853")
    assert owner_driver.employer_profile_id == PROFILE_ID
    assert user.role_id == DRIVER_ROLE_ID
    assert invitation.accepted_at is not None
    assert session.rolled_back
    assert session.commits == 2


def test_acceptance_requires_independent_server_confirmation_evidence():
    session, _, _, _, _, _ = acceptance_session()

    with pytest.raises(HTTPException) as error:
        accept_invitation(
            InvitationAccept(token=TOKEN), auth(), session,
            Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID),
            "Bearer verified-session-token", FakeEmailVerifier(confirmed=False),
        )

    assert error.value.status_code == 403
    assert session.commits == 1
    assert len(session.statements) == 3


def test_email_confirmation_verifier_checks_auth_user_identity_and_confirmed_timestamp(monkeypatch):
    calls = []
    class Response:
        is_success = True
        def json(self):
            return {"id": str(AUTH_ID), "email": "Driver@Example.Test", "email_confirmed_at": "2026-10-01T12:00:00Z"}
    def fake_get(url, *, headers, timeout):
        calls.append((url, headers, timeout))
        return Response()
    monkeypatch.setattr("amira_api.invitation_routes.httpx.get", fake_get)
    verifier = SupabaseEmailConfirmationVerifier("https://project.example/auth/v1", "publishable-test-key")

    assert verifier.is_confirmed("verified-session-token", AUTH_ID, "driver@example.test")
    assert calls[0][0] == "https://project.example/auth/v1/user"
    assert calls[0][1] == {"apikey": "publishable-test-key", "Authorization": "Bearer verified-session-token"}
