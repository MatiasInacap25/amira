"""Test helper: mark a driver's two certificates as verified, as a clean Verifik submission would."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from amira_api.models import VerificacionIdentidad


def verify_driver(db: Session, user_id: UUID) -> None:
    now = datetime.now(UTC)
    for document_type in ("criminal_record", "driver_record"):
        db.add(VerificacionIdentidad(
            id=uuid4(), user_id=user_id, provider="simulated", provider_verification_id=uuid4().hex[:15],
            status="verified", document_type=document_type, verified_at=now, created_at=now, updated_at=now,
        ))


def unverify_driver(db: Session, user_id: UUID) -> None:
    db.execute(delete(VerificacionIdentidad).where(VerificacionIdentidad.user_id == user_id))
    db.commit()
