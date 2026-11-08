"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { SharedTripManager } from "@/components/account/shared-trip-manager";
import { acceptsAssuranceLevel } from "@/lib/auth/dev-mfa";
import { createClient } from "@/lib/supabase/client";

const SIGN_IN_PATH = "/login?next=%2Fcuenta%2Fviajes-compartidos";

export default function ProviderSharedTripsPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const client = createClient();
        const { data, error: authError } = await client.auth.getUser();
        if (authError || !data.user?.email_confirmed_at) {
          router.replace(SIGN_IN_PATH);
          return;
        }
        const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
        if (assuranceError || !acceptsAssuranceLevel(assurance.currentLevel)) {
          router.replace(SIGN_IN_PATH);
          return;
        }
        const { data: sessionData, error: sessionError } = await client.auth.getSession();
        if (sessionError || !sessionData.session?.access_token) throw new Error("La sesión expiró.");
        if (active) setToken(sessionData.session.access_token);
      } catch {
        if (active) setError("No pudimos verificar tu sesión. Inicia sesión de nuevo.");
      } finally {
        if (active) setChecking(false);
      }
    })();
    return () => { active = false; };
  }, [router]);

  return (
    <main className="auth-shell">
      <section className="auth-form-panel" aria-labelledby="shared-trips-title">
        <div className="auth-form-wrap">
          <Link className="auth-back-link" href="/panel">Volver al panel</Link>
          <p className="auth-kicker">PANEL DEL PROVEEDOR</p>
          <h1 id="shared-trips-title">Viajes compartidos</h1>
          <p>Revisa los viajes que publicaste desde tus servicios contratados y cierra los que ya no aceptan solicitudes.</p>
          {error && <p role="alert" aria-live="assertive" className="auth-error">{error}</p>}
          {token && <SharedTripManager token={token} />}
          {checking && !error && <p>Verificando tu sesión…</p>}
        </div>
      </section>
    </main>
  );
}
