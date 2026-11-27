from datetime import UTC
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, exists, func, literal, or_, select
from sqlalchemy.orm import Session, aliased

from amira_api.admin.audit import append_audit
from amira_api.admin.listing import ListFilters, contains
from amira_api.clock import utc_now
from amira_api.invitation_routes import _invitation_status
from amira_api.models import (
    Commune, Conductor, CuentaDesembolso, Desembolso, DriverInvitation, FormularioServicio, Pago, Perfil, Reclamo, Reembolso,
    RolUsuario, Servicio, ServicioAsignacion, ServicioDisponible, TipoConductor, Usuario, Valoracion,
    Vehiculo, VerificacionIdentidad,
)
from amira_api.payment_service import APPROVED
from amira_api.provider_profile_routes import _missing_items

MODELS = {"customers": Usuario, "providers": Perfil, "drivers": Conductor, "invitations": DriverInvitation, "vehicles": Vehiculo}
ENTITY = {"customers": "customer", "providers": "provider", "drivers": "driver", "invitations": "invitation", "vehicles": "vehicle"}
EDIT = {
    "customers": {"first_name", "last_name", "phone"},
    "providers": {"name", "description", "commune_code"},
    "vehicles": {"brand", "model", "year", "maximum_weight"},
}
STATUS = {
    "customers": {"block": ("blocked_at", "blocked_reason", True), "unblock": ("blocked_at", "blocked_reason", False)},
    "drivers": {"block": ("blocked_at", "blocked_reason", True), "unblock": ("blocked_at", "blocked_reason", False)},
    "providers": {"suspend": ("suspended_at", "suspended_reason", True), "reactivate": ("suspended_at", "suspended_reason", False)},
    "vehicles": {"disable": ("disabled_at", "disabled_reason", True), "enable": ("disabled_at", "disabled_reason", False)},
}
REASON_ACTIONS = {"block", "suspend", "disable", "unpublish", "revoke"}


def _status(column, blocked):
    return case((column.is_not(None), blocked), else_="active")


def _date_filter(query, column, filters: ListFilters):
    if filters.start:
        query = query.where(func.date(column) >= filters.start)
    if filters.end:
        query = query.where(func.date(column) <= filters.end)
    return query


def _count(model, condition):
    return select(func.count()).select_from(model).where(condition).correlate_except(model).scalar_subquery()


def _full_name():
    return Usuario.first_name + literal(" ") + Usuario.last_name


def _filtered(query, status, created, filters):
    if filters.status:
        query = query.where(status == filters.status)
    return _date_filter(query, created, filters)


def customers(filters):
    status = _status(Usuario.blocked_at, "blocked")
    linked = Servicio.form_id == FormularioServicio.id
    own = FormularioServicio.customer_id == Usuario.id
    paid = (
        select(func.coalesce(func.sum(Pago.amount), 0)).join(Servicio, Servicio.accepted_quotation_id == Pago.quotation_id)
        .join(FormularioServicio, linked).where(own, Pago.status == APPROVED).correlate(Usuario).scalar_subquery()
    )
    services = select(func.count()).select_from(Servicio).join(FormularioServicio, linked).where(own).correlate(Usuario).scalar_subquery()
    claim = exists(select(Reclamo.id).where(Reclamo.user_id == Usuario.id)).correlate(Usuario)
    q = select(Usuario.id, _full_name().label("name"), Usuario.first_name, Usuario.last_name, Usuario.national_id,
               Usuario.email, Usuario.phone, Usuario.registered_at.label("created_at"), services.label("services"),
               paid.label("paid"), status.label("status")).join(RolUsuario, RolUsuario.id == Usuario.role_id).where(
        RolUsuario.code == "client", contains(filters.q, _full_name(), Usuario.national_id, Usuario.email),
    )
    if filters.has_claim is not None:
        q = q.where(claim if filters.has_claim else ~claim)
    return _filtered(q, status, Usuario.registered_at, filters)


def providers(filters):
    status = _status(Perfil.suspended_at, "suspended")
    avg = select(func.avg(Valoracion.rating)).join(Servicio, Servicio.id == Valoracion.service_id).where(
        Servicio.profile_id == Perfil.id).correlate(Perfil).scalar_subquery()
    q = select(Perfil.id, Perfil.name, Perfil.kind, Perfil.company_tax_id, _full_name().label("owner"),
               Usuario.email.label("owner_email"), Perfil.public_activated_at.is_not(None).label("published"),
               _count(Conductor, or_(Conductor.employer_profile_id == Perfil.id, Conductor.user_id == Perfil.owner_user_id)).label("drivers"),
               _count(Vehiculo, Vehiculo.profile_id == Perfil.id).label("vehicles"),
               _count(Servicio, (Servicio.profile_id == Perfil.id) & (Servicio.status == "completed")).label("services"),
               avg.label("rating"), status.label("status"), Perfil.registered_at.label("created_at"),
               _count(Servicio, (Servicio.profile_id == Perfil.id) & Servicio.status.in_(
                   ("confirmed", "in_progress", "disputed"))).label("open_services"),
               Perfil.description, Perfil.commune_code
               ).join(Usuario, Usuario.id == Perfil.owner_user_id).where(
        Perfil.kind.in_(("company", "independent_driver")), contains(filters.q, Perfil.name, Perfil.company_tax_id, Usuario.email),
    )
    if filters.kind:
        q = q.where(Perfil.kind == filters.kind)
    if filters.published is not None:
        q = q.where(Perfil.public_activated_at.is_not(None) if filters.published else Perfil.public_activated_at.is_(None))
    if filters.region:
        q = q.join(Commune, Commune.code == Perfil.commune_code).where(Commune.region_code == filters.region)
    return _filtered(q, status, Perfil.registered_at, filters)


def drivers(filters):
    status = _status(Usuario.blocked_at, "blocked")
    assigned = select(func.count()).select_from(ServicioAsignacion).where(
        ServicioAsignacion.driver_id == Conductor.id).correlate(Conductor).scalar_subquery()
    last = select(func.max(Servicio.service_at)).join(ServicioAsignacion, ServicioAsignacion.service_id == Servicio.id).where(
        ServicioAsignacion.driver_id == Conductor.id).correlate(Conductor).scalar_subquery()
    verification = func.coalesce(select(VerificacionIdentidad.status).where(
        VerificacionIdentidad.user_id == Conductor.user_id,
    ).order_by(VerificacionIdentidad.created_at.desc(), VerificacionIdentidad.id.desc()).limit(1).correlate(Conductor).scalar_subquery(), "missing")
    owned = aliased(Perfil)
    kind = case((Conductor.employer_profile_id.is_not(None), "company"), else_="independent")
    profile = func.coalesce(Conductor.employer_profile_id, owned.id)
    q = select(Conductor.id, Usuario.id.label("user_id"), _full_name().label("name"), Usuario.national_id, Usuario.email,
               Usuario.phone, TipoConductor.name.label("type_name"), kind.label("kind"), profile.label("provider_id"),
               func.coalesce(Perfil.name, owned.name).label("provider"), verification.label("verification"),
               assigned.label("services"), last.label("last_service"), status.label("status"),
               Conductor.registered_at.label("created_at")).join(Usuario, Usuario.id == Conductor.user_id).outerjoin(
        Perfil, Perfil.id == Conductor.employer_profile_id,
    ).outerjoin(owned, owned.owner_user_id == Conductor.user_id).outerjoin(TipoConductor, TipoConductor.id == Conductor.driver_type_id).where(
        contains(filters.q, _full_name(), Usuario.national_id, Usuario.email))
    if filters.provider:
        q = q.where(profile == filters.provider)
    if filters.verification:
        q = q.where(verification == filters.verification)
    if filters.kind:
        q = q.where(kind == filters.kind)
    return _filtered(q, status, Conductor.registered_at, filters)


def invitations(filters):
    invitation = DriverInvitation
    status = case((invitation.accepted_at.is_not(None), "accepted"), (invitation.revoked_at.is_not(None), "revoked"),
                  (invitation.expires_at <= utc_now(), "expired"), else_="pending")
    q = select(invitation.id, invitation.target_email.label("email"), Perfil.name.label("provider"),
               invitation.company_profile_id.label("provider_id"), invitation.created_at, invitation.expires_at,
               invitation.accepted_at, invitation.revoked_at, status.label("status"), literal(None).label("attempts")
               ).join(Perfil, Perfil.id == invitation.company_profile_id).where(contains(filters.q, invitation.target_email))
    if filters.provider:
        q = q.where(invitation.company_profile_id == filters.provider)
    return _filtered(q, status, invitation.created_at, filters)


def vehicles(filters):
    status = _status(Vehiculo.disabled_at, "disabled")
    q = select(Vehiculo.id, Vehiculo.plate, Perfil.name.label("provider"), Vehiculo.profile_id.label("provider_id"), Vehiculo.brand,
               Vehiculo.model, Vehiculo.year, Vehiculo.maximum_weight, Vehiculo.registered_at.label("created_at"), status.label("status"),
               _count(ServicioAsignacion, ServicioAsignacion.vehicle_id == Vehiculo.id).label("services")
               ).join(Perfil, Perfil.id == Vehiculo.profile_id).where(contains(filters.q, Vehiculo.plate))
    if filters.provider:
        q = q.where(Vehiculo.profile_id == filters.provider)
    return _filtered(q, status, Vehiculo.registered_at, filters)


QUERIES = {"customers": customers, "providers": providers, "drivers": drivers, "invitations": invitations, "vehicles": vehicles}


def _not_found():
    return HTTPException(404, "No se encontró el registro.")


def _rows(session, query):
    return [dict(row) for row in session.execute(query).mappings()]


def detail(session, entity: str, key: UUID):
    source = QUERIES[entity](ListFilters()).subquery()
    row = session.execute(select(source).where(source.c.id == key)).mappings().one_or_none()
    if not row:
        raise _not_found()
    result = dict(row)
    recent = select(Servicio.id, Servicio.status, Servicio.service_at).order_by(Servicio.created_at.desc()).limit(5)
    if entity == "customers":
        result["recent_services"] = _rows(session, recent.join(FormularioServicio, Servicio.form_id == FormularioServicio.id)
                                           .where(FormularioServicio.customer_id == key))
        result["claims"] = session.scalar(select(func.count()).where(Reclamo.user_id == key)) or 0
        result["service_counts"] = _rows(session, select(Servicio.status, func.count().label("count"))
                                          .join(FormularioServicio, Servicio.form_id == FormularioServicio.id)
                                          .where(FormularioServicio.customer_id == key).group_by(Servicio.status))
        result["refunded"] = session.scalar(select(func.coalesce(func.sum(Reembolso.amount), 0))
                                            .join(Pago, Pago.id == Reembolso.payment_id)
                                            .join(Servicio, Servicio.accepted_quotation_id == Pago.quotation_id)
                                            .join(FormularioServicio, FormularioServicio.id == Servicio.form_id)
                                            .where(FormularioServicio.customer_id == key))
        result["assurance"] = None  # Supabase session assurance cannot be inferred from a marketplace row.
    elif entity == "providers":
        result["recent_services"] = _rows(session, recent.where(Servicio.profile_id == key))
        result["driver_list"] = _rows(session, select(Conductor.id, _full_name().label("name"))
                                       .join(Usuario, Usuario.id == Conductor.user_id)
                                       .where(or_(Conductor.employer_profile_id == key, Usuario.id == select(
                                           Perfil.owner_user_id).where(Perfil.id == key).scalar_subquery()))
                                       .order_by(Usuario.last_name, Conductor.id))
        result["vehicle_list"] = _rows(session, select(Vehiculo.id, Vehiculo.plate, Vehiculo.brand, Vehiculo.model)
                                        .where(Vehiculo.profile_id == key).order_by(Vehiculo.plate))
        result["rating_list"] = _rows(session, select(Valoracion.id, Valoracion.rating, Valoracion.comment, Valoracion.created_at)
                                        .join(Servicio, Servicio.id == Valoracion.service_id).where(Servicio.profile_id == key)
                                        .order_by(Valoracion.created_at.desc()).limit(20))
        result["service_types"] = list(session.scalars(select(ServicioDisponible.service_type_id).where(ServicioDisponible.profile_id == key)))
        result["paid_out"] = session.scalar(select(func.coalesce(func.sum(Desembolso.net_amount), 0)).where(
            Desembolso.beneficiary_profile_id == key, Desembolso.status == "released"))
        result["claims"] = session.scalar(select(func.count()).select_from(Reclamo)
                                         .join(Servicio, Servicio.id == Reclamo.service_id).where(Servicio.profile_id == key)) or 0
        result["bank_status"] = session.scalar(select(CuentaDesembolso.registration_status).where(
            CuentaDesembolso.profile_id == key).order_by(CuentaDesembolso.created_at.desc()).limit(1))
    elif entity == "drivers":
        result["verifications"] = _rows(session, select(VerificacionIdentidad.id, VerificacionIdentidad.status, VerificacionIdentidad.created_at)
                                        .where(VerificacionIdentidad.user_id == result["user_id"]).order_by(VerificacionIdentidad.created_at.desc()))
        result["assignments"] = _rows(session, select(ServicioAsignacion.service_id, ServicioAsignacion.vehicle_id)
                                      .where(ServicioAsignacion.driver_id == key))
    return result


def _locked(session, entity: str, key: UUID):
    model = MODELS[entity]
    query = select(model).where(model.id == key)
    if entity == "customers":
        query = query.join(RolUsuario, RolUsuario.id == Usuario.role_id).where(RolUsuario.code == "client")
    if entity == "invitations":
        profile_id = session.scalar(select(DriverInvitation.company_profile_id).where(DriverInvitation.id == key))
        session.scalar(select(Perfil.id).where(Perfil.id == profile_id).with_for_update())
    value = session.scalar(query.with_for_update())
    if value is None:
        raise _not_found()
    if entity == "drivers":
        return session.scalar(select(Usuario).where(Usuario.id == value.user_id).with_for_update())
    return value


def moderate(session: Session, admin_id: UUID, entity: str, key: UUID, action: str, reason: str | None, edit: dict | None = None):
    reason = reason.strip() if reason else None
    if action in REASON_ACTIONS and (not reason or not 10 <= len(reason) <= 500):
        raise HTTPException(422, "Ingresa un motivo de 10 a 500 caracteres.")
    target = _locked(session, entity, key)
    now = utc_now()
    changes = {}
    if action in STATUS.get(entity, {}):
        column, reason_col, enabled = STATUS[entity][action]
        if (getattr(target, column) is not None) == enabled:
            raise HTTPException(409, "El registro ya se encuentra en ese estado.")
        changes = {column: now if enabled else None, reason_col: reason if enabled else None}
    elif entity == "providers" and action in {"publish", "unpublish"}:
        if (target.public_activated_at is not None) == (action == "publish"):
            raise HTTPException(409, "El perfil ya se encuentra en ese estado.")
        if action == "publish":
            if target.suspended_at is not None:
                raise HTTPException(409, "El perfil está suspendido.")
            service_types = list(session.scalars(select(ServicioDisponible.service_type_id).where(ServicioDisponible.profile_id == key)))
            if _missing_items(session, target, service_types):
                raise HTTPException(409, "El perfil no cumple los requisitos de publicación.")
        changes = {"public_activated_at": now if action == "publish" else None}
    elif entity == "invitations" and action == "revoke":
        # SQLite tests may materialize timezone-aware columns as naive UTC.
        if target.expires_at.tzinfo is None:
            pending = not target.accepted_at and not target.revoked_at and target.expires_at.replace(tzinfo=UTC) > now
        else:
            pending = _invitation_status(target, now) == "pending"
        if not pending:
            raise HTTPException(409, "Solo se puede revocar una invitación pendiente.")
        changes = {"revoked_at": now}
    elif action == "edit" and edit and edit.keys() <= EDIT.get(entity, set()):
        changes = {key: value for key, value in edit.items() if getattr(target, key) != value}
        if not changes:
            raise HTTPException(409, "No hay cambios para guardar.")
        if entity == "providers" and "commune_code" in edit and edit["commune_code"] is not None:
            if session.get(Commune, edit["commune_code"]) is None:
                raise HTTPException(422, "Comuna desconocida.")
    else:
        raise HTTPException(422, "Acción o campos no válidos para el registro.")
    before = {name: getattr(target, name) for name in changes}
    for name, value in changes.items():
        setattr(target, name, value)
    append_audit(session, admin_user_id=admin_id, action=f"{ENTITY[entity]}.{action}", entity_type=ENTITY[entity],
                 entity_id=key, reason=reason, before=before, after=changes)
    session.commit()
