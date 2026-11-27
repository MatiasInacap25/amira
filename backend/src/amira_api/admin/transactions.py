"""Read-only financial records plus guarded entry points into the simulated money services."""

from html import escape
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from amira_api.admin.audit import append_audit
from amira_api.admin.listing import ListFilters, contains
from amira_api.admin.operations import _amounts, _name, _rows, breakdown, cancel_admin_service
from amira_api.admin.people import _date_filter
from amira_api.clock import utc_now
from amira_api.models import (
    AdminAuditLog, Chat, Cotizacion, CuentaDesembolso, Desembolso, FormularioServicio, Pago,
    PaymentProviderTransaction, Perfil, Reclamo, Reembolso, Servicio, Usuario,
)
from amira_api.payment_provider import SIMULATED_PROVIDER_NAME
from amira_api.payment_service import APPROVED
from amira_api.payout_service import RELEASED, _due_conditions, _payout_exists, commission_for, release_due_payouts
from amira_api.release_payouts import build_payout_provider
from amira_api.service_views import open_claim_exists
from amira_api.settings import Settings
from amira_api.tax import split_iva


def payments(session: Session, filters: ListFilters):
    query = (
        select(Pago.id, Pago.quotation_id, Servicio.id.label("service_id"), _name(Usuario).label("customer"),
               Perfil.name.label("provider"), FormularioServicio.profile_id.label("provider_id"), Pago.amount, Pago.status,
               Pago.provider.label("payment_provider"), Pago.provider_payment_id.label("external_id"), Pago.created_at,
               Pago.confirmed_at, Servicio.status.label("service_status"),
               exists().where(Desembolso.service_id == Servicio.id).correlate(Servicio).label("already_paid_out"),
               exists().where(Reembolso.payment_id == Pago.id).correlate(Pago).label("already_refunded"))
        .join(Cotizacion, Cotizacion.id == Pago.quotation_id)
        .join(Chat, Chat.id == Cotizacion.chat_id).join(FormularioServicio, FormularioServicio.id == Chat.form_id)
        .join(Usuario, Usuario.id == FormularioServicio.customer_id).outerjoin(Perfil, Perfil.id == FormularioServicio.profile_id)
        .outerjoin(Servicio, Servicio.accepted_quotation_id == Pago.quotation_id)
        .where(contains(filters.q, cast(Pago.id, String), Pago.provider_payment_id, _name(Usuario)))
    )
    for column, value in ((Pago.status, filters.status), (Pago.provider, filters.payment_provider),
                          (Pago.quotation_id, filters.quotation), (Servicio.id, filters.service),
                          (FormularioServicio.customer_id, filters.customer), (FormularioServicio.profile_id, filters.provider)):
        if value is not None:
            query = query.where(column == value)
    return _amounts(_date_filter(query, Pago.created_at, filters), Pago.amount, filters)


def refunds(session: Session, filters: ListFilters):
    audit_reason = select(AdminAuditLog.reason).where(AdminAuditLog.entity_type == "service",
        func.replace(AdminAuditLog.entity_id, "-", "") == func.replace(cast(Servicio.id, String), "-", ""), AdminAuditLog.action == "service.cancel").order_by(
        AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()).limit(1).correlate(Servicio).scalar_subquery()
    query = (
        select(Reembolso.id, Reembolso.payment_id, Servicio.id.label("service_id"), _name(Usuario).label("customer"),
               Reembolso.amount, func.coalesce(Servicio.cancellation_retained_amount, 0).label("retained"),
               func.coalesce(Reclamo.resolution_reason, audit_reason).label("reason"),
               Servicio.cancelled_by.label("actor"), Reembolso.created_at, Reembolso.status)
        .join(Pago, Pago.id == Reembolso.payment_id).join(Servicio, Servicio.accepted_quotation_id == Pago.quotation_id)
        .join(Usuario, Usuario.id == Servicio.customer_id).outerjoin(Reclamo, Reclamo.id == Reembolso.claim_id)
        .where(contains(filters.q, _name(Usuario), cast(Servicio.id, String)))
    )
    if filters.actor:
        query = query.where(Servicio.cancelled_by == filters.actor)
    if filters.service:
        query = query.where(Servicio.id == filters.service)
    return _date_filter(query, Reembolso.created_at, filters)


def payouts(session: Session, filters: ListFilters):
    query = (
        select(Desembolso.id, Desembolso.service_id, Perfil.id.label("provider_id"), Perfil.name.label("provider"),
               Pago.amount, (Pago.amount - Desembolso.net_amount).label("commission"), Desembolso.net_amount,
               Desembolso.provider_payout_id.label("external_id"), Desembolso.status, Desembolso.created_at, Desembolso.confirmed_at)
        .join(Pago, Pago.id == Desembolso.payment_id).join(Perfil, Perfil.id == Desembolso.beneficiary_profile_id)
        .where(Desembolso.status == RELEASED, contains(filters.q, Perfil.name, cast(Desembolso.service_id, String)))
    )
    if filters.provider:
        query = query.where(Perfil.id == filters.provider)
    return _date_filter(query, func.coalesce(Desembolso.confirmed_at, Desembolso.created_at), filters)


def payout_candidates(session: Session, filters: ListFilters):
    now = utc_now()
    amount = select(Pago.amount).where(Pago.quotation_id == Servicio.accepted_quotation_id, Pago.status == APPROVED).order_by(
        Pago.created_at.desc(), Pago.id.desc()).limit(1).correlate(Servicio).scalar_subquery()
    account = select(CuentaDesembolso.registration_status).where(CuentaDesembolso.profile_id == Servicio.profile_id).order_by(
        (and_(CuentaDesembolso.registration_status == "active", CuentaDesembolso.payouts_enabled.is_(True))).desc(),
        CuentaDesembolso.created_at, CuentaDesembolso.id).limit(1).correlate(Servicio).scalar_subquery()
    approved_account = exists().where(CuentaDesembolso.profile_id == Servicio.profile_id,
        CuentaDesembolso.registration_status == "active", CuentaDesembolso.payouts_enabled.is_(True)).correlate(Servicio)
    due = and_(*_due_conditions(now))
    block = case((open_claim_exists(), "claim"), (~due, "window"), (~approved_account, "bank_account"),
                 (amount.is_(None), "payment"), else_="none")
    query = (
        select(Servicio.id, Servicio.id.label("service_id"), Perfil.id.label("provider_id"), Perfil.name.label("provider"),
               account.label("account_status"), amount.label("amount"), Servicio.completed_at,
               Servicio.created_at, (due & approved_account & amount.is_not(None)).label("due"), block.label("blocked_by"))
        .join(Perfil, Perfil.id == Servicio.profile_id)
        .where(Servicio.status.in_(("completed", "disputed")), ~_payout_exists(),
               contains(filters.q, Perfil.name, cast(Servicio.id, String)))
    )
    if filters.provider:
        query = query.where(Perfil.id == filters.provider)
    return _date_filter(query, Servicio.completed_at, filters)


QUERIES = {"payments": payments, "refunds": refunds, "payouts": payouts, "payout-candidates": payout_candidates}


def enrich(kind: str, row: dict, settings: Settings):
    if kind == "payments":
        breakdown(row, settings)
    if kind == "payout-candidates" and row["amount"] is not None:
        row["commission"] = commission_for(row["amount"], settings.payout_commission_percent)
        row["net_amount"] = row["amount"] - row["commission"]
    return row


def detail(session: Session, kind: str, key: UUID, settings: Settings):
    base = QUERIES[kind](session, ListFilters()).subquery()
    row = session.execute(select(base).where(base.c.id == key)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "No se encontró el movimiento.")
    result = enrich(kind, dict(row), settings)
    if kind == "payments":
        entries = _rows(session, select(PaymentProviderTransaction.provider_transaction_id, PaymentProviderTransaction.created_at,
                                PaymentProviderTransaction.amount, PaymentProviderTransaction.live_mode, PaymentProviderTransaction.status_detail,
                                PaymentProviderTransaction.status)
                       .where(PaymentProviderTransaction.payment_id == key)
                       .order_by(PaymentProviderTransaction.created_at.desc(), PaymentProviderTransaction.provider_transaction_id))
        result["transactions"] = [dict(entry, status=entry["status"] or APPROVED, amount=entry["amount"] if entry["amount"] is not None else result["amount"]) for entry in entries]
        result["refunds"] = _rows(session, select(Reembolso.id, Reembolso.amount, Reembolso.status, Reembolso.created_at)
                                  .where(Reembolso.payment_id == key).order_by(Reembolso.created_at.desc()))
    return result


def refund_payment(session: Session, key: UUID, admin_id: UUID, reason: str | None, settings: Settings):
    payment = session.get(Pago, key)
    if payment is None:
        raise HTTPException(404, "No se encontró el pago.")
    if payment.status != APPROVED:
        raise HTTPException(409, "Solo se puede reembolsar un pago aprobado.")
    if payment.provider != SIMULATED_PROVIDER_NAME:
        raise HTTPException(503, "Solo se pueden reembolsar pagos simulados.")
    service_id = session.scalar(select(Servicio.id).where(Servicio.accepted_quotation_id == payment.quotation_id))
    if service_id is None:
        raise HTTPException(409, "El pago no tiene un servicio asociado.")
    cancel_admin_service(session, service_id, admin_id, reason, settings, expected_payment_id=key)


def release_admin_payouts(session: Session, admin_id: UUID, settings: Settings):
    try:
        provider = build_payout_provider(settings)
    except RuntimeError as error:
        raise HTTPException(503, "El adaptador de desembolsos simulado no está habilitado.") from error

    def audit(payout: Desembolso):
        append_audit(session, admin_user_id=admin_id, action="payout.release", entity_type="payout", entity_id=payout.id,
                     after={"service_id": payout.service_id, "net_amount": payout.net_amount, "status": payout.status})

    return release_due_payouts(session, utc_now(), provider, commission_percent=settings.payout_commission_percent, on_release=audit)


def payout_receipt(session: Session, key: UUID, settings: Settings) -> str:
    row = detail(session, "payouts", key, settings)
    gross, fee, net = int(row["amount"]), int(row["commission"]), int(row["net_amount"])
    gross_net, gross_iva = split_iva(gross)
    fee_net, fee_iva = split_iva(fee)
    rows = (("Servicio", row["service_id"]), ("Transportista", row["provider"]), ("Total cobrado (CLP)", gross),
            ("Neto del servicio", gross_net), ("IVA del servicio", gross_iva), ("Comisión bruta de Amira", fee),
            ("Comisión neta", fee_net), ("IVA de la comisión", fee_iva), ("Neto pagado al transportista", net),
            ("Confirmado el", row["confirmed_at"]))
    fields = "".join(f"<dt>{label}</dt><dd>{escape(str(value))}</dd>" for label, value in rows)
    return ('<!doctype html><html lang="es"><meta charset="utf-8"><title>Comprobante de desembolso</title>'
            '<main><h1>Comprobante de desembolso</h1><p>Simulación · Valores en pesos chilenos</p>'
            f"<dl>{fields}</dl></main></html>")
