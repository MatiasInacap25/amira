"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ChatRequestError } from "@/lib/chats";
import { completeSimulatedPayment } from "@/lib/marketplace-api";
import { currentAccessToken } from "@/lib/provider-request-access";

type Props = {
  paymentId: string;
  token: string;
};

function completeErrorMessage(cause: unknown): string {
  if (cause instanceof ChatRequestError && cause.status === 404) return "Este pago simulado ya no está disponible.";
  return "No pudimos registrar tu decisión. Inténtalo nuevamente.";
}

// Development stand-in for a payment provider. The backend signs the confirmation; this page only sends the decision.
export function SimulatedCheckoutView({ paymentId, token }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState("");

  if (!paymentId || !token) {
    return (
      <article className="marketplace-state marketplace-empty chat-result" role="alert">
        <h1>Enlace de pago incompleto</h1>
        <p>Vuelve a la conversación e inicia el pago nuevamente.</p>
        <Link className="button button-secondary" href="/mensajes">Ver mis mensajes</Link>
      </article>
    );
  }

  async function decide(approve: boolean) {
    setBusy(approve ? "approve" : "reject");
    setError("");
    try {
      await completeSimulatedPayment(await currentAccessToken(), paymentId, token, approve);
      const status = approve ? "approved" : "rejected";
      router.replace(`/pagos/resultado?paymentId=${encodeURIComponent(paymentId)}&status=${status}`);
    } catch (cause) {
      setError(completeErrorMessage(cause));
      setBusy(null);
    }
  }

  return (
    <article className="marketplace-state chat-result chat-simulated-checkout" aria-labelledby="simulated-checkout-title">
      <p className="eyebrow">PAGO DE PRUEBA</p>
      <h1 id="simulated-checkout-title">Pago simulado</h1>
      <p>Este entorno de desarrollo no cobra dinero real. Elige el resultado que quieres probar.</p>
      <div className="chat-result-actions">
        <button className="button button-primary" disabled={busy !== null} onClick={() => void decide(true)} type="button">
          {busy === "approve" ? "Aprobando…" : "Aprobar pago"}
        </button>
        <button className="button button-secondary" disabled={busy !== null} onClick={() => void decide(false)} type="button">
          {busy === "reject" ? "Rechazando…" : "Rechazar pago"}
        </button>
      </div>
      {error && <p className="chat-quotation-error" role="alert">{error}</p>}
    </article>
  );
}
