"""Driver verification: drivers submit their two Registro Civil certificates, which the CertificateVerifier checks.

Any user with a Conductor row is a driver here: independent drivers, company drivers and company owners who also
drive. Each certificate is sent as its folio and verification code; the verifier returns the holder's RUN, the
registers and (Verifik) the official PDF, which is kept in the private DRIVER_CERTIFICATES_BUCKET.

This module is the composition root for the CertificateVerifier port: Verifik when VERIFIK_API_TOKEN is set, the
simulator only when VERIFIK_SIMULATOR is on and APP_ENV is set explicitly to development, local or test. Anything
else answers 503, so a missing configuration never verifies a driver.

The external call runs with no database transaction open. The user row is then locked and the "can submit" and
"folio unused" checks run again before the insert, so two concurrent submissions cannot both be stored.
"""

import logging
from collections.abc import Callable
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.driver_certificates import (
    CERTIFICATE_TYPES,
    CertificateInvalid,
    CertificateNotFound,
    CertificateVerifier,
    VerifikUnavailable,
    classify_certificate,
)
from amira_api.driver_verification import is_driver_verified, latest_certificates
from amira_api.driver_verification_schemas import CertificateStatusItem, CertificateSubmission, DriverVerificationView
from amira_api.evidence_storage import EvidenceStorage, EvidenceStorageError, _supabase_storage
from amira_api.models import Conductor, Usuario, VerificacionIdentidad
from amira_api.settings import Settings, get_settings
from amira_api.simulated_certificate_verifier import SIMULATOR_APP_ENVS, SimulatedCertificateVerifier
from amira_api.verifik_certificate_verifier import VerifikCertificateVerifier
from amira_api.verifik_sandbox_demo import SandboxDemoCertificateVerifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/driver/verifications", tags=["driver-verification"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]

UNAVAILABLE_MESSAGE = "La verificación de certificados no está disponible por el momento."
STORAGE_UNAVAILABLE_MESSAGE = "No pudimos guardar el certificado. Inténtalo nuevamente."
NOT_A_DRIVER_MESSAGE = "Solo los conductores pueden verificar certificados."
NOT_FOUND_MESSAGE = "No encontramos un certificado con ese folio y código verificador."
INVALID_MESSAGE = "Revisa el folio y el código verificador del certificado."
FOLIO_USED_MESSAGE = "Este certificado ya fue usado en Amira."
ALREADY_SUBMITTED_MESSAGE = "Ya enviaste este certificado y está verificado o en revisión."


def _simulator_enabled(settings: Settings) -> bool:
    return settings.verifik_simulator and _development_app_env(settings)


def _development_app_env(settings: Settings) -> bool:
    return "app_env" in settings.model_fields_set and settings.app_env.strip().lower() in SIMULATOR_APP_ENVS


def build_certificate_verifier(settings: Settings) -> CertificateVerifier:
    if settings.verifik_api_token is not None and settings.verifik_api_token.get_secret_value().strip():
        verifik = VerifikCertificateVerifier(
            token=settings.verifik_api_token.get_secret_value().strip(),
            base_url=settings.verifik_base_url,
        )
        if not settings.verifik_sandbox_demo:
            return verifik
        # The demo turns every submission into a verified certificate, so a flag outside development fails closed.
        if not _development_app_env(settings):
            raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)
        return SandboxDemoCertificateVerifier(inner=verifik, app_env=settings.app_env)
    if _simulator_enabled(settings):
        return SimulatedCertificateVerifier(app_env=settings.app_env)
    raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)


def _driver_certificate_storage(settings: Settings) -> EvidenceStorage:
    bucket = (settings.driver_certificates_bucket or "").strip()
    if not settings.supabase_url or settings.supabase_service_role_key is None or not bucket:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)
    return _supabase_storage(settings.supabase_url, settings.supabase_service_role_key.get_secret_value(), bucket)


def get_certificate_verifier_resolver(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Callable[[], CertificateVerifier]:
    """Deferred so the driver and payload checks run before a 503."""
    return lambda: build_certificate_verifier(settings)


def get_driver_certificate_storage_resolver(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Callable[[], EvidenceStorage]:
    return lambda: _driver_certificate_storage(settings)


ResolveVerifier = Annotated[Callable[[], CertificateVerifier], Depends(get_certificate_verifier_resolver)]
ResolveStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_driver_certificate_storage_resolver)]


def _driver_user(session: Session, auth_user_id: UUID, *, lock: bool = False) -> Usuario:
    query = select(Usuario).join(Conductor, Conductor.user_id == Usuario.id).where(Usuario.auth_user_id == auth_user_id)
    if lock:
        query = query.with_for_update(of=Usuario)
    user = session.execute(query).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=403, detail=NOT_A_DRIVER_MESSAGE)
    return user


def _ensure_can_submit(session: Session, user_id: UUID, document_type: str) -> None:
    current = latest_certificates(session, user_id).get(document_type)
    if current is not None and current.status in ("verified", "in_review"):
        raise HTTPException(status_code=409, detail=ALREADY_SUBMITTED_MESSAGE)


def _ensure_folio_unused(session: Session, provider: str, folio: str) -> None:
    used = session.execute(
        select(VerificacionIdentidad.id).where(
            VerificacionIdentidad.provider == provider,
            VerificacionIdentidad.provider_verification_id == folio,
        )
    ).first()
    if used is not None:
        raise HTTPException(status_code=409, detail=FOLIO_USED_MESSAGE)


def _view(session: Session, user_id: UUID) -> DriverVerificationView:
    latest = latest_certificates(session, user_id)
    items = []
    for document_type in CERTIFICATE_TYPES:
        row = latest.get(document_type)
        items.append(CertificateStatusItem(
            type=document_type,
            status=row.status if row is not None else "missing",
            reason=row.rejection_reason if row is not None else None,
            submitted_at=row.created_at if row is not None else None,
            verified_at=row.verified_at if row is not None else None,
        ))
    return DriverVerificationView(verified=is_driver_verified(session, user_id), certificates=items)


def _discard_pdf(storage: EvidenceStorage | None, key: str | None) -> None:
    if storage is None or key is None:
        return
    try:
        storage.delete(key)
    except EvidenceStorageError:
        logger.warning("Could not delete the unreferenced certificate PDF %s.", key, exc_info=True)


@router.get("", response_model=DriverVerificationView)
def get_driver_verification(current_user: CurrentUser, session: Database) -> DriverVerificationView:
    user = _driver_user(session, current_user.id)
    return _view(session, user.id)


@router.post("", response_model=DriverVerificationView, status_code=201)
def submit_driver_certificate(
    payload: CertificateSubmission,
    current_user: CurrentUser,
    session: Database,
    resolve_verifier: ResolveVerifier,
    resolve_storage: ResolveStorage,
) -> DriverVerificationView:
    user = _driver_user(session, current_user.id)
    user_id, expected_run = user.id, user.national_id
    _ensure_can_submit(session, user_id, payload.type)
    verifier = resolve_verifier()
    storage = resolve_storage() if verifier.returns_pdf else None
    _ensure_folio_unused(session, verifier.name, payload.folio)
    # No transaction stays open while the Registro Civil answers.
    session.rollback()

    try:
        record = verifier.verify_certificate(
            payload.folio, payload.verification_code, holder_run=expected_run, document_type=payload.type,
        )
    except CertificateNotFound:
        raise HTTPException(status_code=422, detail=NOT_FOUND_MESSAGE) from None
    except CertificateInvalid:
        raise HTTPException(status_code=422, detail=INVALID_MESSAGE) from None
    except VerifikUnavailable:
        logger.warning("Certificate verification failed upstream for user %s.", user_id, exc_info=True)
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE) from None

    outcome = classify_certificate(record, expected_run, payload.type)
    row_id = uuid4()
    pdf_key = None
    if record.pdf is not None and storage is not None:
        pdf_key = f"driver-certificates/{user_id}/{row_id}.pdf"
        try:
            storage.upload(pdf_key, record.pdf, "application/pdf")
        except EvidenceStorageError:
            raise HTTPException(status_code=503, detail=STORAGE_UNAVAILABLE_MESSAGE) from None

    now = utc_now()
    try:
        _driver_user(session, current_user.id, lock=True)
        _ensure_can_submit(session, user_id, payload.type)
        _ensure_folio_unused(session, verifier.name, payload.folio)
        session.add(VerificacionIdentidad(
            id=row_id,
            user_id=user_id,
            provider=verifier.name,
            provider_verification_id=payload.folio,
            status=outcome.status,
            document_type=payload.type,
            annotations=[{"register": item.register, "fines": item.fines} for item in record.registers],
            pdf_storage_key=pdf_key,
            rejection_reason=outcome.reason,
            verified_at=now if outcome.status == "verified" else None,
            created_at=now,
            updated_at=now,
        ))
        session.commit()
    except HTTPException:
        session.rollback()
        _discard_pdf(storage, pdf_key)
        raise
    except IntegrityError:
        session.rollback()
        _discard_pdf(storage, pdf_key)
        raise HTTPException(status_code=409, detail=FOLIO_USED_MESSAGE) from None
    return _view(session, user_id)
