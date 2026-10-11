"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { authenticatedApiFetch } from "@/lib/auth/account-api";
import { createClient } from "@/lib/supabase/client";

const INVITATION_KEY = "amira-driver-invitation";
const EMAIL_REQUIRED = "Inicia sesi\u00f3n con el correo confirmado que recibi\u00f3 la invitaci\u00f3n.";
const MFA_REQUIRED = "Completa la verificaci\u00f3n SMS antes de aceptar la invitaci\u00f3n.";
const ACCEPT_ERROR = "No pudimos aceptar la invitaci\u00f3n. Puede haber vencido, sido revocada o no corresponder a esta cuenta.";
const CHECKING = "Verificando tu sesi\u00f3n y la invitaci\u00f3n...";
const ACCEPTING = "Aceptando invitaci\u00f3n...";
const ACCEPTED = "Aceptaste la invitaci\u00f3n y ya formas parte de la empresa.";

async function validateInvitationSession() {
  const token = window.sessionStorage.getItem(INVITATION_KEY) ?? "";
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new Error("invalid");

  const client = createClient();
  const { data, error: userError } = await client.auth.getUser();
  if (userError || !data.user?.email_confirmed_at) return { kind: "email" as const };

  const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
  if (assuranceError || assurance.currentLevel !== "aal2") return { kind: "mfa" as const };

  const { data: sessionData, error: sessionError } = await client.auth.getSession();
  if (sessionError || !sessionData.session?.access_token) throw new Error("invalid");

  return { kind: "ready" as const, token, accessToken: sessionData.session.access_token };
}

export function AcceptDriverInvitation() {
  const [status, setStatus] = useState(CHECKING);
  const [error, setError] = useState(false);
  const [ready, setReady] = useState(false);
  const [checking, setChecking] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);

  useEffect(() => {
    let active = true;
    void validateInvitationSession().then((result) => {
      if (!active) return;
      if (result.kind === "email") {
        setStatus(EMAIL_REQUIRED);
        return;
      }
      if (result.kind === "mfa") {
        setStatus(MFA_REQUIRED);
        return;
      }
      setReady(true);
      setStatus("La invitaci\u00f3n est\u00e1 lista para aceptar.");
    }).catch(() => {
      if (!active) return;
      setError(true);
      setStatus(ACCEPT_ERROR);
    }).finally(() => {
      if (active) setChecking(false);
    });
    return () => { active = false; };
  }, []);

  async function handleAccept() {
    if (submittingRef.current || checking || !ready) return;
    submittingRef.current = true;
    setSubmitting(true);
    setError(false);
    setStatus(CHECKING);

    try {
      const validation = await validateInvitationSession();
      if (validation.kind === "email") {
        setReady(false);
        setStatus(EMAIL_REQUIRED);
        return;
      }
      if (validation.kind === "mfa") {
        setReady(false);
        setStatus(MFA_REQUIRED);
        return;
      }

      setStatus(ACCEPTING);
      const response = await authenticatedApiFetch(
        "/api/driver-invitations/accept",
        validation.accessToken,
        process.env.NEXT_PUBLIC_API_URL,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: validation.token }) },
      );
      if (!response.ok) throw new Error("invalid");

      window.sessionStorage.removeItem(INVITATION_KEY);
      setReady(false);
      setStatus(ACCEPTED);
    } catch {
      setError(true);
      setStatus(ACCEPT_ERROR);
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-form-panel" aria-labelledby="accept-invitation-title">
        <div className="auth-form-wrap">
          <p className="auth-kicker">{"INVITACI\u00d3N DE EMPRESA"}</p>
          <h1 id="accept-invitation-title">{"Confirmar invitaci\u00f3n"}</h1>
          <p aria-live="polite" role={error ? "alert" : "status"} className={error ? "auth-error" : "auth-notice"}>{status}</p>
          {status.startsWith("Inicia sesi\u00f3n") && <p className="auth-switch"><Link href="/login?next=%2Finvitacion%2Fconductor%2Faceptar">{"Iniciar sesi\u00f3n"}</Link> {" \u00b7 "} <Link href="/registro?intent=invite">Crear cuenta</Link></p>}
          {status.startsWith("Completa") && <p className="auth-switch"><Link href="/login?next=%2Finvitacion%2Fconductor%2Faceptar">{"Continuar verificaci\u00f3n"}</Link></p>}
          {ready && <button className="auth-submit" type="button" disabled={checking || submitting} onClick={handleAccept}>
            {submitting ? (status === ACCEPTING ? ACCEPTING : "Verificando tu sesi\u00f3n...") : "Aceptar invitaci\u00f3n"}
          </button>}
          {status === ACCEPTED && <p className="auth-switch"><Link href="/servicios">Ir a Amira</Link></p>}
        </div>
      </section>
    </main>
  );
}
