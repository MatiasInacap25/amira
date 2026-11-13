"""Driver certificates: the verification rule, the Verifik HTTP adapter, the simulated adapter and adapter selection."""

from __future__ import annotations

import base64

import httpx
from pydantic import SecretStr
import pytest
from fastapi import HTTPException

from amira_api.driver_certificates import (
    CertificateInvalid,
    CertificateNotFound,
    CertificateRecord,
    CertificateRegister,
    VerifikUnavailable,
    classify_certificate,
)
from amira_api.driver_verification_routes import build_certificate_verifier
from amira_api.settings import Settings
from amira_api.simulated_certificate_verifier import SimulatedCertificateVerifier
from amira_api.verifik_certificate_verifier import VerifikCertificateVerifier

CLEAN = "No registra anotaciones"
PDF = b"%PDF-1.7\n" + b"0" * 32
TOKEN = "verifik-secret-token"


def record(run: str = "12.345.678-5", fines: tuple[str, ...] = (CLEAN, CLEAN)) -> CertificateRecord:
    return CertificateRecord(
        name="PEDRO SOTO",
        run=run,
        registers=tuple(CertificateRegister(register=f"Registro General de Condenas {index}", run=run, fines=value) for index, value in enumerate(fines)),
        pdf=None,
    )


# Verification rule (S2)

def test_clean_certificate_of_the_same_run_is_verified() -> None:
    outcome = classify_certificate(record(), expected_run="12345678-5", document_type="criminal_record")
    assert outcome.status == "verified"
    assert outcome.reason is None


def test_run_comparison_ignores_dots_hyphen_spaces_and_case() -> None:
    assert classify_certificate(record(run="12.345.678-k"), expected_run="12345678K", document_type="criminal_record").status == "verified"


def test_certificate_with_annotations_goes_to_manual_review() -> None:
    outcome = classify_certificate(record(fines=(CLEAN, "Condena 2019: conducir en estado de ebriedad")), expected_run="12345678-5", document_type="criminal_record")
    assert outcome.status == "in_review"
    assert outcome.reason == "El certificado tiene anotaciones y será revisado por el equipo de Amira."


def test_certificate_of_another_run_is_rejected() -> None:
    outcome = classify_certificate(record(run="11.111.111-1"), expected_run="12345678-5", document_type="criminal_record")
    assert outcome.status == "rejected"
    assert outcome.reason == "El certificado pertenece a otra persona."


def test_certificate_without_recognisable_registers_goes_to_review_never_verified() -> None:
    assert classify_certificate(record(fines=()), expected_run="12345678-5", document_type="criminal_record").status == "in_review"


def test_a_register_of_another_run_goes_to_review() -> None:
    mixed = CertificateRecord(
        name="PEDRO SOTO",
        run="12345678-5",
        registers=(CertificateRegister(register="Registro General", run="11111111-1", fines=CLEAN),),
        pdf=None,
    )
    assert classify_certificate(mixed, expected_run="12345678-5", document_type="criminal_record").status == "in_review"


def driver_record(run: str = "12345678-5", fines: str = CLEAN) -> CertificateRecord:
    return CertificateRecord(
        name="PEDRO SOTO",
        run=run,
        registers=(CertificateRegister(register="Registro Nacional de Conductores de Vehículos Motorizados", run=run, fines=fines),),
        pdf=None,
    )


def test_a_clean_driver_record_submitted_as_driver_record_is_verified() -> None:
    assert classify_certificate(driver_record(), expected_run="12345678-5", document_type="driver_record").status == "verified"


@pytest.mark.parametrize(
    ("certificate", "document_type"),
    [(record(), "driver_record"), (driver_record(), "criminal_record")],
)
def test_a_certificate_of_another_type_is_never_verified_automatically(certificate, document_type) -> None:
    outcome = classify_certificate(certificate, expected_run="12345678-5", document_type=document_type)
    assert outcome.status == "in_review"
    assert outcome.reason == "No pudimos confirmar que el certificado sea del tipo indicado; será revisado por el equipo de Amira."


def test_user_without_rut_is_never_verified() -> None:
    assert classify_certificate(record(), expected_run=None, document_type="criminal_record").status == "rejected"


# Verifik HTTP adapter (S5)

def verifik_payload(run: str = "12.345.678-5") -> dict:
    return {
        "data": {
            "response": "Certificado verificado correctamente",
            "folio": "50070080804",
            "verificationCode": "2aacbb9a636a",
            "pdfBase64": base64.b64encode(PDF).decode(),
            "details": {
                "name": "PEDRO SOTO",
                "run": run,
                "registers": [
                    {"register": "Registro General de Condenas", "run": run, "fines": CLEAN},
                    {"register": "Registro Especial de Condenas por Actos de Violencia Intrafamiliar", "run": run, "fines": CLEAN},
                ],
            },
        },
        "signature": {"message": "Certified by Verifik.co"},
    }


def adapter(handler) -> VerifikCertificateVerifier:
    return VerifikCertificateVerifier(token=TOKEN, base_url="https://api.verifik.test", transport=httpx.MockTransport(handler))


def test_adapter_sends_the_folio_code_and_bearer_token_and_parses_the_certificate() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=verifik_payload())

    result = adapter(handler).verify_certificate("50070080804", "2aacbb9a636a")

    assert seen[0].method == "GET"
    assert seen[0].url.path == "/v2/cl/registro-civil/certificado"
    assert dict(seen[0].url.params) == {"folio": "50070080804", "verificationCode": "2aacbb9a636a"}
    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert result.run == "12.345.678-5"
    assert result.name == "PEDRO SOTO"
    assert [item.fines for item in result.registers] == [CLEAN, CLEAN]
    assert result.pdf == PDF


def test_adapter_maps_404_to_not_found() -> None:
    with pytest.raises(CertificateNotFound):
        adapter(lambda _: httpx.Response(404, json={"code": "NotFound", "message": "Record not found."})).verify_certificate("9004040100001", "abc")


def test_adapter_maps_missing_parameter_409_to_invalid_input() -> None:
    response = httpx.Response(409, json={"code": "MissingParameter", "message": "folio length must be at least 10 characters long"})
    with pytest.raises(CertificateInvalid):
        adapter(lambda _: response).verify_certificate("123", "abc")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(409, json={"code": "timeout_data_source", "message": "Registro Civil timeout"}),
        httpx.Response(500, text="boom"),
        httpx.Response(401, json={"code": "Unauthorized"}),
        httpx.Response(200, json={"data": {"details": "unexpected"}}),
        httpx.Response(200, text="not json"),
    ],
)
def test_adapter_maps_upstream_failures_to_unavailable_without_leaking_the_token(response: httpx.Response) -> None:
    with pytest.raises(VerifikUnavailable) as raised:
        adapter(lambda _: response).verify_certificate("50070080804", "2aacbb9a636a")
    assert TOKEN not in str(raised.value)


def test_adapter_treats_a_non_json_409_as_unavailable() -> None:
    with pytest.raises(VerifikUnavailable):
        adapter(lambda _: httpx.Response(409, text="conflict")).verify_certificate("50070080804", "2aacbb9a636a")


def test_adapter_treats_a_non_text_field_as_unavailable() -> None:
    payload = verifik_payload()
    payload["data"]["details"]["name"] = 42
    with pytest.raises(VerifikUnavailable):
        adapter(lambda _: httpx.Response(200, json=payload)).verify_certificate("50070080804", "2aacbb9a636a")


@pytest.mark.parametrize("encoded", [None, "", "not base64 !!"])
def test_adapter_returns_no_pdf_when_it_is_missing_or_not_base64(encoded) -> None:
    payload = verifik_payload()
    payload["data"]["pdfBase64"] = encoded
    result = adapter(lambda _: httpx.Response(200, json=payload)).verify_certificate("50070080804", "2aacbb9a636a")
    assert result.pdf is None


def test_adapter_maps_network_errors_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(VerifikUnavailable):
        adapter(handler).verify_certificate("50070080804", "2aacbb9a636a")


def test_adapter_drops_a_pdf_that_is_not_a_pdf() -> None:
    payload = verifik_payload()
    payload["data"]["pdfBase64"] = base64.b64encode(b"<html>nope</html>").decode()
    result = adapter(lambda _: httpx.Response(200, json=payload)).verify_certificate("50070080804", "2aacbb9a636a")
    assert result.pdf is None


# Simulated adapter (S5)

@pytest.mark.parametrize("app_env", ["production", "staging", "", "prod "])
def test_simulated_adapter_refuses_outside_development(app_env: str) -> None:
    with pytest.raises(RuntimeError):
        SimulatedCertificateVerifier(app_env=app_env)


def test_simulated_adapter_returns_a_clean_certificate_for_ok_codes() -> None:
    result = SimulatedCertificateVerifier(app_env="test").verify_certificate("1234567890", "ok-12345678-5")
    assert result.run == "12345678-5"
    assert all(item.fines == CLEAN for item in result.registers)
    assert result.pdf is None


def test_simulated_adapter_returns_annotations_for_anot_codes() -> None:
    result = SimulatedCertificateVerifier(app_env="test").verify_certificate("1234567890", "anot-12345678-5")
    assert any(item.fines != CLEAN for item in result.registers)


@pytest.mark.parametrize(("code", "status"), [("hv-12345678-5", "verified"), ("hvanot-12345678-5", "in_review")])
def test_simulated_adapter_returns_driver_records_for_hv_codes(code: str, status: str) -> None:
    result = SimulatedCertificateVerifier(app_env="test").verify_certificate("1234567890", code)
    assert classify_certificate(result, expected_run="12345678-5", document_type="driver_record").status == status


def test_simulated_adapter_does_not_find_other_codes() -> None:
    with pytest.raises(CertificateNotFound):
        SimulatedCertificateVerifier(app_env="test").verify_certificate("1234567890", "whatever")


# Adapter selection (S5)

def test_a_configured_token_selects_the_verifik_adapter() -> None:
    settings = Settings(_env_file=None, verifik_api_token="token", app_env="production")
    assert isinstance(build_certificate_verifier(settings), VerifikCertificateVerifier)


def test_the_simulator_needs_an_explicit_development_app_env() -> None:
    settings = Settings(_env_file=None, verifik_simulator=True, app_env="development")
    assert isinstance(build_certificate_verifier(settings), SimulatedCertificateVerifier)


@pytest.mark.parametrize("values", [{}, {"verifik_simulator": True}, {"verifik_simulator": True, "app_env": "production"}])
def test_without_a_token_or_an_allowed_simulator_verification_is_unavailable(values: dict) -> None:
    with pytest.raises(HTTPException) as raised:
        build_certificate_verifier(Settings.model_construct(**values) if "app_env" not in values else Settings(_env_file=None, **values))
    assert raised.value.status_code == 503


# Verifik sandbox demo (S7)

from amira_api.verifik_sandbox_demo import SANDBOX_CODE, SANDBOX_FOLIO, SandboxDemoCertificateVerifier  # noqa: E402


def demo(handler, app_env: str = "development") -> SandboxDemoCertificateVerifier:
    return SandboxDemoCertificateVerifier(inner=adapter(handler), app_env=app_env)


@pytest.mark.parametrize("document_type", ["criminal_record", "driver_record"])
def test_sandbox_demo_sends_the_sample_certificate_and_verifies_the_driver(document_type: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=verifik_payload(run="12.345.678-9"))

    result = demo(handler).verify_certificate("99999999999", "codigo-del-conductor", holder_run="11.111.111-1", document_type=document_type)

    assert (SANDBOX_FOLIO, SANDBOX_CODE) == ("50070080804", "2aacbb9a636a")
    assert dict(seen[0].url.params) == {"folio": SANDBOX_FOLIO, "verificationCode": SANDBOX_CODE}
    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert result.run == "11.111.111-1"
    assert result.pdf == PDF
    assert classify_certificate(result, expected_run="11111111-1", document_type=document_type).status == "verified"


def test_sandbox_demo_keeps_sandbox_failures() -> None:
    with pytest.raises(VerifikUnavailable):
        demo(lambda _: httpx.Response(500, text="down")).verify_certificate("99999999999", "x", holder_run="11111111-1", document_type="criminal_record")


@pytest.mark.parametrize("app_env", ["production", "staging", "", " prod"])
def test_sandbox_demo_refuses_outside_development(app_env: str) -> None:
    with pytest.raises(RuntimeError):
        demo(lambda _: httpx.Response(200, json=verifik_payload()), app_env=app_env)


def test_the_sandbox_demo_needs_a_token_the_flag_and_an_explicit_development_app_env() -> None:
    settings = Settings(_env_file=None, verifik_api_token="token", verifik_sandbox_demo=True, app_env="development")
    assert isinstance(build_certificate_verifier(settings), SandboxDemoCertificateVerifier)


@pytest.mark.parametrize(
    "settings",
    [
        Settings(_env_file=None, verifik_api_token="token", verifik_sandbox_demo=True, app_env="production"),
        Settings.model_construct(verifik_api_token=SecretStr("token"), verifik_sandbox_demo=True),
    ],
)
def test_the_sandbox_demo_flag_outside_development_fails_closed(settings) -> None:
    with pytest.raises(HTTPException) as raised:
        build_certificate_verifier(settings)
    assert raised.value.status_code == 503
