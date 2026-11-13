"""Simulated CertificateVerifier for development. It refuses to run outside the development allowlist.

The verification code chooses the answer, so a developer can try every branch without Verifik:
- ``ok-<RUN>``: a certificado de antecedentes of that RUN with no annotations.
- ``anot-<RUN>``: a certificado de antecedentes of that RUN with one annotation (goes to manual review).
- ``hv-<RUN>``: a hoja de vida del conductor of that RUN with no annotations.
- ``hvanot-<RUN>``: a hoja de vida del conductor of that RUN with one annotation.
- anything else: not found.
It never returns a PDF, so no storage bucket is needed in development.
"""

from amira_api.driver_certificates import (
    CLEAN_FINES,
    CertificateNotFound,
    CertificateRecord,
    CertificateRegister,
)

SIMULATOR_APP_ENVS = frozenset({"development", "local", "test"})
SIMULATED_PROVIDER_NAME = "simulated"
CLEAN = CLEAN_FINES.capitalize()


class SimulatedCertificateVerifier:
    name = SIMULATED_PROVIDER_NAME
    returns_pdf = False

    def __init__(self, *, app_env: str) -> None:
        if app_env.strip().lower() not in SIMULATOR_APP_ENVS:
            allowed = ", ".join(sorted(SIMULATOR_APP_ENVS))
            raise RuntimeError(f"The simulated certificate verifier requires APP_ENV to be one of: {allowed}.")

    def verify_certificate(self, folio: str, verification_code: str) -> CertificateRecord:
        prefix, _, run = verification_code.partition("-")
        if prefix not in {"ok", "anot", "hv", "hvanot"} or not run:
            raise CertificateNotFound("The simulator has no certificate for this code.")
        fines = CLEAN if prefix in {"ok", "hv"} else "Anotación simulada"
        if prefix.startswith("hv"):
            registers = (CertificateRegister(register="Registro Nacional de Conductores de Vehículos Motorizados", run=run, fines=fines),)
        else:
            registers = (
                CertificateRegister(register="Registro General de Condenas", run=run, fines=CLEAN),
                CertificateRegister(register="Registro Especial de Condenas por Actos de Violencia Intrafamiliar", run=run, fines=fines),
            )
        return CertificateRecord(name="CONDUCTOR SIMULADO", run=run, registers=registers, pdf=None)
