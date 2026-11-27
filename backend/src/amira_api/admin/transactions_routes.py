from dataclasses import asdict
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from amira_api.admin import transactions
from amira_api.admin.csv_export import EXPORT_LIMIT, export_csv
from amira_api.admin.deps import AdminUser
from amira_api.admin.listing import ListFilters, listed
from amira_api.db import get_db_session
from amira_api.settings import Settings, get_settings

router = APIRouter(prefix="/transactions")
Database = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Resource = Literal["payments", "refunds", "payouts", "payout-candidates"]


class RefundDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=500)


@router.get("/{kind}")
def list_transactions(kind: Resource, session: Database, settings: AppSettings, params: Annotated[ListFilters, Query()]):
    page = listed(session, transactions.QUERIES[kind](session, params), params)
    page["items"] = [transactions.enrich(kind, row, settings) for row in page["items"]]
    return page


@router.get("/{kind}/export.csv")
def download(kind: Resource, session: Database, settings: AppSettings, params: Annotated[ListFilters, Query()]):
    source = transactions.QUERIES[kind](session, params)
    columns = list(source.selected_columns.keys())
    if kind == "payments":
        columns.extend(("net", "iva"))
    if kind == "payout-candidates":
        columns.extend(("commission", "net_amount"))
    rows = [transactions.enrich(kind, row, settings) for row in listed(session, source, params, limit=EXPORT_LIMIT)]
    return export_csv(kind, columns, ([row.get(key) for key in columns] for row in rows))


@router.get("/payouts/{record_id}/receipt")
def receipt(record_id: UUID, session: Database, settings: AppSettings):
    return HTMLResponse(transactions.payout_receipt(session, record_id, settings), headers={
        "Content-Disposition": f'attachment; filename="desembolso-{record_id}.html"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.get("/{kind}/{record_id}")
def item(kind: Resource, record_id: UUID, session: Database, settings: AppSettings):
    return transactions.detail(session, kind, record_id, settings)


@router.post("/payments/{record_id}/refund")
def refund(record_id: UUID, payload: RefundDecision, admin: AdminUser, session: Database, settings: AppSettings):
    transactions.refund_payment(session, record_id, admin.id, payload.reason, settings)
    return {"status": "updated"}


@router.post("/payouts/release")
def release(admin: AdminUser, session: Database, settings: AppSettings):
    return asdict(transactions.release_admin_payouts(session, admin.id, settings))
