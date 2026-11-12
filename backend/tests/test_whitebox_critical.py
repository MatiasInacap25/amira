"""White-box error boundaries of public authentication and infrastructure functions."""

from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy.pool import NullPool

from amira_api import auth, db, release_payouts
from amira_api.settings import Settings
from amira_api.shared_trip_service import SharedTripConflict, link_join_request_stops, publish_shared_trip
from amira_api.simulated_payment_provider import SimulatedPaymentProvider
from test_auth import FakeJwkClient, ISSUER, PRIVATE_KEY, make_token

NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("authorization", [None, "Basic secret", "Bearer "])
def test_verified_user_rejects_missing_bearer(authorization):
    with pytest.raises(HTTPException) as caught:
        auth.get_verified_user(Settings(supabase_jwt_issuer=ISSUER), authorization)
    assert caught.value.status_code == 401
    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}


def test_verified_user_requires_configuration():
    with pytest.raises(HTTPException) as caught:
        auth.get_verified_user(Settings(), "Bearer token")
    assert caught.value.status_code == 503


@pytest.mark.parametrize("claims", [{"email": " "}, {"role": "anon"}, {"is_anonymous": True}, {"aal": "aal3"}, {"amr": "password"}])
def test_verified_user_rejects_invalid_claim_shapes(monkeypatch, claims):
    monkeypatch.setattr(auth, "_jwks_client", lambda url: FakeJwkClient())
    with pytest.raises(HTTPException) as caught:
        auth.get_verified_user(Settings(supabase_jwt_issuer=ISSUER), f"Bearer {make_token(**claims)}")
    assert caught.value.status_code == 401


@pytest.mark.parametrize("failure", [jwt.PyJWKClientError("missing kid"), OSError("JWKS offline")])
def test_verified_user_fails_closed_on_jwks_failure(monkeypatch, failure):
    client = Mock()
    client.get_signing_key_from_jwt.side_effect = failure
    monkeypatch.setattr(auth, "_jwks_client", lambda url: client)
    with pytest.raises(HTTPException) as caught:
        auth.get_verified_user(Settings(supabase_jwt_issuer=ISSUER), "Bearer token")
    assert caught.value.status_code == 401
    assert "offline" not in caught.value.detail


@pytest.mark.parametrize("claims", [{"sub": "bad"}, {"sub": str(uuid4()), "session_id": "bad"}, {"sub": str(uuid4()), "session_id": str(uuid4())}])
def test_fallback_proof_invalid_identity_or_unconsumed_proof(claims):
    session = Mock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    value = auth.verify_email_fallback_proof(
        {"aal": "aal1", "amr": [{"method": "password"}], **claims}, "proof", session,
        Settings(email_fallback_secret="x" * 32),
    )
    assert value is False
    session.commit.assert_not_called()


def test_fallback_proof_rejects_unicode_without_database_access():
    session = Mock()
    assert not auth.verify_email_fallback_proof(
        {"aal": "aal1", "amr": [{"method": "password"}]}, "ñ", session,
        Settings(email_fallback_secret="x" * 32),
    )
    session.execute.assert_not_called()


@pytest.mark.parametrize("url", ["postgres://user:pass@db/test?sslmode=disable", "postgresql://db/test", "postgresql+psycopg://db/test"])
@pytest.mark.parametrize("pool", [False, True])
def test_database_engine_enforces_tls_and_bounded_options(monkeypatch, url, pool):
    create = Mock(return_value=object())
    monkeypatch.setattr(db, "create_engine", create)
    extra = {"poolclass": NullPool} if pool else {}
    assert db.create_database_engine(url, **extra) is create.return_value
    args, options = create.call_args
    assert args[0].drivername == "postgresql+psycopg"
    assert args[0].query["sslmode"] == "require"
    assert options["connect_args"] == {"sslmode": "require", "connect_timeout": 10, "options": "-c statement_timeout=5000"}
    if pool:
        assert options["poolclass"] is NullPool
        assert "pool_size" not in options
    else:
        assert {key: options[key] for key in ("pool_size", "max_overflow", "pool_timeout", "pool_recycle")} == {
            "pool_size": 5, "max_overflow": 5, "pool_timeout": 10, "pool_recycle": 1800,
        }


def test_database_rejects_non_postgres_before_engine_creation(monkeypatch):
    create = Mock()
    monkeypatch.setattr(db, "create_engine", create)
    with pytest.raises(ValueError, match="PostgreSQL"):
        db.create_database_engine("sqlite://")
    create.assert_not_called()


def test_engine_configuration_and_cache(monkeypatch):
    db.get_engine.cache_clear()
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(database_url=None))
    with pytest.raises(RuntimeError, match="not configured"):
        db.get_engine()
    create = Mock(return_value=object())
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(database_url="postgresql://db/test"))
    monkeypatch.setattr(db, "create_database_engine", create)
    try:
        assert db.get_engine() is db.get_engine()
        create.assert_called_once_with("postgresql://db/test")
    finally:
        db.get_engine.cache_clear()


@pytest.mark.parametrize("failure", [RuntimeError("missing"), ValueError("invalid")])
def test_session_configuration_failure_becomes_service_unavailable(monkeypatch, failure):
    monkeypatch.setattr(db, "get_engine", Mock(side_effect=failure))
    with pytest.raises(HTTPException) as caught:
        next(db.get_db_session())
    assert caught.value.status_code == 503
    assert caught.value.detail == "Database is not configured."


def test_session_generator_closes_context(monkeypatch):
    engine, session = object(), object()
    factory = Mock(return_value=nullcontext(session))
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    monkeypatch.setattr(db, "Session", factory)
    iterator = db.get_db_session()
    assert next(iterator) is session
    with pytest.raises(StopIteration):
        next(iterator)
    factory.assert_called_once_with(engine)


def test_payout_provider_requires_explicit_environment():
    with pytest.raises(RuntimeError, match="explicitly"):
        release_payouts.build_payout_provider(Settings())


def test_release_cli_refuses_missing_database(monkeypatch, caplog):
    monkeypatch.setattr(release_payouts, "get_settings", lambda: Settings(app_env="test"))
    monkeypatch.setattr(release_payouts, "get_engine", Mock(side_effect=RuntimeError("not configured")))
    assert release_payouts.main() == 1
    assert "cannot run" in caplog.text


def test_release_cli_success_logs_summary(monkeypatch, caplog):
    from amira_api.payout_service import PayoutSummary
    session, engine = object(), object()
    release = Mock(return_value=PayoutSummary(due=1, released=1))
    monkeypatch.setattr(release_payouts, "get_settings", lambda: Settings(app_env="test"))
    monkeypatch.setattr(release_payouts, "get_engine", lambda: engine)
    monkeypatch.setattr(release_payouts, "Session", lambda value: nullcontext(session))
    monkeypatch.setattr(release_payouts, "release_due_payouts", release)
    monkeypatch.setattr(release_payouts, "utc_now", lambda: NOW)
    with caplog.at_level("INFO"):
        assert release_payouts.main() == 0
    assert "finished" in caplog.text
    assert release.call_args.args[:2] == (session, NOW)


def test_simulator_refuses_empty_secret():
    with pytest.raises(RuntimeError, match="signing secret"):
        SimulatedPaymentProvider(secret="", frontend_base_url="http://frontend.test", app_env="test")


@pytest.mark.parametrize("stage, message", [(0, "no aceptó"), (1, "no está disponible"), (2, "no tiene vehículo"), (3, "no tiene paradas")])
def test_join_stop_guards_do_not_write(stage, message):
    session = Mock()
    trip = SimpleNamespace(id=uuid4())
    results = [None] if stage == 1 else [trip, None] if stage == 2 else [trip, SimpleNamespace(vehicle_id=uuid4())]
    session.execute.side_effect = [SimpleNamespace(scalar_one_or_none=lambda value=value: value) for value in results]
    if stage == 3:
        session.execute.side_effect = [*session.execute.side_effect, SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))]
    with pytest.raises(SharedTripConflict, match=message):
        link_join_request_stops(session, trip_id=uuid4(), pickup_address="A", delivery_address="B", is_exclusive=stage == 0)
    session.add_all.assert_not_called()
    session.commit.assert_not_called()


def test_publish_trip_requires_addresses_before_writes():
    session = Mock()
    service = SimpleNamespace(is_exclusive=False, trip_id=None, form=SimpleNamespace(requested_at=NOW, origin="", destination="B"))
    with pytest.raises(SharedTripConflict, match="origen y destino"):
        publish_shared_trip(session, service=service, vehicle=object(), driver=object(), now=NOW)
    session.add.assert_not_called()


def test_payout_job_counts_a_service_that_disappears_under_lock(monkeypatch):
    from amira_api import payout_service
    session = Mock()
    identifier = uuid4()
    monkeypatch.setattr(payout_service, "_due_service_ids", lambda session, now: [identifier])
    session.execute.return_value.scalar_one_or_none.return_value = None
    summary = payout_service.release_due_payouts(session, NOW, object(), commission_percent=10)
    assert (summary.due, summary.skipped, summary.released, summary.failed) == (1, 1, 0, 0)
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


@pytest.mark.xfail(strict=True, reason="BUG: connect_args overrides mandatory TLS in create_database_engine")
def test_database_tls_cannot_be_disabled_by_engine_options(monkeypatch):
    create = Mock()
    monkeypatch.setattr(db, "create_engine", create)
    db.create_database_engine("postgresql://db/test", connect_args={"sslmode": "disable"})
    assert create.call_args.kwargs["connect_args"]["sslmode"] == "require"


@pytest.mark.parametrize("secret, subject, session_id", [("short", str(uuid4()), str(uuid4())), ("x" * 32, str(uuid4()), str(__import__('uuid').UUID(int=0)))])
def test_fallback_proof_rejects_short_keys_and_nil_sessions(secret, subject, session_id):
    session = Mock()
    assert not auth.verify_email_fallback_proof(
        {"aal": "aal1", "amr": [{"method": "password"}], "sub": subject, "session_id": session_id},
        "proof", session, Settings(email_fallback_secret=secret),
    )
    session.execute.assert_not_called()


def test_payment_composition_root_constructs_configured_adapter():
    from amira_api.payment_routes import get_payment_provider
    provider = get_payment_provider(Settings(app_env="test", payment_simulator_secret="secret", frontend_base_url="http://frontend.test"))
    assert isinstance(provider, SimulatedPaymentProvider)
    assert provider.name == "simulated"
