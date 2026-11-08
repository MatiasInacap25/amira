"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { RegionCommuneSelect, type RegionCommuneValue } from "@/components/marketplace/region-commune-select";
import { acceptsAssuranceLevel } from "@/lib/auth/dev-mfa";
import {
  REQUEST_IMAGE_ACCEPT,
  createServiceRequest,
  uploadRequestImage,
  validateRequestImage,
  type ProviderProfile,
  type ServiceRequestCreated,
  type ServiceRequestInput,
} from "@/lib/marketplace-api";
import { createClient } from "@/lib/supabase/client";

type Props = {
  open: boolean;
  profile: Pick<ProviderProfile, "profileId" | "providerName" | "services">;
  selectedServiceId: string;
  onClose: () => void;
  // Set when the customer joins a shared trip: origin and destination become the pickup and delivery along its route.
  requestedTrip?: { tripId: string; origin: string; destination: string } | null;
};

type AttachedPhoto = { file: File; previewUrl: string };

const emptyLocation: RegionCommuneValue = { regionCode: "", communeCode: "" };

function signInHref() {
  const next = `${window.location.pathname}${window.location.search}`;
  return `/login?next=${encodeURIComponent(next)}`;
}

// date inputs expect local "YYYY-MM-DD" values; the browser compares them as local dates.
function localDateToday(now = new Date()) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

const schedulePairingMessage = "Indica la fecha y la hora deseadas, o deja ambas vacías.";

export function QuoteRequestDialog({ open, profile, selectedServiceId, onClose, requestedTrip = null }: Props) {
  const joiningTrip = requestedTrip !== null;
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [signInPath, setSignInPath] = useState("/login");
  const [serviceId, setServiceId] = useState(selectedServiceId);
  const [originLocation, setOriginLocation] = useState<RegionCommuneValue>(emptyLocation);
  const [destinationLocation, setDestinationLocation] = useState<RegionCommuneValue>(emptyLocation);
  const [scheduleError, setScheduleError] = useState("");
  const [photos, setPhotos] = useState<AttachedPhoto[]>([]);
  const [photoError, setPhotoError] = useState("");
  const [photoUploadFailed, setPhotoUploadFailed] = useState(false);
  const photosRef = useRef<AttachedPhoto[]>([]);
  const selectedService = profile.services.find((service) => service.serviceTypeId === serviceId);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
  }, [open]);

  // Preview URLs are revoked when a photo is removed and when the dialog closes.
  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);
  useEffect(() => () => {
    photosRef.current.forEach((photo) => URL.revokeObjectURL(photo.previewUrl));
  }, []);

  function addPhotos(files: File[]) {
    const accepted: AttachedPhoto[] = [];
    let message = "";
    for (const file of files) {
      const problem = validateRequestImage(file, photos.length + accepted.length);
      if (problem) {
        message = problem;
        continue;
      }
      accepted.push({ file, previewUrl: URL.createObjectURL(file) });
    }
    setPhotos([...photos, ...accepted]);
    setPhotoError(message);
  }

  function removePhoto(index: number) {
    const removed = photos[index];
    if (removed) URL.revokeObjectURL(removed.previewUrl);
    setPhotos(photos.filter((_, position) => position !== index));
    setPhotoError("");
  }

  // Uploads run one after another after the request exists. Each failure is counted, never thrown,
  // so the request stays created and the customer is told that some photos were not attached.
  async function uploadPhotos(requestId: string, accessToken: string, files: File[]): Promise<number> {
    let failed = 0;
    for (const file of files) {
      try {
        const response = await uploadRequestImage(accessToken, requestId, file);
        if (!response.ok) failed += 1;
      } catch {
        failed += 1;
      }
    }
    return failed;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (!selectedService) {
      setError("Elige uno de los servicios publicados para continuar.");
      return;
    }
    if (!originLocation.communeCode || !destinationLocation.communeCode) {
      setError("Elige la comuna de origen y de destino para continuar.");
      return;
    }
    const form = new FormData(event.currentTarget);
    const requestedDate = String(form.get("requestedDate") ?? "");
    const requestedTime = String(form.get("requestedTime") ?? "");
    if (Boolean(requestedDate) !== Boolean(requestedTime)) {
      setScheduleError(schedulePairingMessage);
      return;
    }
    setScheduleError("");
    const requestedAt = requestedDate && requestedTime ? `${requestedDate}T${requestedTime}` : "";
    if (requestedAt && new Date(requestedAt).getTime() < Date.now()) {
      setError("La fecha deseada no puede estar en el pasado.");
      return;
    }
    const weight = String(form.get("estimatedWeight") ?? "").trim();
    const volume = String(form.get("estimatedVolume") ?? "").trim();
    const input: ServiceRequestInput = {
      profileId: profile.profileId,
      serviceTypeId: selectedService.serviceTypeId,
      originCommuneCode: originLocation.communeCode,
      destinationCommuneCode: destinationLocation.communeCode,
      origin: String(form.get("origin") ?? "").trim(),
      destination: String(form.get("destination") ?? "").trim(),
      requestedAt: requestedAt ? new Date(requestedAt).toISOString() : null,
      estimatedWeight: weight || null,
      estimatedVolume: volume || null,
      description: String(form.get("description") ?? "").trim() || null,
      // The measures input was removed; the API field stays for legacy rows.
      cargoMeasurements: null,
      // A join request already means the customer accepts sharing, so the question is not asked in that mode.
      acceptsSharing: joiningTrip || String(form.get("acceptsSharing") ?? "false") === "true",
      // Only a join request carries the trip; a normal quote request never sends the field.
      ...(requestedTrip ? { requestedTripId: requestedTrip.tripId } : {}),
    };

    setBusy(true);
    setError("");
    setSignInPath(signInHref());
    try {
      const client = createClient();
      const { data: userData, error: userError } = await client.auth.getUser();
      if (userError || !userData.user?.email_confirmed_at) {
        setError("Inicia sesión con un correo confirmado y verifica tu teléfono para enviar la solicitud.");
        return;
      }
      const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
      if (assuranceError) throw assuranceError;
      if (!acceptsAssuranceLevel(assurance.currentLevel)) {
        setError("Completa la verificación por SMS antes de solicitar una cotización.");
        return;
      }
      const { data: sessionData, error: sessionError } = await client.auth.getSession();
      if (sessionError || !sessionData.session?.access_token) {
        setError("Tu sesión expiró. Inicia sesión nuevamente para continuar.");
        return;
      }

      const response = await createServiceRequest(input, sessionData.session.access_token);
      if (!response.ok) {
        if (response.status === 401) setError("Tu sesión expiró. Inicia sesión nuevamente para continuar.");
        else if (response.status === 403) setError("Esta cuenta no puede enviar solicitudes de cotización.");
        else if (response.status === 404) setError("El servicio ya no está disponible. Actualiza el perfil e inténtalo nuevamente.");
        else if (response.status === 422) setError("Revisa los datos de origen, destino y carga.");
        else setError("No pudimos enviar la solicitud. Inténtalo nuevamente.");
        return;
      }
      const created = await response.json() as ServiceRequestCreated;
      // The request is already created; a failed photo never turns it into an error.
      if (photos.length > 0) {
        const failed = await uploadPhotos(created.requestId, sessionData.session.access_token, photos.map((photo) => photo.file));
        setPhotoUploadFailed(failed > 0);
      }
      setSuccess(true);
    } catch (cause) {
      setError(cause instanceof Error && /API todav[ií]a no est[aá] configurada/i.test(cause.message)
        ? cause.message
        : "No pudimos enviar la solicitud. Revisa tu conexión e inténtalo nuevamente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      aria-labelledby="quote-dialog-title"
      className="quote-dialog"
      /* While submitting or uploading photos, Escape is refused so the upload outcome notice can be shown. */
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}
      onClose={onClose}
      ref={dialogRef}
    >
      <div className="quote-dialog-header">
        <div>
          <p className="eyebrow">{requestedTrip ? "SUMARME A UN VIAJE" : "SOLICITUD DE COTIZACIÓN"}</p>
          <h2 id="quote-dialog-title">Cuéntanos qué necesitas</h2>
          {requestedTrip && (
            <p className="quote-request-note">Viaje: {requestedTrip.origin} a {requestedTrip.destination}. Indica dónde recogemos y entregamos tu carga a lo largo de la ruta. El transportista decide si la incorpora.</p>
          )}
        </div>
        <button aria-label="Cerrar solicitud" className="quote-dialog-close" disabled={busy} onClick={onClose} type="button">×</button>
      </div>
      {success ? (
        <div className="quote-dialog-success" role="status">
          <h3>Solicitud enviada</h3>
          <p>El prestador podrá revisar los detalles y responderte. Aún no se ha confirmado una reserva ni realizado un pago.</p>
          {photoUploadFailed && <p className="quote-dialog-notice" role="alert">La solicitud se envió, pero no pudimos adjuntar algunas fotos.</p>}
          <button className="button button-primary" onClick={onClose} type="button">Listo</button>
        </div>
      ) : (
        <form className="quote-request-form" onSubmit={submit}>
          <label className="marketplace-field" htmlFor="quote-service">
            <span>Servicio</span>
            <select disabled={profile.services.length === 1 && Boolean(profile.services.find((service) => service.serviceTypeId === selectedServiceId))} id="quote-service" onChange={(event) => { setServiceId(event.target.value); setError(""); }} required value={selectedService ? serviceId : ""}>
              {!selectedService && <option value="">Elige un servicio</option>}
              {profile.services.map((service) => <option key={service.serviceTypeId} value={service.serviceTypeId}>{service.name}</option>)}
            </select>
          </label>
          {!joiningTrip && (
            <>
              <label className="marketplace-field" htmlFor="quote-accepts-sharing">
                <span>¿Aceptas compartir el vehículo con otro cliente?</span>
                <select aria-describedby="quote-accepts-sharing-hint" defaultValue="false" id="quote-accepts-sharing" name="acceptsSharing">
                  <option value="false">No</option>
                  <option value="true">Sí</option>
                </select>
              </label>
              <p className="quote-request-note" id="quote-accepts-sharing-hint">Si aceptas, el proveedor puede sumar la carga de otro cliente en el mismo viaje y publicarlo como viaje compartido.</p>
            </>
          )}
          <div className="quote-request-grid">
            <RegionCommuneSelect
              communeLabel={joiningTrip ? "Comuna de recogida" : "Comuna de origen"}
              idPrefix="quote-origin"
              onChange={setOriginLocation}
              regionLabel={joiningTrip ? "Región de recogida" : "Región de origen"}
              required
              value={originLocation}
            />
            <label className="marketplace-field" htmlFor="quote-origin-address"><span>{joiningTrip ? "Dirección de recogida" : "Dirección de origen"}</span><input autoComplete="street-address" id="quote-origin-address" maxLength={300} name="origin" required /></label>
            <RegionCommuneSelect
              communeLabel={joiningTrip ? "Comuna de entrega" : "Comuna de destino"}
              idPrefix="quote-destination"
              onChange={setDestinationLocation}
              regionLabel={joiningTrip ? "Región de entrega" : "Región de destino"}
              required
              value={destinationLocation}
            />
            <label className="marketplace-field" htmlFor="quote-destination-address"><span>{joiningTrip ? "Dirección de entrega" : "Dirección de destino"}</span><input autoComplete="street-address" id="quote-destination-address" maxLength={300} name="destination" required /></label>
            <label className="marketplace-field" htmlFor="quote-date"><span>Fecha deseada</span><input aria-invalid={scheduleError ? true : undefined} id="quote-date" min={localDateToday()} name="requestedDate" onChange={() => setScheduleError("")} type="date" /></label>
            <label className="marketplace-field" htmlFor="quote-time"><span>Hora deseada</span><input aria-invalid={scheduleError ? true : undefined} id="quote-time" name="requestedTime" onChange={() => setScheduleError("")} type="time" /></label>
            <label className="marketplace-field" htmlFor="quote-weight"><span>Peso estimado (kg) (opcional)</span><input id="quote-weight" min="0" name="estimatedWeight" step="0.01" type="number" /></label>
            <label className="marketplace-field" htmlFor="quote-volume"><span>Volumen estimado (m³) (opcional)</span><input id="quote-volume" min="0" name="estimatedVolume" step="0.001" type="number" /></label>
          </div>
          {scheduleError && <p className="marketplace-field-error" id="quote-schedule-error" role="alert">{scheduleError}</p>}
          <label className="marketplace-field" htmlFor="quote-description"><span>Detalles de la solicitud</span><textarea id="quote-description" maxLength={4000} name="description" rows={4} /></label>
          <div className="quote-photos">
            <label className="marketplace-field" htmlFor="quote-images">
              <span>Fotos de la carga (opcional)</span>
              <input
                accept={REQUEST_IMAGE_ACCEPT}
                id="quote-images"
                multiple
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  event.target.value = "";
                  addPhotos(files);
                }}
                type="file"
              />
            </label>
            {photos.length > 0 && (
              <ul className="quote-photo-list">
                {photos.map((photo, index) => (
                  <li className="quote-photo-item" key={photo.previewUrl}>
                    {/* Object URLs from the local file; next/image does not apply to blob previews. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img alt={`Vista previa de la foto ${index + 1}`} src={photo.previewUrl} />
                    <button aria-label={`Quitar la foto ${index + 1}`} className="quote-photo-remove" onClick={() => removePhoto(index)} type="button">×</button>
                  </li>
                ))}
              </ul>
            )}
            {photoError && <p className="marketplace-field-error" id="quote-photo-error" role="alert">{photoError}</p>}
          </div>
          {error && (
            <div className="quote-request-error" id="quote-request-error" role="alert">
              <p>{error}</p>
              {error.startsWith("Inicia sesión") && <Link href={signInPath}>Iniciar sesión</Link>}
              {error.startsWith("Completa la verificación") && <Link href={signInPath}>Continuar con verificación por SMS</Link>}
            </div>
          )}
          <p className="quote-request-note">Enviar la solicitud no confirma una reserva ni realiza un pago.</p>
          <div className="quote-dialog-actions">
            <button className="button button-secondary" disabled={busy} onClick={onClose} type="button">Cancelar</button>
            <button className="button button-primary" disabled={busy || !selectedService} type="submit">{busy ? "Enviando…" : "Enviar solicitud"}</button>
          </div>
        </form>
      )}
    </dialog>
  );
}
