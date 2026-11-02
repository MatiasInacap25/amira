"""Shared guard and engine for destructive PostgreSQL tests (they drop and recreate tables).

Only an explicit local TCP URL in AMIRA_TEST_DATABASE_URL may reach a database. Anything else is skipped before any
engine is created. DATABASE_URL is deliberately not used: it may point at a real project.
"""

import os

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

PUBLIC_SEARCH_TEST_DATABASE_ENV = "AMIRA_TEST_DATABASE_URL"
# Allowlist: the only URL hosts the destructive tests accept. Anything else is skipped, never connected to.
ALLOWED_TEST_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# Connection settings that can redirect libpq away from the URL host (URL query keys and environment variables).
REDIRECTING_QUERY_KEYS = ("host", "hostaddr", "service", "servicefile")
REDIRECTING_ENVIRONMENT_VARIABLES = ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")


def destructive_test_skip_reason(database_url: str) -> str | None:
    """Why the destructive test must not run against this URL, or None when it may run.

    Allowlist only: an explicit TCP host of exactly localhost, 127.0.0.1 or ::1, and no libpq setting that could
    redirect the connection (URL query keys or PG* environment variables). Nothing here opens a connection.
    """
    try:
        url = make_url(database_url)
    except ArgumentError:
        return "is not a parseable database URL"
    if url.host not in ALLOWED_TEST_DATABASE_HOSTS:
        return (
            "must name an explicit host of localhost, 127.0.0.1 or ::1 "
            f"(found {url.host or 'an empty host'!r}; unix sockets and host lists are not supported)"
        )
    for key in REDIRECTING_QUERY_KEYS:
        if key in url.query:
            return f"must not use the URL query parameter {key!r}"
    for name in REDIRECTING_ENVIRONMENT_VARIABLES:
        if name in os.environ:
            return f"must not be combined with the environment variable {name}"
    return None


def disposable_test_database_url() -> str:
    database_url = os.environ.get(PUBLIC_SEARCH_TEST_DATABASE_ENV, "").strip()
    if not database_url:
        pytest.skip(f"{PUBLIC_SEARCH_TEST_DATABASE_ENV} is not set; the PostgreSQL destructive test was skipped")
    reason = destructive_test_skip_reason(database_url)
    if reason is not None:
        pytest.skip(
            f"{PUBLIC_SEARCH_TEST_DATABASE_ENV} {reason}; refusing to drop and recreate tables "
            "(the PostgreSQL destructive test was skipped without connecting)"
        )
    return database_url


def disposable_test_engine(database_url: str) -> Engine:
    # Only called after disposable_test_database_url() has accepted an explicit localhost URL. A local Postgres
    # usually has no SSL, so this skips the forced sslmode=require that create_database_engine applies in production.
    return create_engine(make_url(database_url).set(drivername="postgresql+psycopg"))
