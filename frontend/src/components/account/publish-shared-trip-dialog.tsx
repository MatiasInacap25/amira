"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { sendWithTokenRetry } from "@/lib/customer-request-retry";
import { readAccessToken, refreshAccessToken } from "@/lib/customer-session";
import { SERVICE_DETAIL_KEY } from "@/lib/service-query-keys";
import { authenticatedApiFetch } from "@/lib/auth/account-api";
import {
  requestProviderDrivers,
  requestSharedTripPublish,
  sharedTripPublishErrorMessage,
  type ProviderDriver,
} from "@/lib/shared-trip-api";
import { vehicleRequestError, type ProviderVehicle } from "@/lib/vehicle-api";

type Props = {
  open: boolean;
  serviceId: string;
  onClose: () => void;
};

const VEHICLES_HREF = "/cuenta/vehiculos";

// Loads the provider's own vehicles and drivers only when the dialog is open.
function useProviderTripOptions(enabled: boolean) {
  const vehicles = useQuery({
    queryKey: ["provider-vehicles-for-trip"],
    queryFn: async () => {
      const response = await sendWithTokenRetry(
        (accessToken) => authenticatedApiFetch("/api/provider/vehicles", accessToken, process.env.NEXT_PUBLIC_API_URL, { cache: "no-store" }),
        readAccessToken,
        refreshAccessToken,
      );
      if (!response.ok) throw new Error(await vehicleRequestError(response));
      const body = await response.json() as { items: ProviderVehicle[] };
      return body.items;
    },
    enabled,
    retry: false,
  });
  const drivers = useQuery({
    queryKey: ["provider-drivers-for-trip"],
    queryFn: async () => {
      const response = await sendWithTokenRetry((accessToken) => requestProviderDrivers(accessToken), readAccessToken, refreshAccessToken);
      if (!response.ok) throw new Error("No pudimos cargar tus conductores.");
      const body = await response.json() as { items: ProviderDriver[] };
      return body.items;
    },
    enabled,
    retry: false,
  });
  return { vehicles, drivers };
}

// Mounted only while open, so every opening starts with a fresh form and fresh option lists.
export function PublishSharedTripDialog({ open, serviceId, onClose }: Props) {
  if (!open) return null;
  return <PublishSharedTripForm onClose={onClose} serviceId={serviceId} />;
}

function PublishSharedTripForm({ serviceId, onClose }: Omit<Props, "open">) {
  const queryClient = useQueryClient();
  const { vehicles, drivers } = useProviderTripOptions(true);
  const [vehicleId, setVehicleId] = useState("");
  const [driverId, setDriverId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [published, setPublished] = useState(false);

  const vehicleItems = vehicles.data ?? [];
  const driverItems = drivers.data ?? [];
  const optionsLoading = vehicles.isPending || drivers.isPending;
  const noVehicles = vehicles.isSuccess && vehicleItems.length === 0;
  const canSubmit = !busy && !optionsLoading && !noVehicles && Boolean(vehicleId) && Boolean(driverId);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError("");
    try {
      const response = await sendWithTokenRetry(
        (accessToken) => requestSharedTripPublish(accessToken, serviceId, { vehicleId, driverId }),
        readAccessToken,
        refreshAccessToken,
      );
      if (!response.ok) {
        setError(sharedTripPublishErrorMessage(response.status));
        return;
      }
      setPublished(true);
      await queryClient.invalidateQueries({ queryKey: SERVICE_DETAIL_KEY });
    } catch {
      setError("No pudimos publicar el viaje. Revisa tu conexión e inténtalo nuevamente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shared-trip-dialog-backdrop">
      <div aria-labelledby="publish-trip-title" aria-modal="true" className="shared-trip-dialog" role="dialog">
        <h2 id="publish-trip-title">Publicar viaje compartido</h2>
        <p className="shared-trip-dialog-note">
          Se publicará la ruta y la fecha de este servicio. Otros clientes podrán sumarse al viaje y cada solicitud la decides tú.
        </p>

        {published ? (
          <div className="shared-trip-dialog-result">
            <p role="status">Viaje publicado.</p>
            <button className="button button-primary" onClick={onClose} type="button">Listo</button>
          </div>
        ) : (
          <form className="shared-trip-dialog-form" onSubmit={submit}>
            {vehicles.isError && <p className="marketplace-field-error" role="alert">{vehicles.error instanceof Error ? vehicles.error.message : "No pudimos cargar tus vehículos."}</p>}
            {noVehicles && (
              <p className="shared-trip-dialog-empty">
                Aún no tienes vehículos registrados. <Link href={VEHICLES_HREF}>Registrar un vehículo</Link> para poder publicar el viaje.
              </p>
            )}
            <label className="marketplace-field" htmlFor="publish-trip-vehicle">
              <span>Vehículo</span>
              <select disabled={optionsLoading || noVehicles} id="publish-trip-vehicle" onChange={(event) => setVehicleId(event.target.value)} required value={vehicleId}>
                <option value="">Elige un vehículo</option>
                {vehicleItems.map((vehicle) => (
                  <option key={vehicle.vehicleId} value={vehicle.vehicleId}>{vehicle.plate} · {vehicle.brand} {vehicle.model}</option>
                ))}
              </select>
            </label>
            <label className="marketplace-field" htmlFor="publish-trip-driver">
              <span>Conductor</span>
              <select disabled={optionsLoading || noVehicles} id="publish-trip-driver" onChange={(event) => setDriverId(event.target.value)} required value={driverId}>
                <option value="">Elige un conductor</option>
                {driverItems.map((driver) => (
                  // An unverified driver stays visible but cannot be chosen: the API refuses to put them on a trip.
                  <option disabled={driver.verified === false} key={driver.driverId} value={driver.driverId}>
                    {driver.verified === false ? `${driver.name} (sin verificar)` : driver.name}
                  </option>
                ))}
              </select>
            </label>
            {error && <p className="marketplace-field-error" role="alert">{error}</p>}
            <div className="shared-trip-dialog-actions">
              <button className="button button-secondary" disabled={busy} onClick={onClose} type="button">Cancelar</button>
              <button className="button button-primary" disabled={!canSubmit} type="submit">{busy ? "Publicando…" : "Publicar viaje"}</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
