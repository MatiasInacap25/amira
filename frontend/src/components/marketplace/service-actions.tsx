"use client";

import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  DELIVERY_PHOTO_ACCEPT,
  DELIVERY_PHOTO_MAX_BYTES,
  deliveryPhotoRejection,
  serviceActionErrorMessage,
} from "@/lib/service-status";
import type { ServiceStatus } from "@/lib/marketplace-api";

type Props = {
  status: ServiceStatus;
  hasAssignments: boolean;
  startPending: boolean;
  completePending: boolean;
  onStart: () => Promise<unknown>;
  onComplete: (photo: File) => Promise<unknown>;
};

const MAX_PHOTO_MB = DELIVERY_PHOTO_MAX_BYTES / (1024 * 1024);

/**
 * Provider actions for a service. The viewer's own assignment is not visible in the detail, so the buttons
 * are shown to every provider viewer and the backend answers 403 when the viewer may not act.
 */
export function ServiceActions({ status, hasAssignments, startPending, completePending, onStart, onComplete }: Props) {
  const [error, setError] = useState("");

  async function start() {
    setError("");
    try {
      await onStart();
    } catch (cause) {
      setError(serviceActionErrorMessage(cause, "start"));
    }
  }

  if (status === "confirmed") {
    return (
      <div className="account-service-actions">
        {hasAssignments ? (
          <button className="button button-primary" disabled={startPending} onClick={() => void start()} type="button">
            {startPending ? "Iniciando…" : "Iniciar servicio"}
          </button>
        ) : (
          <p className="account-service-empty">Asigna al menos un conductor y un vehículo para iniciar el servicio.</p>
        )}
        {error && <p className="account-service-form-error" role="alert">{error}</p>}
      </div>
    );
  }

  if (status === "in_progress") {
    return <CompleteServiceForm busy={completePending} onComplete={onComplete} />;
  }

  return null;
}

function CompleteServiceForm({ busy, onComplete }: { busy: boolean; onComplete: (photo: File) => Promise<unknown> }) {
  const inputId = useId();
  const hintId = useId();
  const [photo, setPhoto] = useState<File | null>(null);
  const [error, setError] = useState("");
  const previewRef = useRef<HTMLImageElement>(null);

  // The object URL is written straight to the preview image and lives as long as the selected file.
  // The cleanup revokes it when the selection changes or the form unmounts.
  useEffect(() => {
    const preview = previewRef.current;
    if (!photo || !preview) return;
    const url = URL.createObjectURL(photo);
    preview.src = url;
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  function choosePhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setError("");
    if (file) {
      const rejection = deliveryPhotoRejection(file);
      if (rejection) {
        setError(rejection);
        setPhoto(null);
        event.target.value = "";
        return;
      }
    }
    setPhoto(file);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!photo || busy) return;
    setError("");
    try {
      await onComplete(photo);
    } catch (cause) {
      setError(serviceActionErrorMessage(cause, "complete"));
    }
  }

  return (
    <form className="account-service-complete-form" noValidate onSubmit={submit}>
      <div className="marketplace-field">
        <label htmlFor={inputId}>Foto de entrega</label>
        <input
          accept={DELIVERY_PHOTO_ACCEPT}
          aria-describedby={hintId}
          aria-invalid={error ? true : undefined}
          disabled={busy}
          id={inputId}
          name="photo"
          onChange={choosePhoto}
          required
          type="file"
        />
        <small className="account-service-hint" id={hintId}>JPEG, PNG o WebP, máximo {MAX_PHOTO_MB} MB.</small>
      </div>

      {/* eslint-disable-next-line @next/next/no-img-element -- local object URL, not optimizable by next/image */}
      <img
        alt="Vista previa de la foto de entrega seleccionada"
        className="account-service-photo-preview"
        height={160}
        hidden={!photo}
        ref={previewRef}
        width={160}
      />

      {error && <p className="account-service-form-error" role="alert">{error}</p>}

      <div className="account-service-actions">
        <button className="button button-primary" disabled={busy || !photo} type="submit">
          {busy ? "Finalizando…" : "Finalizar servicio"}
        </button>
      </div>
    </form>
  );
}
