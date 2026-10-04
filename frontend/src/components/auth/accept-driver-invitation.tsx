"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authenticatedApiFetch } from "@/lib/auth/account-api";
import { createClient } from "@/lib/supabase/client";

const INVITATION_KEY = "amira-driver-invitation";

export function AcceptDriverInvitation() {
  const [status, setStatus] = useState("Verificando tu sesión y la invitación…");
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const token = window.sessionStorage.getItem(INVITATION_KEY) ?? "";
        if (!/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new Error("invalid");
        const client = createClient();
        const { data, error: userError } = await client.auth.getUser();
        if (userError || !data.user?.email_confirmed_at) {
          if (active) setStatus("Inicia sesión con el correo confirmado que recibió la invitación.");
          return;
        }
        const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
        if (assuranceError || assurance.currentLevel !== "aal2") {
          if (active) setStatus("Completa la verificación SMS antes de aceptar la invitación.");
          return;
        }
        const { data: sessionData, error: sessionError } = await client.auth.getSession();
        if (sessionError || !sessionData.session?.access_token) throw new Error("invalid");
        const response = await authenticatedApiFetch("/api/driver-invitations/accept", sessionData.session.access_token,
          process.env.NEXT_PUBLIC_API_URL,
          { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }) });
        if (!response.ok) throw new Error("invalid");
        window.sessionStorage.removeItem(INVITATION_KEY);
        if (active) setStatus("Aceptaste la invitación y ya formas parte de la empresa.");
      } catch {
        if (active) {
          setError(true);
          setStatus("No pudimos aceptar la invitación. Puede haber vencido, sido revocada o no corresponder a esta cuenta.");
        }
      }
    })();
    return () => { active = false; };
  }, []);

  return (
    <main className="auth-shell">
      <section className="auth-form-panel" aria-labelledby="accept-invitation-title">
        <div className="auth-form-wrap">
          <p className="auth-kicker">INVITACIÓN DE EMPRESA</p>
          <h1 id="accept-invitation-title">Confirmar invitación</h1>
          <p aria-live="polite" role={error ? "alert" : "status"} className={error ? "auth-error" : "auth-notice"}>{status}</p>
          {status.startsWith("Inicia sesión") && <p className="auth-switch"><Link href="/login?next=%2Finvitacion%2Fconductor%2Faceptar">Iniciar sesión</Link> · <Link href="/registro?intent=invite">Crear cuenta</Link></p>}
          {status.startsWith("Completa") && <p className="auth-switch"><Link href="/login?next=%2Finvitacion%2Fconductor%2Faceptar">Continuar verificación</Link></p>}
          {status.startsWith("Aceptaste") && <p className="auth-switch"><Link href="/servicios">Ir a Amira</Link></p>}
        </div>
      </section>
    </main>
  );
}
