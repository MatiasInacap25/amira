"""Development-only demo of the Verifik integration: every submission is verified through the Verifik sandbox.

The Verifik sandbox only answers its documented sample certificate (folio 50070080804, code 2aacbb9a636a), which
belongs to a fictitious RUN. For a demo where drivers can complete the flow, this adapter sends that sample to the
real sandbox whatever the driver typed and presents the answer as the driver's own certificate of the declared type:
the RUN becomes the account's RUT and the registers carry the declared type's name. The sandbox call is real, so the
token, the network path and the response parsing are exercised; only the identity of the certificate is staged.

It refuses to run outside the development allowlist, and the composition root answers 503 when its flag is set in
any other environment, so it can never verify a driver in production.
"""

from amira_api.driver_certificates import CertificateRecord, CertificateRegister, CertificateVerifier
from amira_api.simulated_certificate_verifier import SIMULATOR_APP_ENVS

SANDBOX_FOLIO = "50070080804"
SANDBOX_CODE = "2aacbb9a636a"
SANDBOX_PROVIDER_NAME = "verifik-sandbox"
DRIVER_REGISTER = "Registro Nacional de Conductores de Vehículos Motorizados"


class SandboxDemoCertificateVerifier:
    # A separate provider name keeps demo folios apart from real Verifik folios in the uniqueness check.
    name = SANDBOX_PROVIDER_NAME
    returns_pdf = True

    def __init__(self, *, inner: CertificateVerifier, app_env: str) -> None:
        if app_env.strip().lower() not in SIMULATOR_APP_ENVS:
            allowed = ", ".join(sorted(SIMULATOR_APP_ENVS))
            raise RuntimeError(f"The Verifik sandbox demo requires APP_ENV to be one of: {allowed}.")
        self._inner = inner

    def verify_certificate(
        self, folio: str, verification_code: str, *, holder_run: str | None = None, document_type: str | None = None,
    ) -> CertificateRecord:
        sample = self._inner.verify_certificate(SANDBOX_FOLIO, SANDBOX_CODE)
        run = holder_run or sample.run
        if document_type == "driver_record":
            fines = sample.registers[0].fines if sample.registers else ""
            registers = (CertificateRegister(register=DRIVER_REGISTER, run=run, fines=fines),)
        else:
            registers = tuple(CertificateRegister(register=item.register, run=run, fines=item.fines) for item in sample.registers)
        return CertificateRecord(name=sample.name, run=run, registers=registers, pdf=sample.pdf)
