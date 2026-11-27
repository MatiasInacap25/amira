"""Catalog projections and audited edits of service types."""

import re
import unicodedata
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import String, case, cast, delete, exists, literal, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amira_api.admin.audit import append_audit
from amira_api.admin.listing import ListFilters, contains
from amira_api.clock import utc_now
from amira_api.models import Commune, Cotizacion, FormularioServicio, Region, RolPerfil, RolUsuario, ServicioDisponible, TipoConductor, TipoServicio
from amira_api.service_type_visibility import hidden_service_type_clause


def _referenced(identifier):
    return or_(
        exists().where(ServicioDisponible.service_type_id == identifier),
        exists().where(FormularioServicio.service_type_id == identifier),
        exists().where(Cotizacion.service_type_id == identifier),
    )


def service_types(filters: ListFilters):
    state = case((hidden_service_type_clause(), "inactive"), else_="active")
    query = select(TipoServicio.id, TipoServicio.name, TipoServicio.slug, TipoServicio.description,
                   state.label("status"), _referenced(TipoServicio.id).label("referenced")).where(
        contains(filters.q, TipoServicio.name, TipoServicio.slug, TipoServicio.description))
    return query.where(state == filters.status) if filters.status else query


def driver_types(filters: ListFilters):
    return select(TipoConductor.id, TipoConductor.name).where(contains(filters.q, TipoConductor.name))


def locations(filters: ListFilters):
    regions = select((literal("region:") + Region.code).label("id"), Region.code, Region.name,
                     literal("region").label("kind"), Region.name.label("region"))
    communes = select((literal("commune:") + Commune.code).label("id"), Commune.code, Commune.name,
                      literal("commune").label("kind"), Region.name.label("region")).join(Region, Region.code == Commune.region_code)
    data = union_all(regions, communes).subquery()
    return select(data).where(contains(filters.q, data.c.name, data.c.code, data.c.region))


def roles(filters: ListFilters):
    accounts = select((literal("user:") + cast(RolUsuario.id, String)).label("id"),
                      RolUsuario.name, RolUsuario.code, literal("user").label("kind"))
    profiles = select((literal("profile:") + cast(RolPerfil.id, String)).label("id"),
                      RolPerfil.name, RolPerfil.code, literal("profile").label("kind"))
    data = union_all(accounts, profiles).subquery()
    return select(data).where(contains(filters.q, data.c.name, data.c.code))


QUERIES = {"service-types": service_types, "driver-types": driver_types, "locations": locations, "roles": roles}


def detail(session: Session, kind: str, identifier: str):
    if kind in {"service-types", "driver-types"}:
        try:
            identifier = UUID(identifier)
        except ValueError as error:
            raise HTTPException(404, "No se encontró el registro.") from error
    source = QUERIES[kind](ListFilters()).subquery()
    row = session.execute(select(source).where(source.c.id == identifier)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "No se encontró el registro.")
    return dict(row)


def _slug(value: str):
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")
    if not slug or len(slug) > 120:
        raise HTTPException(422, "El nombre no permite generar un identificador válido.")
    return slug


def _commit(session: Session, message: str):
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, message) from error


def create_service_type(session: Session, admin_id: UUID, fields: dict):
    slug = _slug(fields["name"])
    if session.scalar(select(TipoServicio.id).where(or_(TipoServicio.name == fields["name"], TipoServicio.slug == slug))) is not None:
        raise HTTPException(409, "Ya existe un tipo de servicio con ese nombre o identificador.")
    row = TipoServicio(id=uuid4(), name=fields["name"], slug=slug, description=fields.get("description"))
    session.add(row)
    append_audit(session, admin_user_id=admin_id, action="service_type.create", entity_type="service_type",
                 entity_id=row.id, after={"name": row.name, "slug": slug, "description": row.description})
    identifier = row.id
    _commit(session, "Ya existe un tipo de servicio con ese nombre o identificador.")
    return identifier


def change_service_type(session: Session, admin_id: UUID, identifier: UUID, action: str, fields: dict | None = None):
    row = session.scalar(select(TipoServicio).where(TipoServicio.id == identifier).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "No se encontró el tipo de servicio.")
    before = {"name": row.name, "slug": row.slug, "description": row.description, "deactivated_at": row.deactivated_at}
    conflict = "Ya existe un tipo de servicio con ese nombre."
    if action == "edit":
        changes = {key: value for key, value in (fields or {}).items() if key in {"name", "description"} and value != before[key]}
        if not changes:
            raise HTTPException(409, "No hay cambios para guardar.")
        for key, value in changes.items():
            setattr(row, key, value)
        before = {key: before[key] for key in changes}
        after = changes
    elif action == "deactivate":
        if row.deactivated_at is not None:
            raise HTTPException(409, "El tipo de servicio ya está desactivado.")
        row.deactivated_at = utc_now()
        before = {"deactivated_at": before["deactivated_at"]}
        after = {"deactivated_at": row.deactivated_at}
    elif action == "delete":
        conflict = "Este tipo está referenciado y no se puede eliminar. Puedes desactivarlo."
        if session.scalar(select(_referenced(identifier))):
            raise HTTPException(409, conflict)
        after = None
    else:
        raise HTTPException(422, "Acción no válida.")
    append_audit(session, admin_user_id=admin_id, action=f"service_type.{action}", entity_type="service_type",
                 entity_id=identifier, before=before, after=after)
    if action == "delete":
        try:
            session.execute(delete(TipoServicio).where(TipoServicio.id == identifier))
        except IntegrityError as error:
            session.rollback()
            raise HTTPException(409, conflict) from error
    _commit(session, conflict)
