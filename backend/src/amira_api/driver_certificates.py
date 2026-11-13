"""Driver certificates: the port that verifies a Registro Civil certificate and the rule that classifies the result.

Drivers verify two certificates, the certificado de antecedentes and the hoja de vida del conductor. Both carry a folio
and a verification code, which an adapter checks against the Registro Civil (Verifik in production, a simulator in
development). The domain never picks the adapter: the composition root (driver_verification_routes) does.

A certificate is verified automatically only when it belongs to the driver's RUN and every register says it has no
annotations. Annotations, or a response the rule does not recognise, send it to manual review; another person's
certificate is rejected. Nothing here ever turns an unknown answer into a verification.
"""

import re
from dataclasses import dataclass
from typing import Literal, Protocol

CertificateType = Literal["criminal_record", "driver_record"]
CERTIFICATE_TYPES: tuple[CertificateType, ...] = ("criminal_record", "driver_record")
VerificationStatus = Literal["verified", "in_review", "rejected"]
VERIFIK_PROVIDER_NAME = "verifik"

CLEAN_FINES = "no registra anotaciones"
ANNOTATIONS_REASON = "El certificado tiene anotaciones y será revisado por el equipo de Amira."
UNRECOGNISED_REASON = "No pudimos leer las anotaciones del certificado; será revisado por el equipo de Amira."
OTHER_PERSON_REASON = "El certificado pertenece a otra persona."
NO_RUT_REASON = "Tu cuenta no tiene un RUT registrado para comparar con el certificado."
OTHER_TYPE_REASON = "No pudimos confirmar que el certificado sea del tipo indicado; será revisado por el equipo de Amira."
# Verifik returns no certificate type, so the type is read from the register names: the antecedentes certificate
# lists the conviction registers ("Registro General de Condenas", ...), the hoja de vida the national driver register
# ("Registro Nacional de Conductores ..."). A certificate whose registers do not show the declared type is never
# verified automatically, so an antecedentes certificate cannot stand in for the hoja de vida.
TYPE_MARKERS: dict[str, str] = {"criminal_record": "condenas", "driver_record": "conductores"}


class CertificateNotFound(Exception):
    """The Registro Civil has no certificate for this folio and verification code."""


class CertificateInvalid(Exception):
    """The folio or the verification code is malformed."""


class VerifikUnavailable(Exception):
    """The verification service failed or answered something unexpected. Nothing was verified."""


@dataclass(frozen=True)
class CertificateRegister:
    register: str
    run: str
    fines: str


@dataclass(frozen=True)
class CertificateRecord:
    name: str
    run: str
    registers: tuple[CertificateRegister, ...]
    # The official PDF when the adapter returns one; None otherwise.
    pdf: bytes | None


@dataclass(frozen=True)
class CertificateOutcome:
    status: VerificationStatus
    reason: str | None


class CertificateVerifier(Protocol):
    name: str
    # True when verify_certificate returns the official PDF, which must then be stored in the private bucket.
    returns_pdf: bool

    def verify_certificate(self, folio: str, verification_code: str) -> CertificateRecord:
        """The certificate behind this folio and code. Raises CertificateNotFound, CertificateInvalid or VerifikUnavailable."""
        ...


def compact_run(value: str) -> str:
    """The RUN without dots, spaces or hyphen, uppercased, so 12.345.678-k and 12345678K compare equal."""
    return re.sub(r"[.\s-]", "", value).upper()


def _shows_type(record: CertificateRecord, document_type: str) -> bool:
    names = [item.register.lower() for item in record.registers]
    own = TYPE_MARKERS[document_type]
    others = [marker for kind, marker in TYPE_MARKERS.items() if kind != document_type]
    return any(own in name for name in names) and not any(marker in name for name in names for marker in others)


def classify_certificate(record: CertificateRecord, expected_run: str | None, document_type: str) -> CertificateOutcome:
    if not expected_run:
        return CertificateOutcome("rejected", NO_RUT_REASON)
    expected = compact_run(expected_run)
    if compact_run(record.run) != expected:
        return CertificateOutcome("rejected", OTHER_PERSON_REASON)
    if not record.registers or any(compact_run(item.run) != expected for item in record.registers):
        return CertificateOutcome("in_review", UNRECOGNISED_REASON)
    if not _shows_type(record, document_type):
        return CertificateOutcome("in_review", OTHER_TYPE_REASON)
    if all(item.fines.strip().lower() == CLEAN_FINES for item in record.registers):
        return CertificateOutcome("verified", None)
    return CertificateOutcome("in_review", ANNOTATIONS_REASON)
