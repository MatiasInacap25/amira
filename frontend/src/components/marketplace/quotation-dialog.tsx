"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ChatRequestError } from "@/lib/chats";
import {
  QUOTATION_DEFAULT_VALIDITY_HOURS,
  QUOTATION_MAX_VALIDITY_HOURS,
  QUOTATION_MIN_VALIDITY_HOURS,
  validateQuotationDraft,
} from "@/lib/chat-quotations";
import { createQuotation } from "@/lib/marketplace-api";
import { currentAccessToken } from "@/lib/provider-request-access";

type Props = {
  chatId: string;
  onClose: () => void;
  onCreated: () => void;
};

// datetime-local expects local "YYYY-MM-DDTHH:mm" values; the browser compares them as local time.
function localDateTimeNow(now = new Date()) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function sendErrorMessage(cause: unknown): string {
  if (cause instanceof ChatRequestError) {
    if (cause.status === 403) return "Solo el prestador de esta conversación puede enviar cotizaciones.";
    if (cause.status === 404) return "Esta conversación ya no está disponible.";
    if (cause.status === 422) return "Revisa los datos de la cotización.";
  }
  return "No pudimos enviar la cotización. Revisa tu conexión e inténtalo nuevamente.";
}

// Mounted only while open, so every opening starts with an empty form.
export function QuotationDialog({ chatId, onClose, onCreated }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [minServiceAt] = useState(() => localDateTimeNow());

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const serviceAtLocal = String(form.get("serviceAt") ?? "");
    const draft = {
      amount: Number(form.get("amount")),
      serviceAt: serviceAtLocal,
      description: String(form.get("description") ?? "").trim(),
      validityHours: Number(form.get("validityHours")),
    };
    const validation = validateQuotationDraft(draft);
    if (validation) {
      setError(validation);
      return;
    }
    if (new Date(serviceAtLocal).getTime() < Date.now()) {
      setError("La fecha del servicio no puede estar en el pasado.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      await createQuotation(await currentAccessToken(), chatId, {
        amount: draft.amount,
        serviceAt: new Date(serviceAtLocal).toISOString(),
        description: draft.description,
        validityHours: draft.validityHours,
      });
      onCreated();
      dialogRef.current?.close();
    } catch (cause) {
      setError(sendErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      aria-labelledby="quotation-dialog-title"
      className="quote-dialog"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClose={onClose}
      ref={dialogRef}
    >
      <div className="quote-dialog-header">
        <div>
          <p className="eyebrow">COTIZACIÓN</p>
          <h2 id="quotation-dialog-title">Envía tu cotización</h2>
        </div>
        <button aria-label="Cerrar cotización" className="quote-dialog-close" onClick={() => dialogRef.current?.close()} type="button">×</button>
      </div>
      <form className="quote-request-form" noValidate onSubmit={submit}>
        <label className="marketplace-field" htmlFor="quotation-amount">
          <span>Monto (CLP)</span>
          <input id="quotation-amount" inputMode="numeric" min={1} name="amount" placeholder="Ej: 125000" step={1} type="number" />
        </label>
        <label className="marketplace-field" htmlFor="quotation-service-at">
          <span>Fecha del servicio</span>
          <input id="quotation-service-at" min={minServiceAt} name="serviceAt" type="datetime-local" />
        </label>
        <label className="marketplace-field" htmlFor="quotation-description">
          <span>Descripción</span>
          <textarea id="quotation-description" maxLength={1000} name="description" placeholder="Qué incluye el servicio y el vehículo." rows={4} />
        </label>
        <label className="marketplace-field" htmlFor="quotation-validity">
          <span>Vigencia (horas)</span>
          <input
            defaultValue={QUOTATION_DEFAULT_VALIDITY_HOURS}
            id="quotation-validity"
            inputMode="numeric"
            max={QUOTATION_MAX_VALIDITY_HOURS}
            min={QUOTATION_MIN_VALIDITY_HOURS}
            name="validityHours"
            step={1}
            type="number"
          />
          <small className="quotation-field-hint">Entre {QUOTATION_MIN_VALIDITY_HOURS} y {QUOTATION_MAX_VALIDITY_HOURS} horas. El cliente puede pagarla hasta que venza.</small>
        </label>
        {error && <p className="quote-dialog-error" role="alert">{error}</p>}
        <div className="quote-dialog-actions">
          <button className="button button-secondary" onClick={() => dialogRef.current?.close()} type="button">Cancelar</button>
          <button className="button button-primary" disabled={busy} type="submit">{busy ? "Enviando…" : "Enviar cotización"}</button>
        </div>
      </form>
    </dialog>
  );
}
