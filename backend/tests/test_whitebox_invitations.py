"""Invitation adapter, management, and acceptance rejection branches without network."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amira_api import invitation_routes as routes
from amira_api.settings import Settings
from test_company_invitations import (
    DRIVER_TYPE_ID, TOKEN, FakeEmailVerifier, FakeSender, Result, Session, acceptance_session, auth,
)


NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_invitation_clock(monkeypatch):
    import test_company_invitations

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(routes, "datetime", FixedDatetime)
    monkeypatch.setattr(test_company_invitations, "datetime", FixedDatetime)


@pytest.mark.parametrize("configured", [False, True])
def test_invitation_adapter_factories(configured):
    settings = Settings(resend_api_key="test-key", invitation_sender_email="sender@example.test",
        frontend_base_url="https://frontend.test", supabase_jwt_issuer="https://auth.test/auth/v1",
        supabase_publishable_key="test-key") if configured else Settings()
    sender = routes.get_invitation_sender(settings)
    verifier = routes.get_email_confirmation_verifier(settings)
    assert isinstance(sender, routes.ResendInvitationSender) if configured else sender is None
    assert isinstance(verifier, routes.SupabaseEmailConfirmationVerifier) if configured else verifier is None


@pytest.mark.parametrize("outcome", ["success", "reject", "exception"])
def test_invitation_sender_transport_contract(monkeypatch, outcome):
    post = Mock(side_effect=httpx.ConnectError("offline")) if outcome == "exception" else Mock(return_value=NS(is_success=outcome == "success"))
    monkeypatch.setattr(routes.httpx, "post", post)
    assert routes.ResendInvitationSender("key", "sender@example.test").send_invitation("driver@example.test", "https://frontend.test/#token=x") is (outcome == "success")
    assert post.call_args.kwargs["timeout"] == 5.0
    assert post.call_args.kwargs["json"]["to"] == ["driver@example.test"]


@pytest.mark.parametrize("data", [[], {}, {"id": "wrong"}, {"id": "correct", "email": 1}, {"id": "correct", "email": "other@example.test"}, {"id": "correct", "email": "driver@example.test"}, "failure", "exception"])
def test_confirmation_verifier_rejects_untrusted_provider_responses(monkeypatch, data):
    identifier = uuid4()
    if isinstance(data, dict) and data.get("id") == "correct":
        data = {**data, "id": str(identifier)}
    get = Mock(side_effect=httpx.ConnectError("offline")) if data == "exception" else Mock(return_value=NS(is_success=data != "failure", json=lambda: data))
    monkeypatch.setattr(routes.httpx, "get", get)
    assert not routes.SupabaseEmailConfirmationVerifier("https://auth.test", "key").is_confirmed("token", identifier, "driver@example.test")
    assert get.call_args.kwargs["timeout"] == 3.0


@pytest.mark.parametrize("email", ["@example.test", "driver@.test", "driver@example."])
def test_invitation_email_rejects_empty_local_or_invalid_domain(email):
    with pytest.raises(ValidationError):
        routes.InvitationCreate(email=email)


def managed_session(invitation=None):
    owner = NS(id=uuid4())
    profile = NS(id=uuid4(), kind="company")
    session = Session([Result(row=(owner, profile, "company_owner", "company")), Result(scalar=invitation)])
    return session, owner, profile


@pytest.mark.parametrize("state", ["pending", "accepted", "revoked", "expired"])
def test_list_invitations_exposes_each_lifecycle_state(state):
    now = NOW
    invitation = NS(id=uuid4(), target_email="driver@example.test", created_at=now,
        expires_at=now + timedelta(days=-1 if state == "expired" else 1),
        accepted_at=now if state == "accepted" else None, revoked_at=now if state == "revoked" else None)
    session, _, _ = managed_session([invitation])
    result = routes.list_invitations(auth(), session)
    assert result.invitations[0].status == state
    assert result.invitations[0].email == invitation.target_email
    assert not session.committed


@pytest.mark.parametrize("operation", ["revoke", "reissue"])
@pytest.mark.parametrize("state", ["missing", "accepted", "pending"])
def test_invitation_management_guards_and_success(operation, state):
    now = NOW
    invitation = None if state == "missing" else NS(id=uuid4(), target_email="driver@example.test", expires_at=now + timedelta(days=1),
        accepted_at=now if state == "accepted" else None, revoked_at=None)
    session, _, _ = managed_session(invitation)
    if operation == "reissue" and state == "pending":
        session.results = iter([*session.results, Result(scalar=0), Result()])
    call = lambda: routes.revoke_invitation(uuid4(), auth(), session) if operation == "revoke" else routes.reissue_invitation(uuid4(), auth(), session, Settings(frontend_base_url="https://frontend.test"), FakeSender())
    if state != "pending":
        with pytest.raises(HTTPException) as caught:
            call()
        assert caught.value.status_code == (404 if state == "missing" else 409)
        assert not session.committed
    else:
        assert call().email == invitation.target_email
        assert invitation.revoked_at is not None and session.committed


@pytest.mark.parametrize("slot", [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
def test_acceptance_refuses_missing_or_preexisting_dependencies(slot):
    session, invitation, profile, user, owner, driver = acceptance_session(independent=True)
    results = list(session.results)
    if slot in {7, 8}:
        results[slot] = Result(scalar=uuid4())
    elif slot in {4, 6}:
        results[slot] = Result(row=None)
    else:
        results[slot] = Result(scalar=None)
    session.results = iter(results)
    with pytest.raises(HTTPException) as caught:
        routes.accept_invitation(routes.InvitationAccept(token=TOKEN), auth(), session,
            Settings(company_driver_type_id=DRIVER_TYPE_ID), "Bearer token", FakeEmailVerifier())
    assert caught.value.status_code == (503 if slot in {9, 10, 12, 13} else 400)
    assert session.commits == 1
    assert len(session.added) == 1  # Only the abuse-attempt record is committed.
    assert invitation.accepted_at is None and user.role_id != DRIVER_TYPE_ID


@pytest.mark.parametrize("change", ["profile-role", "owner-role", "tax-id", "owner-employer"])
def test_acceptance_checks_company_conversion_invariants(change):
    session, invitation, profile, user, owner, driver = acceptance_session(independent=True)
    results = list(session.results)
    if change == "profile-role":
        row = list(results[4].row); row[1] = "company"; results[4] = Result(row=tuple(row))
    elif change == "owner-role":
        row = list(results[4].row); row[3] = "client"; results[4] = Result(row=tuple(row))
    elif change == "tax-id":
        profile.company_tax_id = None
    else:
        driver.employer_profile_id = uuid4()
    session.results = iter(results)
    with pytest.raises(HTTPException) as caught:
        routes.accept_invitation(routes.InvitationAccept(token=TOKEN), auth(), session,
            Settings(company_driver_type_id=DRIVER_TYPE_ID), "Bearer token", FakeEmailVerifier())
    assert caught.value.status_code == 400 and invitation.accepted_at is None


@pytest.mark.parametrize("base", ["ftp://frontend.test", "https://user:pass@frontend.test", "https://frontend.test?x=1", "https://frontend.test/#fragment"])
def test_invitation_rejects_invalid_delivery_base_before_send(base):
    session, _, _ = managed_session()
    sender = FakeSender()
    with pytest.raises(HTTPException) as caught:
        routes.create_invitation(routes.InvitationCreate(email="driver@example.test"), auth(), session, Settings(frontend_base_url=base), sender)
    assert caught.value.status_code == 503
    assert not sender.sent and not session.committed


def test_invitation_issue_rate_limit_blocks_delivery():
    session, _, _ = managed_session(5)
    sender = FakeSender()
    with pytest.raises(HTTPException) as caught:
        routes.create_invitation(routes.InvitationCreate(email="driver@example.test"), auth(), session, Settings(frontend_base_url="https://frontend.test"), sender)
    assert caught.value.status_code == 429 and not sender.sent


def test_invitation_sender_exception_rolls_back_without_private_detail():
    session, _, _ = managed_session(0)
    session.results = iter([*session.results, Result()])
    sender = Mock()
    sender.send_invitation.side_effect = RuntimeError("private transport detail")
    with pytest.raises(HTTPException) as caught:
        routes.create_invitation(routes.InvitationCreate(email="driver@example.test"), auth(), session, Settings(frontend_base_url="https://frontend.test"), sender)
    assert caught.value.status_code == 503 and session.rolled_back
    assert "private" not in caught.value.detail


@pytest.mark.parametrize("tax_id, existing, status", [(None, None, 422), ("76123456-0", "different", 409), ("76123456-0", None, 201)])
def test_independent_first_invitation_requires_stable_company_tax_id(tax_id, existing, status):
    profile = NS(id=uuid4(), kind="independent_driver", company_tax_id=existing)
    owner = NS(id=uuid4())
    session = Session([Result(row=(owner, profile, "independent_driver", "independent_driver")), Result(scalar=0), Result()])
    payload = routes.InvitationCreate(email="driver@example.test", company_tax_id=tax_id)
    if status == 201:
        assert routes.create_invitation(payload, auth(), session, Settings(frontend_base_url="https://frontend.test"), FakeSender()).email == "driver@example.test"
        assert profile.company_tax_id == tax_id and session.committed
    else:
        with pytest.raises(HTTPException) as caught:
            routes.create_invitation(payload, auth(), session, Settings(frontend_base_url="https://frontend.test"), FakeSender())
        assert caught.value.status_code == status and not session.committed


@pytest.mark.parametrize("authorization, configured, status", [(None, True, 401), ("Bearer token", False, 503), ("Bearer ", True, 403)])
def test_acceptance_authentication_and_mapping_guards(authorization, configured, status):
    session, *_ = acceptance_session()
    config = Settings(company_driver_type_id=DRIVER_TYPE_ID) if configured else Settings()
    with pytest.raises(HTTPException) as caught:
        routes.accept_invitation(routes.InvitationAccept(token=TOKEN), auth(), session, config, authorization, FakeEmailVerifier())
    assert caught.value.status_code == status
