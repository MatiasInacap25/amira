// Driver certificate verification: form rules, labels and API error messages. The backend checks the certificate with
// Verifik and enforces the same folio and code formats again.

export type CertificateType = "criminal_record" | "driver_record";
export type CertificateStatus = "missing" | "verified" | "in_review" | "rejected";

export type CertificateState = {
  type: CertificateType;
  status: CertificateStatus;
  reason: string | null;
  submittedAt: string | null;
  verifiedAt: string | null;
};

export type DriverVerification = {
  verified: boolean;
  certificates: CertificateState[];
};

export type CertificateFormValues = { folio: string; verificationCode: string };
export type CertificateFormErrors = Partial<Record<keyof CertificateFormValues, string>>;

export const DRIVER_VERIFICATION_PATH = "/api/driver/verifications";

export const CERTIFICATE_LABELS: Record<CertificateType, string> = {
  criminal_record: "Certificado de antecedentes",
  driver_record: "Hoja de vida del conductor",
};

const STATUS_LABELS: Record<CertificateStatus, string> = {
  missing: "Pendiente",
  verified: "Verificado",
  in_review: "En revisión",
  rejected: "Rechazado",
};

export function certificateStatusLabel(status: CertificateStatus): string {
  return STATUS_LABELS[status];
}

export function validateCertificateForm(values: CertificateFormValues): CertificateFormErrors {
  const errors: CertificateFormErrors = {};
  const folio = values.folio.trim();
  const code = values.verificationCode.trim();
  if (!folio) errors.folio = "Ingresa el folio del certificado.";
  else if (!/^[0-9A-Za-z]{10,15}$/.test(folio)) errors.folio = "El folio tiene entre 10 y 15 letras o números.";
  if (!code) errors.verificationCode = "Ingresa el código verificador.";
  else if (!/^[0-9A-Za-z_-]{1,64}$/.test(code)) errors.verificationCode = "El código verificador solo tiene letras y números.";
  return errors;
}

// 409, 422 and 403 carry a Spanish detail from the API; anything else gets a fixed message.
export async function driverVerificationError(response: Response): Promise<string> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  const detail = typeof body?.detail === "string" ? body.detail : null;
  if ((response.status === 409 || response.status === 403) && detail) return detail;
  if (response.status === 422) return detail ?? "Revisa el folio y el código verificador.";
  if (response.status === 503) return "La verificación de certificados no está disponible por el momento. Inténtalo más tarde.";
  return "No pudimos completar la verificación. Inténtalo nuevamente.";
}
