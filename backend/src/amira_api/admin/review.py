"""Admin projections and audited decisions for document, bank, and rating review."""

from collections.abc import Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Integer, String, case, cast, func, literal, select
from sqlalchemy.orm import Session, aliased

from amira_api.admin.audit import append_audit
from amira_api.admin.claim_service import require_reason
from amira_api.admin.listing import ListFilters, contains
from amira_api.admin.people import _date_filter
from amira_api.clock import utc_now
from amira_api.driver_verification_review import ReviewRefused, approve_certificate, reject_certificate
from amira_api.evidence_storage import EvidenceStorage, EvidenceStorageError
from amira_api.models import Conductor, Cotizacion, CuentaDesembolso, Desembolso, Pago, Perfil, Reclamo, Servicio, Usuario, Valoracion, VerificacionIdentidad
from amira_api.settings import Settings

MISMATCH = "El RUT del titular no coincide con el del proveedor"


def _name(person):
    return person.first_name + literal(" ") + person.last_name


def _match_rut(column):
    return func.lower(func.replace(func.replace(func.trim(column), ".", ""), "-", ""))


def _compare_rut(value: str | None):
    return value.strip().replace(".", "").replace("-", "").lower() if value else ""


def _status_and_date(query, state, created, filters):
    if filters.status:
        query = query.where(state == filters.status)
    return _date_filter(query, created, filters)


def documents(session: Session, filters: ListFilters):
    row = VerificacionIdentidad
    reviewer = aliased(Usuario)
    query = (
        select(row.id, _name(Usuario).label("driver"), Usuario.national_id, Perfil.name.label("provider"),
               row.document_type, row.created_at, row.provider,
               case((row.reviewed_at.is_not(None), "in_review"), else_=row.status).label("result"), row.status, row.reviewed_at,
               func.coalesce(reviewer.email, cast(row.reviewed_by, String)).label("reviewer"))
        .join(Usuario, Usuario.id == row.user_id).outerjoin(Conductor, Conductor.user_id == row.user_id)
        .outerjoin(Perfil, Perfil.id == Conductor.employer_profile_id)
        .outerjoin(reviewer, reviewer.auth_user_id == row.reviewed_by)
        .where(row.document_type.in_(("criminal_record", "driver_record")), contains(filters.q, _name(Usuario), Usuario.national_id))
    )
    if filters.driver:
        query = query.where(Conductor.id == filters.driver)
    return _status_and_date(query, row.status, row.created_at, filters)


def bank_accounts(session: Session, filters: ListFilters):
    row = CuentaDesembolso
    profile_rut = case((Perfil.kind == "company", Perfil.company_tax_id), else_=Usuario.national_id)
    match = func.coalesce((_match_rut(row.holder_rut) == _match_rut(profile_rut)) & (_match_rut(row.holder_rut) != ""), False)
    last_four = case((func.length(row.account_number) > 4, func.length(row.account_number) - 3), else_=1)
    masked = literal("****") + func.substr(row.account_number, last_four, 4)
    query = (
        select(row.id, Perfil.name.label("provider"), Perfil.id.label("provider_id"), row.bank_name, row.account_type,
               masked.label("masked_number"), row.holder_rut, profile_rut.label("profile_rut"), match.label("matches"),
               row.registration_status.label("status"), row.payouts_enabled, row.created_at)
        .join(Perfil, Perfil.id == row.profile_id).join(Usuario, Usuario.id == Perfil.owner_user_id)
        .where(contains(filters.q, Perfil.name, row.holder_rut, profile_rut))
    )
    if filters.provider:
        query = query.where(row.profile_id == filters.provider)
    if filters.matches is not None:
        query = query.where(match.is_(filters.matches))
    return _status_and_date(query, row.registration_status, row.created_at, filters)


def claims(session: Session, filters: ListFilters):
    now = utc_now()
    last = func.coalesce(Reclamo.resolved_at, now)
    days = (func.julianday(last) - func.julianday(Reclamo.created_at)) if session.get_bind().dialect.name == "sqlite" else (
        func.extract("epoch", last - Reclamo.created_at) / 86400)
    query = (
        select(Reclamo.id, Reclamo.service_id, _name(Usuario).label("customer"), Perfil.name.label("provider"),
               Perfil.id.label("provider_id"), Reclamo.reason, Reclamo.created_at, cast(func.floor(days), Integer).label("open_days"),
               Servicio.amount, Reclamo.status, Reclamo.resolution, Reclamo.resolved_at, Reclamo.resolution_reason)
        .join(Servicio, Servicio.id == Reclamo.service_id).join(Perfil, Perfil.id == Servicio.profile_id)
        .join(Usuario, Usuario.id == Reclamo.user_id)
        .where(contains(filters.q, _name(Usuario), Perfil.name, cast(Servicio.id, String)))
    )
    if filters.provider:
        query = query.where(Perfil.id == filters.provider)
    if filters.service:
        query = query.where(Servicio.id == filters.service)
    return _status_and_date(query, Reclamo.status, Reclamo.created_at, filters)


def ratings(session: Session, filters: ListFilters):
    visible = Valoracion.hidden_at.is_(None)
    query = (
        select(Valoracion.id, Perfil.name.label("provider"), Perfil.id.label("provider_id"), _name(Usuario).label("customer"),
               Valoracion.service_id, Valoracion.rating, Valoracion.comment, Valoracion.created_at,
               visible.label("visible"), Valoracion.hidden_at, Valoracion.hidden_reason)
        .join(Servicio, Servicio.id == Valoracion.service_id)
        .join(Perfil, Perfil.id == Servicio.profile_id).join(Usuario, Usuario.id == Valoracion.user_id)
        .where(contains(filters.q, Valoracion.comment, Perfil.name))
    )
    if filters.provider:
        query = query.where(Perfil.id == filters.provider)
    if filters.rating:
        query = query.where(Valoracion.rating == filters.rating)
    if filters.visible is not None:
        query = query.where(visible if filters.visible else ~visible)
    return _date_filter(query, Valoracion.created_at, filters)


QUERIES = {"documents": documents, "bank-accounts": bank_accounts, "claims": claims, "ratings": ratings}


def _signed_url(resolve: Callable[[], EvidenceStorage], key: str | None, ttl: int):
    if not key:
        return None
    try:
        return resolve().create_signed_url(key, ttl)
    except (HTTPException, EvidenceStorageError):
        return None


def review_detail(session: Session, kind: str, key: UUID, settings: Settings,
                  certificate_storage: Callable[[], EvidenceStorage], service_storage: Callable[[], EvidenceStorage]):
    rows = QUERIES[kind](session, ListFilters()).subquery()
    row = session.execute(select(rows).where(rows.c.id == key)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "No se encontró el registro.")
    result = dict(row)
    if kind == "documents":
        doc = session.get(VerificacionIdentidad, key)
        result.update(annotations=doc.annotations, review_reason=doc.rejection_reason,
                      pdf_url=_signed_url(certificate_storage, doc.pdf_storage_key, settings.driver_certificate_url_ttl_seconds))
    if kind == "claims":
        claim = session.get(Reclamo, key)
        service = session.get(Servicio, claim.service_id)
        result.update(
            evidence_url=_signed_url(service_storage, claim.private_evidence_key, settings.service_evidence_url_ttl_seconds),
            delivery_url=_signed_url(service_storage, service.delivery_evidence_key, settings.service_evidence_url_ttl_seconds),
            chat_id=session.scalar(select(Cotizacion.chat_id).where(Cotizacion.id == service.accepted_quotation_id)),
            service_status=service.status, started_at=service.starts_at, completed_at=service.completed_at, cancelled_at=service.cancelled_at,
            payment_status=session.scalar(select(Pago.status).where(Pago.quotation_id == service.accepted_quotation_id)
                                          .order_by(Pago.created_at.desc()).limit(1)),
            payout_status=session.scalar(select(Desembolso.status).where(Desembolso.service_id == service.id).limit(1)),
        )
    return result


def review_action(session: Session, kind: str, key: UUID, admin_id: UUID, action: str, reason: str | None):
    if action in {"reject", "disable", "hide"}:
        reason = require_reason(reason)
    now = utc_now()

    def audit(entity, prior, result):
        append_audit(session, admin_user_id=admin_id, action=f"{entity}.{action}", entity_type=entity,
                     entity_id=key, reason=reason, before=prior, after=result)

    if kind == "documents" and action in {"approve", "reject"}:
        def reviewed(row: VerificacionIdentidad):
            row.reviewed_by = admin_id
            audit("verification", {"status": "in_review"}, {"status": row.status, "reviewed_by": admin_id, "reviewed_at": now})
        try:
            if action == "approve":
                approve_certificate(session, key, now, on_review=reviewed)
            else:
                reject_certificate(session, key, reason or "", now, on_review=reviewed)
        except ReviewRefused as error:
            raise HTTPException(409, str(error)) from error
        return
    if kind == "bank-accounts" and action in {"approve", "reject", "disable"}:
        account = session.scalar(select(CuentaDesembolso).where(CuentaDesembolso.id == key).with_for_update())
        if account is None:
            raise HTTPException(404, "No se encontró la cuenta.")
        prior = {"status": account.registration_status, "payouts_enabled": account.payouts_enabled}
        if action in {"approve", "reject"} and account.registration_status != "pending":
            raise HTTPException(409, "Solo se puede decidir una cuenta pendiente.")
        if action == "disable" and account.registration_status != "active":
            raise HTTPException(409, "Solo se puede deshabilitar una cuenta activa.")
        if action == "approve":
            profile = account.profile
            profile_rut = profile.company_tax_id if profile.kind == "company" else profile.owner.national_id
            if not _compare_rut(account.holder_rut) or _compare_rut(account.holder_rut) != _compare_rut(profile_rut):
                raise HTTPException(409, MISMATCH)
        account.registration_status = {"approve": "active", "reject": "rejected", "disable": "disabled"}[action]
        account.payouts_enabled = action == "approve"
        audit("bank_account", prior, {"status": account.registration_status, "payouts_enabled": account.payouts_enabled})
    elif kind == "ratings" and action in {"hide", "show"}:
        rating = session.scalar(select(Valoracion).where(Valoracion.id == key).with_for_update())
        if rating is None:
            raise HTTPException(404, "No se encontró la valoración.")
        if (rating.hidden_at is not None) == (action == "hide"):
            raise HTTPException(409, "La valoración ya se encuentra en ese estado.")
        prior = {"hidden_at": rating.hidden_at, "hidden_reason": rating.hidden_reason}
        rating.hidden_at = now if action == "hide" else None
        rating.hidden_reason = reason if action == "hide" else None
        audit("rating", prior, {"hidden_at": rating.hidden_at, "hidden_reason": rating.hidden_reason})
    else:
        raise HTTPException(422, "Acción no válida para el registro.")
    session.commit()
