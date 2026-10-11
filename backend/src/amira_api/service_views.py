"""Query and shaping logic for contracted services, shared by the customer and provider routes.

Callers add their own visibility filter to ``service_rows``; the page total and the page items use the
same relation, so the total never counts a service the item query cannot return.
"""

from typing import Literal
from uuid import UUID

from datetime import timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, aliased

from amira_api.clock import utc_now
from amira_api.evidence_storage import EvidenceStorage
from amira_api.models import (
    Commune,
    Conductor,
    Cotizacion,
    FormularioServicio,
    Perfil,
    Servicio,
    ServicioAsignacion,
    TipoServicio,
    Usuario,
    Vehiculo,
)
from amira_api.provider_service_schemas import DeliveryPhotoUrl, ServiceAssignment, ServiceDetail, ServiceListItem

DELIVERY_PHOTO_LINK_MESSAGE = "The delivery photo could not be retrieved. Try again."
PROVIDER_FALLBACK_NAME = "Prestador"
CUSTOMER_FALLBACK_NAME = "Cliente"
ViewerRole = Literal["customer", "provider"]

_provider_owner = aliased(Usuario)
_customer = aliased(Usuario)
_origin_commune = aliased(Commune)
_destination_commune = aliased(Commune)


def provider_display_name(kind: str, profile_name: str | None, first_name: str | None, last_name: str | None) -> str:
    """Return a non-empty provider name; independent drivers use their real name, never the profile handle."""
    if kind == "independent_driver":
        name = " ".join(part.strip() for part in (first_name, last_name) if part and part.strip())
    else:
        name = (profile_name or "").strip()
    return name or PROVIDER_FALLBACK_NAME


def _service_relation(statement: Select) -> Select:
    return (
        statement.select_from(Servicio)
        .join(Cotizacion, Cotizacion.id == Servicio.accepted_quotation_id)
        .join(FormularioServicio, FormularioServicio.id == Servicio.form_id)
        .join(TipoServicio, TipoServicio.id == FormularioServicio.service_type_id)
        .join(Perfil, Perfil.id == Servicio.profile_id)
        .join(_provider_owner, _provider_owner.id == Perfil.owner_user_id)
        .join(_customer, _customer.id == Servicio.customer_id)
        .outerjoin(_origin_commune, _origin_commune.code == FormularioServicio.origin_commune_code)
        .outerjoin(_destination_commune, _destination_commune.code == FormularioServicio.destination_commune_code)
    )


def service_count(*conditions) -> Select:
    return _service_relation(select(func.count(Servicio.id))).where(*conditions)


def service_rows(*conditions) -> Select:
    assignment_count = (
        select(func.count(ServicioAsignacion.id))
        .where(ServicioAsignacion.service_id == Servicio.id)
        .correlate(Servicio)
        .scalar_subquery()
    )
    return _service_relation(
        select(
            Servicio.id.label("service_id"),
            Servicio.status.label("status"),
            TipoServicio.name.label("service_type_name"),
            Servicio.service_at.label("service_at"),
            Servicio.amount.label("amount"),
            Cotizacion.currency.label("currency"),
            Cotizacion.chat_id.label("chat_id"),
            _origin_commune.name.label("origin_commune"),
            _destination_commune.name.label("destination_commune"),
            Servicio.is_exclusive.label("is_exclusive"),
            Servicio.description.label("description"),
            Servicio.created_at.label("created_at"),
            Servicio.starts_at.label("started_at"),
            Servicio.completed_at.label("completed_at"),
            Servicio.payout_deadline_at.label("payout_deadline_at"),
            Servicio.delivery_evidence_key.label("delivery_evidence_key"),
            Perfil.kind.label("provider_kind"),
            Perfil.name.label("profile_name"),
            _provider_owner.first_name.label("owner_first_name"),
            _provider_owner.last_name.label("owner_last_name"),
            _customer.first_name.label("customer_first_name"),
            assignment_count.label("assignment_count"),
        )
    ).where(*conditions)


def _counterpart_name(row, viewer_role: ViewerRole) -> str:
    if viewer_role == "customer":
        return provider_display_name(
            row["provider_kind"], row["profile_name"], row["owner_first_name"], row["owner_last_name"]
        )
    return (row["customer_first_name"] or "").strip() or CUSTOMER_FALLBACK_NAME


def _list_fields(row, viewer_role: ViewerRole) -> dict:
    return {
        "service_id": row["service_id"],
        "status": row["status"],
        "service_type_name": row["service_type_name"],
        "service_at": row["service_at"],
        "amount": int(row["amount"]) if row["amount"] is not None else None,
        "currency": row["currency"],
        "origin_commune": row["origin_commune"],
        "destination_commune": row["destination_commune"],
        "is_exclusive": row["is_exclusive"],
        "counterpart_name": _counterpart_name(row, viewer_role),
        "assignment_count": row["assignment_count"],
    }


def shape_list_item(row, viewer_role: ViewerRole) -> ServiceListItem:
    return ServiceListItem(**_list_fields(row, viewer_role))


def load_assignments(session: Session, service_id: UUID) -> list[ServiceAssignment]:
    rows = session.execute(
        select(
            Conductor.id.label("driver_id"),
            Usuario.first_name.label("driver_first_name"),
            Vehiculo.id.label("vehicle_id"),
            Vehiculo.brand.label("brand"),
            Vehiculo.model.label("model"),
            Vehiculo.plate.label("plate"),
        )
        .select_from(ServicioAsignacion)
        .join(Conductor, Conductor.id == ServicioAsignacion.driver_id)
        .join(Usuario, Usuario.id == Conductor.user_id)
        .join(Vehiculo, Vehiculo.id == ServicioAsignacion.vehicle_id)
        .where(ServicioAsignacion.service_id == service_id)
        .order_by(ServicioAsignacion.assigned_at, ServicioAsignacion.id)
    ).mappings().all()
    return [
        ServiceAssignment(
            driver_id=row["driver_id"],
            driver_first_name=row["driver_first_name"],
            vehicle_id=row["vehicle_id"],
            vehicle_label=f"{row['brand']} {row['model']}".strip(),
            plate=row["plate"],
        )
        for row in rows
    ]


def shape_detail(
    row, viewer_role: ViewerRole, *, can_manage: bool, assignments: list[ServiceAssignment]
) -> ServiceDetail:
    return ServiceDetail(
        **_list_fields(row, viewer_role),
        chat_id=row["chat_id"],
        description=row["description"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        payout_deadline_at=row["payout_deadline_at"],
        viewer_role=viewer_role,
        can_manage=can_manage,
        delivery_photo_available=row["delivery_evidence_key"] is not None,
        assignments=assignments,
    )


def signed_delivery_photo(storage: EvidenceStorage, key: str, ttl_seconds: int) -> DeliveryPhotoUrl:
    """A short-lived read URL for the completion photo. The key itself never leaves the server."""
    return DeliveryPhotoUrl(
        url=storage.create_signed_url(key, ttl_seconds),
        expires_at=utc_now() + timedelta(seconds=ttl_seconds),
    )
