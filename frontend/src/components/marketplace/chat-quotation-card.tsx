"use client";

import { useState } from "react";
import { ChatRequestError, type ChatQuotation, type ChatViewerRole } from "@/lib/chats";
import { canPayQuotation, canRejectQuotation, formatClp, quotationStatusLabel } from "@/lib/chat-quotations";
import { createQuotationPayment, rejectQuotation } from "@/lib/marketplace-api";
import { currentAccessToken } from "@/lib/provider-request-access";

type Props = {
  quotation: ChatQuotation;
  viewerRole: ChatViewerRole;
  onChanged: () => void;
};

const dateFormatter = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" });

// The customer's actions are offered only while the quotation is pending and unexpired. The backend re-checks both.
function actionErrorMessage(cause: unknown, verb: "pagar" | "rechazar"): string {
  if (cause instanceof ChatRequestError && cause.status === 409) {
    return `Esta cotización ya no se puede ${verb}. Actualizamos la conversación.`;
  }
  return `No pudimos ${verb === "pagar" ? "iniciar el pago" : "rechazar la cotización"}. Inténtalo nuevamente.`;
}

export function ChatQuotationCard({ quotation, viewerRole, onChanged }: Props) {
  const [busy, setBusy] = useState<"pay" | "reject" | null>(null);
  const [confirmingReject, setConfirmingReject] = useState(false);
  const [error, setError] = useState("");
  const now = new Date();
  const isCustomer = viewerRole === "customer";
  const showPay = isCustomer && canPayQuotation(quotation, now);
  const showReject = isCustomer && canRejectQuotation(quotation, now);

  async function pay() {
    setBusy("pay");
    setError("");
    try {
      const { checkoutUrl } = await createQuotationPayment(await currentAccessToken(), quotation.quotationId);
      window.location.assign(checkoutUrl);
    } catch (cause) {
      setError(actionErrorMessage(cause, "pagar"));
      setBusy(null);
      onChanged();
    }
  }

  async function reject() {
    setBusy("reject");
    setError("");
    try {
      await rejectQuotation(await currentAccessToken(), quotation.quotationId);
      setConfirmingReject(false);
      onChanged();
    } catch (cause) {
      setError(actionErrorMessage(cause, "rechazar"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <article aria-labelledby={`quotation-${quotation.quotationId}-title`} className={`chat-quotation chat-quotation-${quotation.status}`}>
      <header className="chat-quotation-header">
        <h3 id={`quotation-${quotation.quotationId}-title`}>Cotización</h3>
        <span className="chat-quotation-status">{quotationStatusLabel(quotation.status)}</span>
      </header>
      <p className="chat-quotation-amount">{formatClp(quotation.amount)}</p>
      <dl className="chat-quotation-details">
        <div>
          <dt>Servicio</dt>
          <dd>{dateFormatter.format(new Date(quotation.serviceAt))}</dd>
        </div>
        <div>
          <dt>Descripción</dt>
          <dd>{quotation.description}</dd>
        </div>
        {quotation.status === "pending" && (
          <div>
            <dt>Vence</dt>
            <dd>{dateFormatter.format(new Date(quotation.expiresAt))}</dd>
          </div>
        )}
        {quotation.status === "paid" && quotation.paidAt && (
          <div>
            <dt>Pagada el</dt>
            <dd>{dateFormatter.format(new Date(quotation.paidAt))}</dd>
          </div>
        )}
      </dl>

      {showPay && !confirmingReject && (
        <div className="chat-quotation-actions">
          <button className="button button-primary" disabled={busy !== null} onClick={() => void pay()} type="button">
            {busy === "pay" ? "Abriendo pago…" : "Pagar"}
          </button>
          {showReject && (
            <button className="button button-secondary" disabled={busy !== null} onClick={() => setConfirmingReject(true)} type="button">
              Rechazar
            </button>
          )}
        </div>
      )}

      {showReject && confirmingReject && (
        <div className="chat-quotation-confirm" role="group" aria-label="Confirmar rechazo">
          <p>¿Rechazar esta cotización? El prestador podrá enviarte otra.</p>
          <div className="chat-quotation-actions">
            <button className="button button-secondary" disabled={busy !== null} onClick={() => setConfirmingReject(false)} type="button">
              Volver
            </button>
            <button className="button button-primary chat-quotation-reject" disabled={busy !== null} onClick={() => void reject()} type="button">
              {busy === "reject" ? "Rechazando…" : "Sí, rechazar"}
            </button>
          </div>
        </div>
      )}

      {error && <p className="chat-quotation-error" role="alert">{error}</p>}
    </article>
  );
}
