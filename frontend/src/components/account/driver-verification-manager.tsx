"use client";

import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { authenticatedApiFetch } from "@/lib/auth/account-api";
import {
  CERTIFICATE_LABELS,
  DRIVER_VERIFICATION_PATH,
  certificateStatusLabel,
  driverVerificationError,
  simulatedCertificateSubmission,
  validateCertificateFile,
  type CertificateState,
  type CertificateType,
  type DriverVerification,
} from "@/lib/driver-verification-api";

const LOAD_ERROR = "No pudimos cargar el estado de tu verificación.";
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
  onSubmit: (type: CertificateType) => Promise<boolean>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const id = certificate.type;
  const canSubmit = certificate.status === "missing" || certificate.status === "rejected";

  function choose(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const nextError = await validateCertificateFile(file);
    setError(nextError);
    if (nextError) return;
    // The PDF stays in the browser: only the certificate type reaches the API (see simulatedCertificateSubmission).
    if (await onSubmit(certificate.type)) {
      form.reset();
      setFile(null);
    }
  }

  return (
    <section aria-labelledby={`${id}-title`} className="driver-certificate">
      <h2 id={`${id}-title`}>{CERTIFICATE_LABELS[certificate.type]}</h2>
      <p className={`driver-certificate-status status-${certificate.status}`}>{certificateStatusLabel(certificate.status)}</p>
      {certificate.reason && <p className="auth-help">{certificate.reason}</p>}
      {canSubmit && (
        <form aria-label={`Verificar ${CERTIFICATE_LABELS[certificate.type].toLowerCase()}`} className="auth-form" noValidate onSubmit={submit}>
          <p className="auth-help">{HINTS[certificate.type]} Sube el certificado en PDF, de hasta 5 MB.</p>
          <label className="auth-field" htmlFor={`${id}-file`}>Certificado en PDF
            <input accept="application/pdf,.pdf" aria-describedby={error ? `${id}-file-error` : undefined} aria-invalid={error ? true : undefined} id={`${id}-file`} onChange={choose} type="file" />
            {error && <span className="auth-field-error" id={`${id}-file-error`}>{error}</span>}
          </label>
          <button className="auth-submit" disabled={busy} type="submit">{busy ? "Subiendo…" : "Subir certificado"}</button>
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

  async function submit(type: CertificateType): Promise<boolean> {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await api({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(simulatedCertificateSubmission(type)),
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
