"""Whether a driver is verified, read from Verificacion_Identidad.

A driver is verified when both certificate types have a verified row. New submissions are refused while a
certificate of that type is verified or in review, and an administrator changes a row's status in place, so a
verified row is always the latest of its type: "a verified row exists" and "the latest row is verified" agree.
"""

from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, select
from sqlalchemy.orm import Session

from amira_api.driver_certificates import CERTIFICATE_TYPES
from amira_api.models import VerificacionIdentidad


def latest_certificates(session: Session, user_id: UUID) -> dict[str, VerificacionIdentidad]:
    rows = session.execute(
        select(VerificacionIdentidad)
        .where(VerificacionIdentidad.user_id == user_id, VerificacionIdentidad.document_type.in_(CERTIFICATE_TYPES))
        .order_by(VerificacionIdentidad.created_at.desc(), VerificacionIdentidad.id.desc())
    ).scalars()
    latest: dict[str, VerificacionIdentidad] = {}
    for row in rows:
        latest.setdefault(row.document_type, row)
    return latest


def verified_driver_condition(user_id: ColumnElement[UUID] | UUID) -> ColumnElement[bool]:
    """SQL condition: the user behind ``user_id`` (a column or a value) has both certificates verified."""
    return and_(*(
        exists().where(
            VerificacionIdentidad.user_id == user_id,
            VerificacionIdentidad.document_type == document_type,
            VerificacionIdentidad.status == "verified",
        )
        for document_type in CERTIFICATE_TYPES
    ))


def is_driver_verified(session: Session, user_id: UUID) -> bool:
    return bool(session.execute(select(verified_driver_condition(user_id))).scalar_one_or_none())
