from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from amira_api.admin import finance
from amira_api.admin.csv_export import EXPORT_LIMIT, export_csv
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.settings import Settings, get_settings

router = APIRouter()
Database = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
First = Annotated[date | None, Query(alias="from")]
Last = Annotated[date | None, Query(alias="to")]


@router.get("/finance/summary")
def summary(session: Database, settings: AppSettings, first: First = None, last: Last = None):
    now = utc_now()
    return finance.finance_summary(session, finance.reporting_period(first, last, now), now, settings)


@router.get("/finance/timeseries")
def timeseries(session: Database, settings: AppSettings, first: First = None, last: Last = None, bucket: Literal["day"] = "day"):
    return finance.timeseries(session, finance.reporting_period(first, last, utc_now()), settings.payout_commission_percent)


@router.get("/finance/movements")
def movements(session: Database, limit: Annotated[int, Query(ge=1, le=100)] = 10):
    return finance.movements(session, limit)


@router.get("/finance/providers")
def providers(session: Database, settings: AppSettings, first: First = None, last: Last = None):
    return finance.provider_commissions(session, finance.reporting_period(first, last, utc_now()), settings.payout_commission_percent)


@router.get("/finance/export.csv")
def export(session: Database, settings: AppSettings, first: First = None, last: Last = None):
    now = utc_now()
    period = finance.reporting_period(first, last, now)
    totals = finance.finance_summary(session, period, now, settings)
    rows = finance.provider_commissions(session, period, settings.payout_commission_percent)[:EXPORT_LIMIT]
    return export_csv("comisiones", (
        "Desde", "Hasta", "Proveedor", "Servicios", "Bruto cobrado", "Comisión bruta",
        "IVA comisión", "Pagado neto", "Comisión neta total", "Retenido neto", "IVA retenciones", "IVA débito total",
    ), [
        (period.first, period.last, "Total", "", totals["collected"], totals["commission_gross"], totals["commission_iva"],
         totals["payout_paid"], totals["commission_net"], totals["retained_net"], totals["retained_iva"], totals["platform_iva"]),
        *((period.first, period.last, row["provider"], row["services"], row["gross"], row["commission"], row["commission_iva"],
           row["net_paid"], "", "", "", "") for row in rows[:EXPORT_LIMIT - 1]),
    ])


@router.get("/configuration")
def configuration(session: Database, settings: AppSettings):
    return finance.configuration(session, settings)
