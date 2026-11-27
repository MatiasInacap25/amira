from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from amira_api.admin.csv_export import EXPORT_LIMIT, export_csv
from amira_api.admin.schemas import AdminAuditEntry, AdminPage
from amira_api.db import get_db_session
from amira_api.models import AdminAuditLog

router = APIRouter(prefix="/audit")
Database = Annotated[Session, Depends(get_db_session)]


class AuditFilters(BaseModel):
    admin: UUID | None = None
    action: str | None = Field(default=None, max_length=80)
    entity: str | None = Field(default=None, max_length=80)
    q: str | None = Field(default=None, max_length=200)
    created_from: AwareDatetime | None = None
    created_to: AwareDatetime | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort: Literal["created_at", "-created_at"] = "-created_at"


class AuditListFilters(AuditFilters):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


def _filtered(filters: AuditFilters):
    log = AdminAuditLog
    statement = select(log)
    for column, value in ((log.admin_user_id, filters.admin), (log.action, filters.action), (log.entity_type, filters.entity)):
        if value is not None:
            statement = statement.where(column == value)
    if filters.created_from is not None:
        statement = statement.where(log.created_at >= filters.created_from)
    if filters.created_to is not None:
        statement = statement.where(log.created_at <= filters.created_to)
    timezone = ZoneInfo("America/Santiago")
    if filters.date_from is not None:
        statement = statement.where(log.created_at >= datetime.combine(filters.date_from, time.min, timezone))
    if filters.date_to is not None:
        statement = statement.where(log.created_at <= datetime.combine(filters.date_to, time.max, timezone))
    if filters.q:
        statement = statement.where(or_(*(column.icontains(filters.q, autoescape=True) for column in (
            log.action, log.entity_type, log.entity_id, log.reason,
        ))))
    return statement


def _order(filters: AuditFilters):
    if filters.sort == "created_at":
        return AdminAuditLog.created_at.asc(), AdminAuditLog.id.asc()
    return AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()


@router.get("", response_model=AdminPage[AdminAuditEntry])
def list_audit(
    session: Database,
    filters: Annotated[AuditListFilters, Query()],
):
    statement = _filtered(filters)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    entries = session.scalars(statement.order_by(*_order(filters)).limit(filters.limit).offset(filters.offset)).all()
    return {"items": entries, "total": total, "limit": filters.limit, "offset": filters.offset}


@router.get("/export.csv")
def download_audit(session: Database, filters: Annotated[AuditFilters, Query()]):
    entries = session.scalars(_filtered(filters).order_by(*_order(filters)).limit(EXPORT_LIMIT))
    return export_csv(
        "auditoria", ("fecha", "admin", "acción", "entidad", "id", "motivo"),
        ((entry.created_at.isoformat(), entry.admin_user_id, entry.action, entry.entity_type, entry.entity_id, entry.reason)
         for entry in entries),
    )
