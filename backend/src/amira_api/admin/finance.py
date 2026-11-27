"""Read-only mandate-model reporting. No financial provider is called."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.orm import Session

from amira_api.admin.badges import pending_badges
from amira_api.models import Desembolso, FormularioServicio, Pago, Perfil, Reembolso, Servicio, Usuario
from amira_api.payment_routes import get_payment_provider
from amira_api.payment_service import APPROVED
from amira_api.payout_service import RELEASED, _due_service_ids, _payout_exists, commission_for
from amira_api.release_payouts import build_payout_provider
from amira_api.service_views import open_claim_exists
from amira_api.settings import Settings

SANTIAGO = ZoneInfo("America/Santiago")


class Period(NamedTuple):
    first: date
    last: date

    @property
    def bounds(self) -> tuple[datetime, datetime]:
        return (
            datetime.combine(self.first, time.min, SANTIAGO).astimezone(UTC),
            datetime.combine(self.last + timedelta(days=1), time.min, SANTIAGO).astimezone(UTC),
        )


def reporting_period(first: date | None, last: date | None, now: datetime) -> Period:
    last = last or now.astimezone(SANTIAGO).date()
    first = first or date.fromordinal(max(1, last.toordinal() - 29))
    if not 0 <= (last - first).days <= 365 or last == date.max:
        raise HTTPException(422, "El período debe contener entre 1 y 366 días.")
    return Period(first, last)


def split_iva(gross: Decimal) -> tuple[Decimal, Decimal]:
    net = (gross / Decimal("1.19")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return net, gross - net


def _during(column, period: Period):
    first, end = period.bounds
    return column >= first, column < end


def _payment_time():
    return func.coalesce(Pago.confirmed_at, Pago.created_at)


def _refund_time():
    return func.coalesce(Reembolso.confirmed_at, Reembolso.created_at)


def _payout_time():
    return func.coalesce(Desembolso.confirmed_at, Desembolso.created_at)


def _payments(period: Period):
    timestamp = _payment_time()
    return (
        select(Pago.amount, timestamp.label("timestamp"), Servicio.id.label("service_id"),
               Perfil.id.label("provider_id"), Perfil.name.label("provider"))
        .outerjoin(Servicio, Servicio.accepted_quotation_id == Pago.quotation_id)
        .outerjoin(Perfil, Perfil.id == Servicio.profile_id)
        .where(Pago.status == APPROVED, *_during(timestamp, period))
    )


def _collected(session: Session, period: Period, percent: int):
    for row in session.execute(_payments(period)).yield_per(500):
        fee = commission_for(row.amount, percent)
        net, iva = split_iva(fee)
        occurred = row.timestamp.replace(tzinfo=UTC) if row.timestamp.tzinfo is None else row.timestamp
        yield row, occurred.astimezone(SANTIAGO).date(), fee, net, iva


def _paid(period: Period):
    return select(Desembolso).where(Desembolso.status == RELEASED, *_during(_payout_time(), period))


def _eligible_payments():
    latest = (
        select(Pago.amount).where(Pago.quotation_id == Servicio.accepted_quotation_id, Pago.status == APPROVED)
        .order_by(Pago.created_at.desc(), Pago.id.desc()).limit(1).correlate(Servicio).scalar_subquery()
    )
    return latest


def _sum(session: Session, column, *criteria):
    return session.scalar(select(func.coalesce(func.sum(column), 0)).where(*criteria)) or Decimal(0)


def finance_summary(session: Session, period: Period, now: datetime, settings: Settings):
    percent = settings.payout_commission_percent
    collected = fee = fee_net = fee_iva = Decimal(0)
    for payment, _, commission, net, iva in _collected(session, period, percent):
        collected += payment.amount
        fee += commission
        fee_net += net
        fee_iva += iva
    refunds = _sum(session, Reembolso.amount, *_during(_refund_time(), period))
    paid = _sum(session, Desembolso.net_amount, Desembolso.status == RELEASED, *_during(_payout_time(), period))
    retained = retention_iva = Decimal(0)
    amounts = session.scalars(select(Servicio.cancellation_retained_amount).where(
        Servicio.cancellation_retained_amount > 0, *_during(Servicio.cancelled_at, period),
    ))
    for amount in amounts.yield_per(500):
        retained += amount
        retention_iva += split_iva(amount)[1]
    due_ids = _due_service_ids(session, now)
    latest = _eligible_payments()
    due_count = 0
    due = Decimal(0)
    for start in range(0, len(due_ids), 500):
        for amount in session.scalars(select(latest).select_from(Servicio).where(
            Servicio.id.in_(due_ids[start:start + 500]), latest.is_not(None), *_during(Servicio.completed_at, period),
        )):
            due_count += 1
            due += amount - commission_for(amount, percent)
    blocked = session.scalar(select(func.count()).select_from(Servicio).where(
        open_claim_exists(), ~_payout_exists(), latest.is_not(None),
        *_during(func.coalesce(Servicio.completed_at, Servicio.created_at), period),
    )) or 0
    states = {
        status: session.scalar(select(func.count()).select_from(Servicio).where(Servicio.status == status, *_during(event, period))) or 0
        for status, event in (("in_progress", Servicio.created_at), ("completed", Servicio.completed_at), ("cancelled", Servicio.cancelled_at))
    }
    return {
        "from": period.first, "to": period.last, "collected": collected, "refunded": refunds,
        "net_collected": collected - refunds, "payout_due": due, "payout_due_count": due_count,
        "payout_blocked_count": blocked, "payout_paid": paid, "commission_gross": fee,
        "commission_net": fee_net, "commission_iva": fee_iva, "retained_net": retained - retention_iva,
        "retained_iva": retention_iva, "platform_iva": fee_iva + retention_iva, "service_counts": states,
        "pending": pending_badges(session),
    }


def timeseries(session: Session, period: Period, percent: int):
    days = {period.first + timedelta(days=i): [Decimal(0), Decimal(0)] for i in range((period.last - period.first).days + 1)}
    for payment, day, fee, *_ in _collected(session, period, percent):
        days[day][0] += payment.amount
        days[day][1] += fee
    return [{"day": day, "collected": values[0], "commission": values[1]} for day, values in days.items()]


def movements(session: Session, limit: int):
    payments = select(Pago.id, _payment_time().label("at"), literal("payment").label("kind"), Pago.quotation_id,
                      Pago.amount, Pago.status).where(Pago.status == APPROVED)
    refunds = select(Reembolso.id, _refund_time(), literal("refund"), Pago.quotation_id,
                     Reembolso.amount, Reembolso.status).join(Pago, Pago.id == Reembolso.payment_id)
    payouts = select(Desembolso.id, _payout_time(), literal("payout"), Pago.quotation_id,
                     Desembolso.net_amount, Desembolso.status).join(Pago, Pago.id == Desembolso.payment_id)
    entry = union_all(payments, refunds, payouts).subquery()
    statement = (
        select(entry.c.id, entry.c.at, entry.c.kind, entry.c.amount, entry.c.status, Servicio.id.label("service_id"),
               Usuario.first_name, Usuario.last_name, Perfil.name.label("provider"))
        .outerjoin(Servicio, Servicio.accepted_quotation_id == entry.c.quotation_id)
        .outerjoin(FormularioServicio, FormularioServicio.id == Servicio.form_id)
        .outerjoin(Usuario, Usuario.id == FormularioServicio.customer_id)
        .outerjoin(Perfil, Perfil.id == Servicio.profile_id)
        .order_by(entry.c.at.desc(), entry.c.id.desc()).limit(limit)
    )
    return [dict(row._mapping) for row in session.execute(statement)]


def provider_commissions(session: Session, period: Period, percent: int):
    providers = {}
    def account(provider_id, name):
        return providers.setdefault(provider_id, {
            "provider": name, "services": set(), "gross": Decimal(0), "commission": Decimal(0),
            "commission_iva": Decimal(0), "net_paid": Decimal(0),
        })

    for payment, _, fee, _, iva in _collected(session, period, percent):
        if payment.provider_id is None:
            continue
        row = account(payment.provider_id, payment.provider)
        row["services"].add(payment.service_id)
        row["gross"] += payment.amount
        row["commission"] += fee
        row["commission_iva"] += iva

    payouts = _paid(period).with_only_columns(Desembolso.beneficiary_profile_id, Perfil.name, func.sum(Desembolso.net_amount))
    payouts = payouts.join(Perfil, Perfil.id == Desembolso.beneficiary_profile_id).group_by(Desembolso.beneficiary_profile_id, Perfil.name)
    for provider_id, name, paid in session.execute(payouts):
        account(provider_id, name)["net_paid"] = paid
    return [dict(row, services=len(row["services"])) for row in sorted(providers.values(), key=lambda item: item["provider"])]


def configuration(session: Session, settings: Settings):
    try:
        payment = get_payment_provider(settings).name
    except (HTTPException, RuntimeError):
        payment = None
    try:
        payout = build_payout_provider(settings).name
    except RuntimeError:
        payout = None
    emails = dict(session.execute(select(Usuario.auth_user_id, Usuario.email).where(
        Usuario.auth_user_id.in_(settings.admin_user_ids)
    )).all())
    return {
        "app_env": settings.app_env,
        "commission_percent": settings.payout_commission_percent,
        "claim_window_hours": settings.service_claim_window_hours,
        "payment_adapter": payment, "payout_adapter": payout,
        "admins": [{"user_id": admin_id, "email": emails.get(admin_id)} for admin_id in sorted(settings.admin_user_ids)],
    }
