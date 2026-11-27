"""Shared parameter and pagination contract for allowlisted admin resources."""

from datetime import date
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session


class ListFilters(BaseModel):
    q: str | None = Field(None, max_length=200)
    status: str | None = Field(None, max_length=50)
    sort: str | None = Field(None, max_length=64)
    provider: UUID | None = None
    customer: UUID | None = None
    driver: UUID | None = None
    service: UUID | None = None
    kind: str | None = Field(None, max_length=50)
    region: str | None = Field(None, max_length=20)
    verification: str | None = Field(None, max_length=50)
    published: bool | None = None
    has_claim: bool | None = None
    matches: bool | None = None
    visible: bool | None = None
    rating: int | None = Field(None, ge=1, le=5)
    start: date | None = None
    end: date | None = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100_000)


def contains(term: str | None, *columns):
    return or_(*(column.icontains(term, autoescape=True) for column in columns)) if term else True


def listed(session: Session, source, params: ListFilters, *, limit: int | None = None):
    rows = source.order_by(None).subquery()
    keys = {item.key for item in rows.c}
    primary = rows.c.id
    sort = params.sort or ("-created_at" if "created_at" in keys else "-id")
    descending = sort.startswith("-")
    sort_key = sort.removeprefix("-")
    if sort_key not in {"id", "created_at", "paid", "open_days"} or sort_key not in keys:
        raise HTTPException(422, "Orden no válido.")
    column = rows.c[sort_key]
    statement = select(rows).order_by(column.desc() if descending else column.asc(), primary.asc())
    if limit is not None:
        return [dict(row) for row in session.execute(statement.limit(limit)).mappings()]
    total = session.scalar(select(func.count()).select_from(rows)) or 0
    items = session.execute(statement.limit(params.limit).offset(params.offset)).mappings()
    return {"items": [dict(row) for row in items], "total": total, "limit": params.limit, "offset": params.offset}
