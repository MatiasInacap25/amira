"""Manual review of driver certificates that Verifik found authentic but with annotations.

Only a certificate in review can be decided. Approving it marks it verified (the driver becomes verified once both
certificates are); rejecting it stores the reviewer's reason, which the driver sees, and lets them submit another
certificate of that type. The row is locked while it changes, so two reviewers cannot decide it twice.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.models import Usuario, VerificacionIdentidad


class ReviewRefused(Exception):
    """The decision cannot be applied. The message is user-facing Spanish."""


@dataclass(frozen=True)
class PendingReview:
    id: UUID
    holder: str
    rut: str | None
    document_type: str | None
    folio: str
    submitted_at: datetime
    annotations: list[dict[str, Any]]
    pdf_storage_key: str | None


def pending_reviews(session: Session) -> list[PendingReview]:
    rows = session.execute(
        select(VerificacionIdentidad, Usuario)
        .join(Usuario, Usuario.id == VerificacionIdentidad.user_id)
        .where(VerificacionIdentidad.status == "in_review")
        .order_by(VerificacionIdentidad.created_at, VerificacionIdentidad.id)
    ).all()
    return [
        PendingReview(
            id=row.id,
            holder=f"{user.first_name} {user.last_name}",
            rut=user.national_id,
            document_type=row.document_type,
            folio=row.provider_verification_id,
            submitted_at=row.created_at,
            annotations=list(row.annotations or []),
            pdf_storage_key=row.pdf_storage_key,
        )
        for row, user in rows
    ]


def _locked_in_review(session: Session, certificate_id: UUID) -> VerificacionIdentidad:
    row = session.execute(
        select(VerificacionIdentidad).where(VerificacionIdentidad.id == certificate_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise ReviewRefused("No existe un certificado con ese ID.")
    if row.status != "in_review":
        raise ReviewRefused(f"El certificado no está en revisión (estado: {row.status}).")
    return row


def approve_certificate(session: Session, certificate_id: UUID, now: datetime) -> None:
    try:
        row = _locked_in_review(session, certificate_id)
        row.status = "verified"
        row.rejection_reason = None
        row.verified_at = now
        row.reviewed_at = now
        row.updated_at = now
        session.commit()
    except ReviewRefused:
        session.rollback()
        raise


def reject_certificate(session: Session, certificate_id: UUID, reason: str, now: datetime) -> None:
    reason = reason.strip()
    try:
        if not reason:
            raise ReviewRefused("Indica el motivo del rechazo; el conductor lo verá.")
        row = _locked_in_review(session, certificate_id)
        row.status = "rejected"
        row.rejection_reason = reason
        row.reviewed_at = now
        row.updated_at = now
        session.commit()
    except ReviewRefused:
        session.rollback()
        raise
