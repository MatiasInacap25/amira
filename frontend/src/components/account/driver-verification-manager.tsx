"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { authenticatedApiFetch } from "@/lib/auth/account-api";
import {
  CERTIFICATE_LABELS,
  DRIVER_VERIFICATION_PATH,
  certificateStatusLabel,
  driverVerificationError,
  validateCertificateForm,
  type CertificateFormErrors,
  type CertificateFormValues,
  type CertificateState,
  type CertificateType,
  type DriverVerification,
} from "@/lib/driver-verification-api";

const LOAD_ERROR = "No pudimos cargar el estado de tu verificación.";
const EMPTY_FORM: CertificateFormValues = { folio: "", verificationCode: "" };
const HINTS: Record<CertificateType, string> = {
  criminal_record: "Lo descargas gratis en el sitio del Registro Civil con tu ClaveÚnica.",
  driver_record: "Lo descargas gratis en el sitio del Registro Civil, sección Vehículos, con tu ClaveÚnica.",
};

function CertificateCard({
  certificate,
  busy,
  onSubmit,
}: {
  certificate: CertificateState;
  busy: boolean;
  onSubmit: (type: CertificateType, values: CertificateFormValues) => Promise<boolean>;
}) {
  const [values, setValues] = useState<CertificateFormValues>(EMPTY_FORM);
  const [errors, setErrors] = useState<CertificateFormErrors>({});
  const id = certificate.type;
  const canSubmit = certificate.status === "missing" || certificate.status === "rejected";

  function update(field: keyof CertificateFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validateCertificateForm(values);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    if (await onSubmit(certificate.type, { folio: values.folio.trim(), verificationCode: values.verificationCode.trim() })) {
      setValues(EMPTY_FORM);
    }
  }

  return (
    <section aria-labelledby={`${id}-title`} className="driver-certificate">
      <h2 id={`${id}-title`}>{CERTIFICATE_LABELS[certificate.type]}</h2>
      <p className={`driver-certificate-status status-${certificate.status}`}>{certificateStatusLabel(certificate.status)}</p>
      {certificate.reason && <p className="auth-help">{certificate.reason}</p>}
      {canSubmit && (
        <form aria-label={`Verificar ${CERTIFICATE_LABELS[certificate.type].toLowerCase()}`} className="auth-form" noValidate onSubmit={submit}>
          <p className="auth-help">{HINTS[certificate.type]} Ingresa el folio y el código verificador impresos en el certificado.</p>
          <label className="auth-field" htmlFor={`${id}-folio`}>Folio
            <input aria-describedby={errors.folio ? `${id}-folio-error` : undefined} aria-invalid={errors.folio ? true : undefined} autoComplete="off" id={`${id}-folio`} inputMode="numeric" maxLength={20} onChange={(event) => update("folio", event.target.value)} value={values.folio} />
            {errors.folio && <span className="auth-field-error" id={`${id}-folio-error`}>{errors.folio}</span>}
          </label>
          <label className="auth-field" htmlFor={`${id}-code`}>Código verificador
            <input aria-describedby={errors.verificationCode ? `${id}-code-error` : undefined} aria-invalid={errors.verificationCode ? true : undefined} autoComplete="off" id={`${id}-code`} maxLength={70} onChange={(event) => update("verificationCode", event.target.value)} value={values.verificationCode} />
            {errors.verificationCode && <span className="auth-field-error" id={`${id}-code-error`}>{errors.verificationCode}</span>}
          </label>
          <button className="auth-submit" disabled={busy} type="submit">{busy ? "Verificando…" : "Verificar certificado"}</button>
        </form>
      )}
    </section>
  );
}

export function DriverVerificationManager({ token }: { token: string }) {
  const [verification, setVerification] = useState<DriverVerification | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const api = useCallback((options?: RequestInit) =>
    authenticatedApiFetch(DRIVER_VERIFICATION_PATH, token, process.env.NEXT_PUBLIC_API_URL, options), [token]);

  useEffect(() => {
    void Promise.resolve()
      .then(async () => {
        const response = await api();
        if (!response.ok) throw new Error(await driverVerificationError(response));
        setVerification(await response.json() as DriverVerification);
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : LOAD_ERROR));
  }, [api]);

  async function submit(type: CertificateType, values: CertificateFormValues): Promise<boolean> {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await api({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, folio: values.folio, verification_code: values.verificationCode }),
      });
      if (!response.ok) throw new Error(await driverVerificationError(response));
      const next = await response.json() as DriverVerification;
      setVerification(next);
      const status = next.certificates.find((item) => item.type === type)?.status;
      setNotice(status === "verified" ? "Certificado verificado." : status === "in_review" ? "Recibimos tu certificado. El equipo de Amira lo revisará." : "No pudimos verificar el certificado.");
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No pudimos completar la verificación.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="driver-verification">
      {notice && <p role="status" aria-live="polite" className="auth-notice">{notice}</p>}
      {error && <p role="alert" aria-live="assertive" className="auth-error">{error}</p>}
      {verification && (
        <>
          <p className={verification.verified ? "auth-notice" : "auth-help"}>
            {verification.verified
              ? "Tus certificados están verificados. Ya puedes publicar tu perfil y recibir asignaciones."
              : "Mientras tus dos certificados no estén verificados no podrás publicar tu perfil ni ser asignado a servicios o viajes."}
          </p>
          {verification.certificates.map((certificate) => (
            <CertificateCard busy={busy} certificate={certificate} key={certificate.type} onSubmit={submit} />
          ))}
        </>
      )}
    </div>
  );
}
