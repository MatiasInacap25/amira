"""Verifik adapter for the CertificateVerifier port: checks a Registro Civil certificate by folio and verification code.

GET {base}/v2/cl/registro-civil/certificado?folio=&verificationCode= with a Bearer token
(https://docs.verifik.co/background-check/chile-certificate-verify/). The token is a server-side secret: it never
reaches the browser, a log line or an exception message. Any answer this adapter does not fully understand is a
VerifikUnavailable, so an unexpected shape can never be read as a clean certificate.
"""

import base64
import binascii
from typing import Any

import httpx

from amira_api.driver_certificates import (
    VERIFIK_PROVIDER_NAME,
    CertificateInvalid,
    CertificateNotFound,
    CertificateRecord,
    CertificateRegister,
    VerifikUnavailable,
)

DEFAULT_BASE_URL = "https://api.verifik.co"
CERTIFICATE_PATH = "/v2/cl/registro-civil/certificado"
# The Registro Civil can be slow; Verifik reports its own upstream timeout as a 409 timeout_data_source.
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_PDF_BYTES = 5 * 1024 * 1024


class VerifikCertificateVerifier:
    name = VERIFIK_PROVIDER_NAME
    returns_pdf = True

    def __init__(self, *, token: str, base_url: str = DEFAULT_BASE_URL, transport: httpx.BaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._transport = transport

    def verify_certificate(
        self, folio: str, verification_code: str, *, holder_run: str | None = None, document_type: str | None = None,
    ) -> CertificateRecord:
        # One short-lived client per verification, closed on exit: the composition root builds a verifier per request.
        try:
            with httpx.Client(
                base_url=self._base_url, headers=self._headers, timeout=REQUEST_TIMEOUT_SECONDS, transport=self._transport,
            ) as client:
                response = client.get(CERTIFICATE_PATH, params={"folio": folio, "verificationCode": verification_code})
        except httpx.HTTPError as error:
            raise VerifikUnavailable("Verifik could not be reached.") from error

        if response.status_code == 404:
            raise CertificateNotFound("No certificate for this folio and verification code.")
        if response.status_code == 409 and _error_code(response) == "MissingParameter":
            raise CertificateInvalid("The folio or the verification code is malformed.")
        if response.status_code != 200:
            raise VerifikUnavailable(f"Verifik answered HTTP {response.status_code}.")
        try:
            return _parse(response.json())
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise VerifikUnavailable("Verifik answered an unexpected certificate shape.") from error


def _error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("code") if isinstance(body, dict) else None


def _parse(body: Any) -> CertificateRecord:
    data = body["data"]
    details = data["details"]
    registers = tuple(
        CertificateRegister(register=_text(item["register"]), run=_text(item["run"]), fines=_text(item["fines"]))
        for item in details["registers"]
    )
    return CertificateRecord(name=_text(details["name"]), run=_text(details["run"]), registers=registers, pdf=_pdf(data.get("pdfBase64")))


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("Expected a string field.")
    return value


def _pdf(encoded: Any) -> bytes | None:
    """The decoded PDF, or None when it is missing, not base64, too large or not a PDF."""
    if not isinstance(encoded, str) or not encoded:
        return None
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-"):
        return None
    return content
