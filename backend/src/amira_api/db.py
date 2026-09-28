"""Database engine and session configuration for the API and Alembic."""

from collections.abc import Generator
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from amira_api.settings import get_settings


def create_database_engine(database_url: str, **engine_options) -> Engine:
    """Create a bounded psycopg engine that requires TLS for PostgreSQL."""
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use PostgreSQL with psycopg 3.")

    query = dict(url.query)
    query["sslmode"] = "require"
    secure_url = url.set(query=query)
    options = {"connect_args": {"sslmode": "require", "connect_timeout": 10, "options": "-c statement_timeout=5000"}}
    if "poolclass" not in engine_options:
        options.update(
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_timeout=10,
            pool_recycle=1800,
        )
    options.update(engine_options)
    return create_engine(secure_url, **options)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return create_database_engine(database_url)


def get_db_session() -> Generator[Session, None, None]:
    try:
        engine = get_engine()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Database is not configured.") from exc

    with Session(engine) as session:
        yield session
