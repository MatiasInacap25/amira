"use client";

import { useEffect, useRef, useState } from "react";
import type { ServiceDetail } from "@/lib/marketplace-api";
import { formatServiceDateTime, serviceActionErrorMessage } from "@/lib/service-status";

const refundFormatter = new Intl.NumberFormat("es-CL", {
  style: "currency", currency: "CLP", minimumFractionDigits: 0, maximumFractionDigits: 4,
});

export function ServiceCancellation({ service, pending, onCancel }: {
  service: ServiceDetail;
  pending: boolean;
  onCancel: () => Promise<unknown>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const cancellation = service.cancellation;
  const confirmationTitle = useRef<HTMLHeadingElement>(null);
  const summaryTitle = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (confirming) confirmationTitle.current?.focus();
  }, [confirming]);
  useEffect(() => {
    if (cancellation) summaryTitle.current?.focus();
  }, [cancellation]);

  async function confirm() {
    if (submitting.current) return;
    submitting.current = true;
    setError("");
    try {
      await onCancel();
      setConfirming(false);
    } catch (cause) {
      setError(serviceActionErrorMessage(cause, "cancel"));
    } finally {
      submitting.current = false;
    }
  }

  if (cancellation) return (
    <section aria-labelledby="service-cancellation-title" className="account-service-section">
      <h2 id="service-cancellation-title" ref={summaryTitle} tabIndex={-1}>Cancelación del servicio</h2>
      <p>Cancelado por {cancellation.cancelledBy === "customer" ? "el cliente" : "el prestador"} el {formatServiceDateTime(cancellation.cancelledAt)}.</p>
      <dl className="account-service-detail-facts">
        <div><dt>Reembolso simulado al cliente</dt><dd>{refundFormatter.format(cancellation.refundedAmount)}</dd></div>
        <div><dt>Adelanto retenido</dt><dd>{refundFormatter.format(cancellation.retainedAmount)}</dd></div>
      </dl>
      <p className="account-service-hint">No se mueve dinero real. El viaje compartido y los servicios de otros clientes no se cancelan.</p>
    </section>
  );

  if (!service.canCancel || service.status !== "confirmed" || service.startedAt !== null) return null;
  const customer = service.viewerRole === "customer";
  return (
    <section aria-labelledby="service-cancel-title" className="account-service-section">
      <h2 id="service-cancel-title">Cancelar servicio</h2>
      {confirming ? (
        <section aria-labelledby="service-cancel-confirm-title" className="account-service-confirm">
          <h3 id="service-cancel-confirm-title" ref={confirmationTitle} tabIndex={-1}>Confirmar cancelación</h3>
          <p>{customer
            ? "Se devolverá el 90 % del total al cliente y se retendrá el 10 % como adelanto."
            : "Se devolverá el 100 % del total al cliente, sin retención."}</p>
          <p>El reembolso es simulado: no se mueve dinero real.</p>
          <p>El viaje compartido y los servicios de otros clientes no se cancelan.</p>
          <div className="account-service-actions">
            <button className="button button-primary" disabled={pending} onClick={() => void confirm()} type="button">{pending ? "Cancelando…" : "Confirmar cancelación"}</button>
            <button className="button button-secondary" disabled={pending} onClick={() => { setConfirming(false); setError(""); requestAnimationFrame(() => trigger.current?.focus()); }} type="button">Volver</button>
          </div>
        </section>
      ) : (
        <button className="button button-secondary" onClick={() => setConfirming(true)} ref={trigger} type="button">Cancelar servicio</button>
      )}
      {error && <p className="account-service-form-error" role="alert">{error}</p>}
    </section>
  );
}
