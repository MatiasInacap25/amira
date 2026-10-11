"use client";

import { useState } from "react";
import type { DeliveryPhotoLink } from "@/lib/marketplace-api";
import { formatServiceDateTime, serviceActionErrorMessage } from "@/lib/service-status";

type Props = {
  onLoad: () => Promise<DeliveryPhotoLink>;
};

const LINK_EXPIRED_MESSAGE = "La foto ya no está disponible en este enlace. Vuelve a cargarla.";

/**
 * Loads the delivery photo on demand. The signed URL expires quickly, so it is requested per view and never stored.
 */
export function DeliveryPhoto({ onLoad }: Props) {
  const [link, setLink] = useState<DeliveryPhotoLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      setLink(await onLoad());
    } catch (cause) {
      setLink(null);
      setError(serviceActionErrorMessage(cause, "delivery-photo"));
    } finally {
      setBusy(false);
    }
  }

  if (!link) {
    return (
      <div className="account-service-photo">
        <button className="button button-secondary" disabled={busy} onClick={() => void load()} type="button">
          {busy ? "Cargando foto…" : "Ver foto de entrega"}
        </button>
        {error && <p className="account-service-form-error" role="alert">{error}</p>}
      </div>
    );
  }

  return (
    <figure className="account-service-photo">
      {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL; next/image would proxy and cache it */}
      <img
        alt="Foto de entrega del servicio"
        className="account-service-photo-image"
        onError={() => { setLink(null); setError(LINK_EXPIRED_MESSAGE); }}
        src={link.url}
      />
      <figcaption className="account-service-hint">
        Enlace válido hasta {formatServiceDateTime(link.expiresAt)}.{" "}
        <button className="account-service-inline-action" onClick={() => void load()} type="button">Recargar</button>
      </figcaption>
    </figure>
  );
}
