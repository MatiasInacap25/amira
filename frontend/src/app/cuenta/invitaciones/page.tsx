"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authenticatedApiFetch } from "@/lib/auth/account-api";
import { createClient } from "@/lib/supabase/client";

type Invitation = { id: string; email: string; created_at: string; expires_at: string; status: "pending" | "expired" | "revoked" | "accepted" };

export default function CompanyInvitationsPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [companyTaxId, setCompanyTaxId] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  const api = useCallback((path: string, options?: RequestInit) =>
    authenticatedApiFetch(path, token, process.env.NEXT_PUBLIC_API_URL, options), [token]);

  const reload = useCallback(async () => {
    if (!token) return;
    const response = await api("/api/company/profiles/me/driver-invitations");
    if (!response.ok) throw new Error("No pudimos cargar las invitaciones.");
    const body = await response.json() as { invitations: Invitation[] };
    setInvitations(body.invitations);
  }, [api, token]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const client = createClient();
        const { data, error: authError } = await client.auth.getUser();
        if (authError || !data.user?.email_confirmed_at) {
          router.replace("/login?next=%2Fcuenta%2Finvitaciones");
          return;
        }
        const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
        if (assuranceError || assurance.currentLevel !== "aal2") {
          router.replace("/login?next=%2Fcuenta%2Finvitaciones");
          return;
        }
        const { data: sessionData, error: sessionError } = await client.auth.getSession();
        if (sessionError || !sessionData.session?.access_token) throw new Error("La sesión expiró.");
        if (active) setToken(sessionData.session.access_token);
      } catch {
        if (active) setError("No pudimos verificar tu sesión. Inicia sesión de nuevo.");
      } finally {
        if (active) setBusy(false);
      }
    })();
    return () => { active = false; };
  }, [router]);

  useEffect(() => {
    if (!token) return;
    void Promise.resolve().then(() => reload()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "No pudimos cargar las invitaciones."));
  }, [reload, token]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await api("/api/company/profiles/me/driver-invitations", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, ...(companyTaxId.trim() ? { company_tax_id: companyTaxId.trim() } : {}) }),
      });
      if (!response.ok) throw new Error("No pudimos enviar la invitación. Revisa la dirección o intenta más tarde.");
      setEmail(""); setNotice("Invitación enviada. El vínculo vence en siete días."); await reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "No pudimos enviar la invitación."); }
    finally { setBusy(false); }
  }

  async function act(invitation: Invitation, action: "revoke" | "reissue") {
    setBusy(true); setError(""); setNotice("");
    try {
      const path = `/api/company/profiles/me/driver-invitations/${invitation.id}${action === "reissue" ? "/reissue" : ""}`;
      const response = await api(path, action === "reissue" ? { method: "POST" } : { method: "DELETE" });
      if (!response.ok) throw new Error("No pudimos actualizar esta invitación.");
      setNotice(action === "reissue" ? "Nuevo vínculo enviado; el anterior dejó de funcionar." : "Invitación revocada.");
      await reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "No pudimos actualizar esta invitación."); }
    finally { setBusy(false); }
  }

  return (
    <main className="auth-shell">
      <section className="auth-form-panel" aria-labelledby="invitations-title">
        <div className="auth-form-wrap">
          <Link className="auth-back-link" href="/servicios">Volver a Amira</Link>
          <p className="auth-kicker">GESTIÓN DE EMPRESA</p>
          <h1 id="invitations-title">Invitar conductores</h1>
          <p>Las personas invitadas deberán confirmar su correo, completar la verificación de acceso y aceptar antes de quedar vinculadas.</p>
          <p>El perfil independiente se convierte en empresa solo cuando la primera persona invitada acepta.</p>
          {notice && <p role="status" aria-live="polite" className="auth-notice">{notice}</p>}
          {error && <p role="alert" aria-live="assertive" className="auth-error">{error}</p>}
          <form className="auth-form" onSubmit={create}>
            <label className="auth-field" htmlFor="driver-invitation-email">Correo de la persona invitada
              <input id="driver-invitation-email" autoComplete="email" type="email" required maxLength={320} value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
            <label className="auth-field" htmlFor="driver-invitation-company-tax-id">RUT de empresa (requerido solo para el primer conductor)
              <input id="driver-invitation-company-tax-id" autoComplete="off" maxLength={16} value={companyTaxId} onChange={(event) => setCompanyTaxId(event.target.value)} />
            </label>
            <button className="auth-submit" disabled={busy || !token} type="submit">{busy ? "Procesando…" : "Enviar invitación"}</button>
          </form>
          <h2>Invitaciones</h2>
          {invitations.length === 0 ? <p>No hay invitaciones todavía.</p> : <ul>
            {invitations.map((invitation) => <li key={invitation.id}>
              <strong>{invitation.email}</strong> · {invitation.status} · vence {new Date(invitation.expires_at).toLocaleDateString("es-CL")}
              {invitation.status === "pending" && <>
                <button className="auth-secondary-action" disabled={busy} onClick={() => void act(invitation, "reissue")} type="button">Reenviar</button>
                <button className="auth-secondary-action" disabled={busy} onClick={() => void act(invitation, "revoke")} type="button">Revocar</button>
              </>}
            </li>)}
          </ul>}
        </div>
      </section>
    </main>
  );
}
