"""UTC helpers for values read from the database.

Postgres returns timezone-aware datetimes. SQLite, used by the tests, returns naive values that are UTC by construction.
"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
