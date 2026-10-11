"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { RegionCommuneSelect, type RegionCommuneValue } from "@/components/marketplace/region-commune-select";
import { acceptsAssuranceLevel } from "@/lib/auth/dev-mfa";
import { createServiceRequest, type ProviderProfile, type ServiceRequestInput } from "@/lib/marketplace-api";
import { createClient } from "@/lib/supabase/client";

type Props = {
  open: boolean;
  profile: Pick<ProviderProfile, "profileId" | "providerName" | "services">;
  selectedServiceId: string;
  onClose: () => void;
};

const emptyLocation: RegionCommuneValue = { regionCode: "", communeCode: "" };

function signInHref() {
  const next = `${window.location.pathname}${window.location.search}`;
  return `/login?next=${encodeURIComponent(next)}`;
}

// datetime-local expects local "YYYY-MM-DDTHH:mm" values; the browser compares them as local time.
function localDateTimeNow(now = new Date()) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

export function QuoteRequestDialog({ open, profile, selectedServiceId, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [signInPath, setSignInPath] = useState("/login");
  const [serviceId, setServiceId] = useState(selectedServiceId);
  const [originLocation, setOriginLocation] = useState<RegionCommuneValue>(emptyLocation);
  const [destinationLocation, setDestinationLocation] = useState<RegionCommuneValue>(emptyLocation);
  const selectedService = profile.services.find((service) => service.serviceTypeId === serviceId);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
  }, [open]);

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
    const requestedAt = String(form.get("requestedAt") ?? "");
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
      origin: String(form.get("origin") ?? "").trim() || null,
      destination: String(form.get("destination") ?? "").trim() || null,
      requestedAt: requestedAt ? new Date(requestedAt).toISOString() : null,
      estimatedWeight: weight || null,
      estimatedVolume: volume || null,
      description: String(form.get("description") ?? "").trim() || null,
      cargoMeasurements: String(form.get("cargoMeasurements") ?? "").trim() || null,
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
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClose={onClose}
      ref={dialogRef}
    >
      <div className="quote-dialog-header">
        <div>
          <p className="eyebrow">SOLICITUD DE COTIZACIÓN</p>
          <h2 id="quote-dialog-title">Cuéntanos qué necesitas</h2>
        </div>
        <button aria-label="Cerrar solicitud" className="quote-dialog-close" onClick={onClose} type="button">×</button>
      </div>
      {success ? (
        <div className="quote-dialog-success" role="status">
          <h3>Solicitud enviada</h3>
          <p>El prestador podrá revisar los detalles y responderte. Aún no se ha confirmado una reserva ni realizado un pago.</p>
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
          <div className="quote-request-grid">
            <RegionCommuneSelect
              communeLabel="Comuna de origen"
              idPrefix="quote-origin"
              onChange={setOriginLocation}
              regionLabel="Región de origen"
              required
              value={originLocation}
            />
            <label className="marketplace-field" htmlFor="quote-origin-address"><span>Dirección de origen (opcional)</span><input autoComplete="street-address" id="quote-origin-address" maxLength={300} name="origin" /></label>
            <RegionCommuneSelect
              communeLabel="Comuna de destino"
              idPrefix="quote-destination"
              onChange={setDestinationLocation}
              regionLabel="Región de destino"
              required
              value={destinationLocation}
            />
            <label className="marketplace-field" htmlFor="quote-destination-address"><span>Dirección de destino (opcional)</span><input autoComplete="street-address" id="quote-destination-address" maxLength={300} name="destination" /></label>
            <label className="marketplace-field" htmlFor="quote-date"><span>Fecha deseada</span><input id="quote-date" min={localDateTimeNow()} name="requestedAt" type="datetime-local" /></label>
            <label className="marketplace-field" htmlFor="quote-weight"><span>Peso estimado (kg)</span><input id="quote-weight" min="0" name="estimatedWeight" step="0.01" type="number" /></label>
            <label className="marketplace-field" htmlFor="quote-volume"><span>Volumen estimado (m³)</span><input id="quote-volume" min="0" name="estimatedVolume" step="0.001" type="number" /></label>
            <label className="marketplace-field" htmlFor="quote-measurements"><span>Medidas de la carga</span><input id="quote-measurements" maxLength={2000} name="cargoMeasurements" /></label>
          </div>
          <label className="marketplace-field" htmlFor="quote-description"><span>Detalles de la solicitud</span><textarea id="quote-description" maxLength={4000} name="description" rows={4} /></label>
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
