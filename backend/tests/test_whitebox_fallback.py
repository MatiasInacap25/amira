"""Fallback delivery and atomic-update failure branches with bounded local fakes."""

from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from amira_api import fallback_routes as routes
from test_email_fallback import TEST_SECRET, settings, user

NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)


def session_with_results(values, *, postgres=False):
    session = Mock()
    session.get_bind.return_value.dialect.name = "postgresql" if postgres else "sqlite"
    session.execute.side_effect = [NS(scalar_one=lambda value=value: value, scalar_one_or_none=lambda value=value: value) for value in values]
    return session


def test_fallback_sender_is_explicitly_unconfigured():
    assert routes.get_email_fallback_sender() is None


@pytest.mark.parametrize("postgres", [False, True])
@pytest.mark.parametrize("delivery", ["exception", "activation-missing", "success"])
def test_issue_releases_lock_and_handles_delivery_activation(monkeypatch, postgres, delivery):
    session = session_with_results([NOW.isoformat(), 0, None, None, None if delivery == "activation-missing" else uuid4()], postgres=postgres)
    connection = Mock()
    session.get_bind.return_value.connect.return_value = nullcontext(connection)
    sender = Mock()
    sender.send_code.return_value = True
    if delivery == "exception":
        sender.send_code.side_effect = RuntimeError("private provider detail")
    if delivery == "success":
        assert routes.issue_email_code(user(), session, settings(), sender).expires_in_seconds == 600
        assert session.commit.call_count == 2
    else:
        with pytest.raises(HTTPException) as caught:
            routes.issue_email_code(user(), session, settings(), sender)
        assert caught.value.status_code == 503
        assert "private" not in caught.value.detail
        assert session.commit.call_count == 1
        assert session.rollback.call_count == int(delivery == "activation-missing")
    if postgres:
        assert connection.execute.call_count == 2 and connection.commit.call_count == 2
        assert "pg_advisory_unlock" in str(connection.execute.call_args.args[0])


@pytest.mark.parametrize("attempts", [None, 5])
def test_wrong_code_atomic_update_exhaustion(attempts):
    challenge = NS(id=uuid4(), attempt_count=0, code_hash="wrong")
    session = session_with_results([challenge, attempts])
    with pytest.raises(HTTPException) as caught:
        routes.verify_email_code(routes.EmailCodeRequest(code="123456"), user(), session, settings())
    assert caught.value.status_code == 429
    session.commit.assert_called_once()


def test_correct_code_lost_atomic_consume_rolls_back():
    import hashlib, hmac
    identifier = uuid4()
    code_hash = hmac.new(TEST_SECRET.encode(), b"email-code:" + identifier.bytes + b":123456", hashlib.sha256).hexdigest()
    challenge = NS(id=identifier, attempt_count=0, code_hash=code_hash)
    session = session_with_results([challenge, NOW, None])
    with pytest.raises(HTTPException) as caught:
        routes.verify_email_code(routes.EmailCodeRequest(code="123456"), user(), session, settings())
    assert caught.value.status_code == 400
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
