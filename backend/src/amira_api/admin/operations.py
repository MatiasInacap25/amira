"""Operations reporting, audited service/trip changes, and consent-gated chat access."""

from dataclasses import asdict
from typing import Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, exists, func, literal, or_, select
from sqlalchemy.orm import Session, aliased

from amira_api.admin.audit import append_audit
from amira_api.admin.claim_service import require_reason
from amira_api.admin.listing import ListFilters, contains
from amira_api.admin.people import _date_filter
from amira_api.admin.review import _signed_url
from amira_api.clock import utc_now
from amira_api.evidence_storage import EvidenceStorage
from amira_api.models import (
    Chat, ChatParticipante, Commune, Conductor, Cotizacion, Desembolso, FormularioServicio, ImagenFormulario,
    Mensaje, Pago, ParadaViaje, Perfil, Reclamo, Region, Servicio, ServicioAsignacion, ServicioUbicacion, TipoServicio,
    Usuario, Vehiculo, Viaje, ViajeVehiculo,
)
from amira_api.payment_service import APPROVED
from amira_api.payout_service import _due_conditions
from amira_api.service_cancellation import cancel_service
from amira_api.service_views import load_assignments
from amira_api.settings import Settings
from amira_api.shared_trip_service import close_shared_trip
from amira_api.simulated_payment_provider import SIMULATOR_APP_ENVS
from amira_api.tax import amount_breakdown

TRANSCRIPT_LIMIT = 30


def _name(person):
    return person.first_name + literal(" ") + person.last_name


def _names(session: Session, column):
    return func.group_concat(column, ", ") if session.get_bind().dialect.name == "sqlite" else func.string_agg(column, ", ")


def _statuses(query, status, filters):
    return query.where(status == filters.status) if filters.status else query


def _rows(session, query):
    return [dict(row) for row in session.execute(query).mappings()]


def _amounts(query, column, filters):
    if filters.minimum_amount is not None:
        query = query.where(column >= filters.minimum_amount)
    if filters.maximum_amount is not None:
        query = query.where(column <= filters.maximum_amount)
    return query


def requests(session: Session, filters: ListFilters):
    req = FormularioServicio
    origin = aliased(Commune)
    destination = aliased(Commune)
    quotes = select(func.count(Cotizacion.id)).join(Chat, Chat.id == Cotizacion.chat_id).where(
        Chat.form_id == req.id).correlate(req).scalar_subquery()
    query = (
        select(req.id, _name(Usuario).label("customer"), Perfil.name.label("provider"), req.profile_id.label("provider_id"),
               TipoServicio.name.label("service_type"), func.coalesce(origin.name, req.origin).label("origin"),
               func.coalesce(destination.name, req.destination).label("destination"), req.requested_at, req.created_at,
               req.status, quotes.label("quotes"))
        .join(Usuario, Usuario.id == req.customer_id).outerjoin(Perfil, Perfil.id == req.profile_id)
        .join(TipoServicio, TipoServicio.id == req.service_type_id)
        .outerjoin(origin, origin.code == req.origin_commune_code).outerjoin(destination, destination.code == req.destination_commune_code)
        .where(contains(filters.q, _name(Usuario), Perfil.name, origin.name, destination.name, req.origin, req.destination))
    )
    if filters.region:
        query = query.where(or_(origin.region_code == filters.region, destination.region_code == filters.region))
    if filters.service_type:
        query = query.where(req.service_type_id == filters.service_type)
    if filters.provider:
        query = query.where(req.profile_id == filters.provider)
    if filters.customer:
        query = query.where(req.customer_id == filters.customer)
    return _date_filter(_statuses(query, req.status, filters), req.requested_at, filters)


def quotations(session: Session, filters: ListFilters):
    quote = Cotizacion
    req = FormularioServicio
    status = case((and_(quote.status == "pending", quote.expires_at <= utc_now()), "expired"), else_=quote.status)
    query = (
        select(quote.id, req.id.label("request_id"), _name(Usuario).label("customer"),
               Perfil.name.label("provider"), req.profile_id.label("provider_id"), quote.amount, status.label("status"), quote.expires_at,
               quote.created_at, quote.description, quote.is_exclusive, quote.origin, quote.destination)
        .join(Chat, Chat.id == quote.chat_id).join(req, req.id == Chat.form_id)
        .join(Usuario, Usuario.id == req.customer_id).outerjoin(Perfil, Perfil.id == req.profile_id)
        .where(contains(filters.q, _name(Usuario), Perfil.name))
    )
    if filters.request:
        query = query.where(req.id == filters.request)
    if filters.provider:
        query = query.where(req.profile_id == filters.provider)
    return _amounts(_date_filter(_statuses(query, status, filters), quote.created_at, filters), quote.amount, filters)


def services(session: Session, filters: ListFilters):
    srv = Servicio
    names = select(_names(session, _name(Usuario))).select_from(ServicioAsignacion).join(
        Conductor, Conductor.id == ServicioAsignacion.driver_id).join(Usuario, Usuario.id == Conductor.user_id).where(
        ServicioAsignacion.service_id == srv.id).correlate(srv).scalar_subquery()
    plates = select(_names(session, Vehiculo.plate)).select_from(ServicioAsignacion).join(
        Vehiculo, Vehiculo.id == ServicioAsignacion.vehicle_id).where(
        ServicioAsignacion.service_id == srv.id).correlate(srv).scalar_subquery()
    pay = select(Pago.status).where(Pago.quotation_id == srv.accepted_quotation_id).order_by(
        (Pago.status == APPROVED).desc(), Pago.created_at.desc(), Pago.id.desc()).limit(1).correlate(srv).scalar_subquery()
    payment_id = select(Pago.id).where(Pago.quotation_id == srv.accepted_quotation_id).order_by(
        (Pago.status == APPROVED).desc(), Pago.created_at.desc(), Pago.id.desc()).limit(1).correlate(srv).scalar_subquery()
    payout_id = select(Desembolso.id).where(Desembolso.service_id == srv.id).limit(1).correlate(srv).scalar_subquery()
    claim_id = select(Reclamo.id).where(Reclamo.service_id == srv.id).order_by(Reclamo.created_at.desc(), Reclamo.id.desc()).limit(1).correlate(srv).scalar_subquery()
    payout = select(Desembolso.status).where(Desembolso.service_id == srv.id).limit(1).correlate(srv).scalar_subquery()
    claim = exists().where(Reclamo.service_id == srv.id).correlate(srv)
    query = (
        select(srv.id, _name(Usuario).label("customer"), Perfil.name.label("provider"), Perfil.id.label("provider_id"),
               names.label("drivers"), plates.label("vehicles"), Cotizacion.origin, Cotizacion.destination, srv.amount,
               srv.starts_at, srv.completed_at, srv.created_at, srv.service_at, srv.status, pay.label("payment_status"),
               payout.label("payout_status"), srv.is_exclusive, srv.trip_id, srv.accepted_quotation_id.label("quotation_id"),
               payment_id.label("payment_id"), payout_id.label("payout_id"), claim_id.label("claim_id"), Cotizacion.chat_id,
               srv.form_id.label("request_id"))
        .join(Usuario, Usuario.id == srv.customer_id).join(Perfil, Perfil.id == srv.profile_id)
        .join(Cotizacion, Cotizacion.id == srv.accepted_quotation_id)
        .where(contains(filters.q, cast(srv.id, String), _name(Usuario), Perfil.name, plates))
    )
    if filters.provider:
        query = query.where(srv.profile_id == filters.provider)
    if filters.customer:
        query = query.where(srv.customer_id == filters.customer)
    if filters.driver:
        query = query.where(or_(srv.contracted_driver_id == filters.driver, exists().where(
            ServicioAsignacion.service_id == srv.id, ServicioAsignacion.driver_id == filters.driver)))
    if filters.exclusive is not None:
        query = query.where(srv.is_exclusive.is_(filters.exclusive))
    if filters.has_claim is not None:
        query = query.where(claim if filters.has_claim else ~claim)
    if filters.payout_due is not None:
        due = and_(*_due_conditions(utc_now()), exists().where(Pago.quotation_id == srv.accepted_quotation_id, Pago.status == APPROVED))
        query = query.where(due if filters.payout_due else ~due)
    return _date_filter(_statuses(query, srv.status, filters), srv.service_at, filters)


def chats(session: Session, filters: ListFilters):
    participants = select(_names(session, _name(Usuario))).select_from(ChatParticipante).join(
        Usuario, Usuario.id == ChatParticipante.user_id).where(ChatParticipante.chat_id == Chat.id).correlate(Chat).scalar_subquery()
    last = select(func.max(Mensaje.created_at)).where(Mensaje.chat_id == Chat.id).correlate(Chat).scalar_subquery()
    messages = select(func.count(Mensaje.id)).where(Mensaje.chat_id == Chat.id).correlate(Chat).scalar_subquery()
    linked = select(Servicio.id).join(Cotizacion, Cotizacion.id == Servicio.accepted_quotation_id).where(
        Cotizacion.chat_id == Chat.id).order_by(Servicio.created_at.desc(), Servicio.id.desc()).limit(1).correlate(Chat).scalar_subquery()
    has_claim = exists(select(Reclamo.id).join(Servicio, Servicio.id == Reclamo.service_id)
                       .join(Cotizacion, Cotizacion.id == Servicio.accepted_quotation_id).where(Cotizacion.chat_id == Chat.id)).correlate(Chat)
    query = select(Chat.id, Chat.form_id.label("request_id"), linked.label("service_id"),
                   participants.label("participants"), last.label("last_message_at"), messages.label("messages"),
                   Chat.created_at, has_claim.label("has_claim")).select_from(Chat).where(
        contains(filters.q, participants, cast(Chat.id, String)))
    if filters.service:
        query = query.where(linked == filters.service)
    if filters.request:
        query = query.where(Chat.form_id == filters.request)
    return query


def trips(session: Session, filters: ListFilters):
    trip = Viaje
    source, target = aliased(Commune), aliased(Commune)
    origin, destination = aliased(Region), aliased(Region)
    attached = select(func.count(Servicio.id)).where(Servicio.trip_id == trip.id).correlate(trip).scalar_subquery()
    stops = select(func.count(ParadaViaje.id)).where(ParadaViaje.trip_id == trip.id).correlate(trip).scalar_subquery()
    query = (
        select(trip.id, Perfil.name.label("provider"), Perfil.id.label("provider_id"),
               func.coalesce(origin.name, trip.origin).label("origin"), func.coalesce(destination.name, trip.destination).label("destination"),
               trip.departure_at, trip.status, trip.is_published.label("published"), trip.accepts_requests,
               attached.label("services"), stops.label("stops"), trip.registered_at.label("created_at"))
        .join(Perfil, Perfil.id == trip.profile_id)
        .outerjoin(source, source.code == trip.origin_commune_code).outerjoin(target, target.code == trip.destination_commune_code)
        .outerjoin(origin, origin.code == source.region_code).outerjoin(destination, destination.code == target.region_code)
        .where(contains(filters.q, Perfil.name))
    )
    if filters.published is not None:
        query = query.where(trip.is_published.is_(filters.published))
    if filters.accepts_requests is not None:
        query = query.where(trip.accepts_requests.is_(filters.accepts_requests))
    return _date_filter(_statuses(query, trip.status, filters), trip.departure_at, filters)


QUERIES = {"requests": requests, "quotations": quotations, "services": services, "chats": chats, "trips": trips}


def breakdown(row: dict, settings: Settings):
    if row.get("amount") is not None:
        amounts = asdict(amount_breakdown(int(row["amount"]), settings.payout_commission_percent))
        row.update({key: amounts[key] for key in ("net", "iva", "commission", "carrier_amount")})
    return row


def _trip_details(session: Session, trip_id: UUID):
    jobs = _rows(session, select(Servicio.id, Servicio.pickup_stop_id, Servicio.delivery_stop_id,
                                _name(Usuario).label("customer"), Servicio.status).join(
        Usuario, Usuario.id == Servicio.customer_id).where(Servicio.trip_id == trip_id))
    stops = _rows(session, select(ParadaViaje.id, ParadaViaje.order, ParadaViaje.address, ParadaViaje.estimated_at)
                  .where(ParadaViaje.trip_id == trip_id).order_by(ParadaViaje.order, ParadaViaje.id))
    roles = {}
    for job in jobs:
        roles.setdefault(job["pickup_stop_id"], []).append(f"Retiro de {job['customer']}")
        roles.setdefault(job["delivery_stop_id"], []).append(f"Entrega de {job['customer']}")
    for index, stop in enumerate(stops):
        stop["role"] = " / ".join(roles.get(stop["id"], [])) or (
            "Origen" if index == 0 else "Destino" if index == len(stops) - 1 else "Parada intermedia")
    crew = _rows(session, select(Vehiculo.plate, Vehiculo.brand, Vehiculo.model, _name(Usuario).label("driver"))
                 .select_from(ViajeVehiculo).join(Vehiculo, Vehiculo.id == ViajeVehiculo.vehicle_id)
                 .join(Conductor, Conductor.id == ViajeVehiculo.driver_id).join(Usuario, Usuario.id == Conductor.user_id)
                 .where(ViajeVehiculo.trip_id == trip_id))
    return {"ordered_stops": stops, "linked_services": jobs, "assigned_crew": crew}


def detail(session: Session, entity: str, key: UUID, settings: Settings,
           request_storage: Callable[[], EvidenceStorage], service_storage: Callable[[], EvidenceStorage]):
    base = QUERIES[entity](session, ListFilters()).subquery()
    row = session.execute(select(base).where(base.c.id == key)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "No se encontró el registro.")
    result = dict(row)
    if entity == "requests":
        req = session.get(FormularioServicio, key)
        result.update(description=req.description, origin_address=req.origin, destination_address=req.destination,
                      cargo_measurements=req.cargo_measurements, estimated_weight=req.estimated_weight,
                      estimated_volume=req.estimated_volume, is_exclusive=req.is_exclusive)
        result["images"] = [url for storage_key in session.scalars(select(ImagenFormulario.private_storage_key)
                            .where(ImagenFormulario.form_id == key).order_by(ImagenFormulario.id).limit(20))
                            if (url := _signed_url(request_storage, storage_key, settings.request_image_url_ttl_seconds))]
        result["linked_quotes"] = _rows(session, select(Cotizacion.id, Cotizacion.amount, Cotizacion.status)
                                        .join(Chat, Chat.id == Cotizacion.chat_id).where(Chat.form_id == key)
                                        .order_by(Cotizacion.created_at.desc()).limit(20))
    elif entity == "quotations":
        breakdown(result, settings)
        result["payment_id"] = session.scalar(select(Pago.id).where(Pago.quotation_id == key, Pago.status == APPROVED).limit(1))
    elif entity == "services":
        service = session.get(Servicio, key)
        result.update(payment_confirmed_at=service.payment_confirmed_at, cancelled_at=service.cancelled_at,
                      contractual_amount=service.amount, assignments=[item.model_dump() for item in load_assignments(session, key)],
                      request_id=service.form_id,
                      delivery_url=_signed_url(service_storage, service.delivery_evidence_key, settings.service_evidence_url_ttl_seconds))
        location = session.get(ServicioUbicacion, key)
        if location:
            result["last_location"] = {"latitude": location.latitude, "longitude": location.longitude,
                                       "accuracy_meters": location.accuracy_meters, "updated_at": location.updated_at}
        if service.trip_id is not None:
            result.update(_trip_details(session, service.trip_id))
        breakdown(result, settings)
    elif entity == "trips":
        result.update(_trip_details(session, key))
    return result


def transcript(session: Session, chat_id: UUID, admin_id: UUID, reason: str | None, before: UUID | None,
               attachment_storage: Callable[[], EvidenceStorage], settings: Settings):
    chat = session.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(404, "No se encontró el chat.")
    has_claim = session.scalar(select(Reclamo.id).join(Servicio, Servicio.id == Reclamo.service_id)
                               .join(Cotizacion, Cotizacion.id == Servicio.accepted_quotation_id)
                               .where(Cotizacion.chat_id == chat.id).limit(1)) is not None
    if not has_claim:
        if not reason:
            raise HTTPException(403, "Ingresa un motivo para acceder a esta conversación.")
        reason = require_reason(reason)
    query = select(Mensaje, _name(Usuario)).join(Usuario, Usuario.id == Mensaje.user_id).where(Mensaje.chat_id == chat_id)
    if before:
        cursor = session.scalar(select(Mensaje).where(Mensaje.id == before, Mensaje.chat_id == chat_id))
        if cursor is None:
            raise HTTPException(422, "Cursor inválido para esta conversación.")
        query = query.where(or_(Mensaje.created_at < cursor.created_at,
                                and_(Mensaje.created_at == cursor.created_at, Mensaje.id < cursor.id)))
    rows = session.execute(query.order_by(Mensaje.created_at.desc(), Mensaje.id.desc()).limit(TRANSCRIPT_LIMIT + 1)).all()
    window = rows[:TRANSCRIPT_LIMIT]
    append_audit(session, admin_user_id=admin_id, action="chat.access", entity_type="chat",
                 entity_id=chat.id, reason=reason, after={"has_claim": has_claim})
    session.commit()
    return {
        "items": [{"id": row.id, "sender": sender, "text": row.content, "created_at": row.created_at,
                   "attachment_url": _signed_url(attachment_storage, row.attachment_key, settings.chat_attachment_url_ttl_seconds)}
                  for row, sender in reversed(window)],
        "before": window[-1][0].id if len(rows) > TRANSCRIPT_LIMIT else None,
    }


def cancel_admin_service(session: Session, key: UUID, admin_id: UUID, reason: str | None, settings: Settings):
    reason = require_reason(reason)
    if "app_env" not in settings.model_fields_set or settings.app_env.strip().lower() not in SIMULATOR_APP_ENVS:
        raise HTTPException(503, "El reembolso simulado no está habilitado.")
    service = session.scalar(select(Servicio).where(Servicio.id == key).with_for_update().execution_options(populate_existing=True))
    if service is None:
        raise HTTPException(404, "No se encontró el servicio.")
    if service.status != "confirmed" or service.starts_at is not None:
        raise HTTPException(409, "Solo se pueden cancelar servicios confirmados que no hayan comenzado.")
    cancel_service(session, key, "admin")
    append_audit(session, admin_user_id=admin_id, action="service.cancel", entity_type="service", entity_id=key,
                 reason=reason, before={"status": "confirmed"}, after={"status": service.status,
                 "refunded_amount": service.cancellation_refunded_amount, "retained_amount": service.cancellation_retained_amount})
    session.commit()


def change_trip(session: Session, key: UUID, admin_id: UUID, action: str, reason: str | None):
    if action == "unpublish":
        reason = require_reason(reason)
    trip = session.scalar(select(Viaje).where(Viaje.id == key).with_for_update())
    if trip is None:
        raise HTTPException(404, "No se encontró el viaje.")
    prior = {"published": trip.is_published, "accepts_requests": trip.accepts_requests}
    if action == "unpublish" and trip.is_published:
        trip.is_published = False
    elif action == "close" and trip.accepts_requests:
        close_shared_trip(trip)
    else:
        raise HTTPException(409, "El viaje ya se encuentra en ese estado.")
    append_audit(session, admin_user_id=admin_id, action=f"trip.{action}", entity_type="trip", entity_id=key,
                 reason=reason, before=prior, after={"published": trip.is_published, "accepts_requests": trip.accepts_requests})
    session.commit()
