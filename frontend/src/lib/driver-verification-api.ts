// Driver certificate verification: file rules, labels and API error messages.
//
// Demo flow: the driver picks the certificate PDF, which is checked here and never leaves the browser. The request
// carries a generated folio instead, and the backend's development-only Verifik sandbox demo marks it verified.

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

export type CertificateSubmission = { type: CertificateType; folio: string; verification_code: string };

export const MAX_CERTIFICATE_BYTES = 5 * 1024 * 1024;
const SIMULATED_VERIFICATION_CODE = "demo-pdf";

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

// A PDF by name, declared type and content signature (%PDF-), so a renamed image is refused too.
export async function validateCertificateFile(file: File | null): Promise<string | null> {
  if (!file) return "Selecciona el certificado en PDF.";
  const pdfName = file.name.toLowerCase().endsWith(".pdf");
  const pdfType = file.type === "" || file.type === "application/pdf";
  if (!pdfName || !pdfType) return "Solo se aceptan certificados en PDF.";
  if (file.size > MAX_CERTIFICATE_BYTES) return "El PDF no puede pesar más de 5 MB.";
  const signature = new TextDecoder().decode(await file.slice(0, 5).arrayBuffer());
  return signature === "%PDF-" ? null : "Solo se aceptan certificados en PDF.";
}

// The request sent for a chosen PDF: a fresh 15-digit folio, so every submission is a new certificate for the backend.
export function simulatedCertificateSubmission(type: CertificateType): CertificateSubmission {
  const digits = crypto.getRandomValues(new Uint8Array(15));
  const folio = Array.from(digits, (value, index) => (index === 0 ? 1 + (value % 9) : value % 10)).join("");
  return { type, folio, verification_code: SIMULATED_VERIFICATION_CODE };
}

// 409, 422 and 403 carry a Spanish detail from the API; anything else gets a fixed message.
export async function driverVerificationError(response: Response): Promise<string> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  const detail = typeof body?.detail === "string" ? body.detail : null;
  if ((response.status === 409 || response.status === 403) && detail) return detail;
  if (response.status === 422) return detail ?? "Revisa el certificado e inténtalo nuevamente.";
  if (response.status === 503) return "La verificación de certificados no está disponible por el momento. Inténtalo más tarde.";
  return "No pudimos completar la verificación. Inténtalo nuevamente.";
}
