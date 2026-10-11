"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const INVITATION_KEY = "amira-driver-invitation";

export function DriverInvitationLanding() {
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    const fragment = window.location.hash.slice(1);
    const params = new URLSearchParams(fragment);
    const token = params.get("token") ?? "";
    const safeToken = /^[A-Za-z0-9_-]{32,128}$/.test(token) ? token : "";
    try {
      if (safeToken) window.sessionStorage.setItem(INVITATION_KEY, safeToken);
      else if (fragment) window.sessionStorage.removeItem(INVITATION_KEY);
      else {
        const retainedToken = window.sessionStorage.getItem(INVITATION_KEY) ?? "";
        void Promise.resolve().then(() => setAvailable(/^[A-Za-z0-9_-]{32,128}$/.test(retainedToken)));
        return;
      }
    } catch {
      void Promise.resolve().then(() => setAvailable(false));
      return;
    }
    window.history.replaceState(null, "", window.location.pathname);
    void Promise.resolve().then(() => setAvailable(Boolean(safeToken)));
  }, []);

  return (
    <main className="auth-shell">
      <section className="auth-form-panel" aria-labelledby="invitation-title">
        <div className="auth-form-wrap">
          <p className="auth-kicker">INVITACIÓN DE EMPRESA</p>
          <h1 id="invitation-title">Únete a un equipo de Amira</h1>
          {available ? <>
            <p>Inicia sesión o crea una cuenta con el correo que recibió la invitación. La empresa quedará vinculada solo cuando aceptes después de confirmar tu correo y verificar tu acceso.</p>
            <p className="auth-step-actions"><Link className="auth-submit" href="/login?next=%2Finvitacion%2Fconductor%2Faceptar">Iniciar sesión</Link></p>
            <p className="auth-switch">¿Todavía no tienes cuenta? <Link href="/registro?intent=invite">Crear cuenta desde la invitación</Link></p>
          </> : <>
            <p role="alert" className="auth-error">El enlace de invitación no es válido o ya no está disponible.</p>
            <Link href="/login">Ir al inicio de sesión</Link>
          </>}
        </div>
      </section>
    </main>
  );
}
