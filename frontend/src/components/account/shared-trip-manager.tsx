"use client";

import { useCallback, useEffect, useState } from "react";
import { vehicleRequestError } from "@/lib/vehicle-api";
import {
  joinedServicesLabel,
  requestProviderSharedTripClose,
  requestProviderSharedTrips,
  type ProviderSharedTrip,
} from "@/lib/shared-trip-api";

const LOAD_ERROR = "No pudimos cargar tus viajes compartidos.";
const CLOSE_ERROR = "No pudimos cerrar el viaje. Inténtalo nuevamente.";

const dateFormatter = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" });

function formatDeparture(value: string | null) {
  if (!value) return "Fecha por confirmar";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Fecha por confirmar" : dateFormatter.format(date);
}

export function SharedTripManager({ token }: { token: string }) {
  const [trips, setTrips] = useState<ProviderSharedTrip[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busyTripId, setBusyTripId] = useState("");
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    const response = await requestProviderSharedTrips(token, 0);
    if (!response.ok) throw new Error(await vehicleRequestError(response));
    const body = await response.json() as { items: ProviderSharedTrip[] };
    setTrips(body.items);
    setLoaded(true);
  }, [token]);

  useEffect(() => {
    void Promise.resolve().then(() => reload()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : LOAD_ERROR));
  }, [reload]);

  async function close(tripId: string) {
    setError("");
    setBusyTripId(tripId);
    try {
      const response = await requestProviderSharedTripClose(token, tripId);
      if (!response.ok) {
        setError(CLOSE_ERROR);
        return;
      }
      setTrips((current) => current.map((trip) => (trip.tripId === tripId ? { ...trip, status: "closed" } : trip)));
    } catch {
      setError(CLOSE_ERROR);
    } finally {
      setBusyTripId("");
    }
  }

  if (error && !loaded) return <p role="alert" className="auth-error">{error}</p>;

  return (
    <section aria-labelledby="shared-trips-list-title" className="shared-trips-manager">
      <h2 id="shared-trips-list-title">Tus viajes publicados</h2>
      {error && <p role="alert" className="auth-error">{error}</p>}
      {loaded && trips.length === 0 && <p className="shared-trips-empty">Aún no has publicado viajes compartidos. Puedes publicarlos desde un servicio contratado.</p>}
      {trips.length > 0 && (
        <ul aria-label="Viajes compartidos publicados" className="shared-trips-list">
          {trips.map((trip) => {
            const open = trip.status === "open";
            return (
              <li className="shared-trip-item" key={trip.tripId}>
                <h3>{trip.origin} a {trip.destination}</h3>
                <p>Salida: {formatDeparture(trip.departureAt)}</p>
                <p>
                  <span className={open ? "shared-trip-status shared-trip-status-open" : "shared-trip-status shared-trip-status-closed"}>
                    {open ? "Abierto" : "Cerrado"}
                  </span>{" "}
                  · {joinedServicesLabel(trip.joinedServices)}
                </p>
                {open && (
                  <button
                    className="button button-secondary"
                    disabled={busyTripId === trip.tripId}
                    onClick={() => void close(trip.tripId)}
                    type="button"
                  >
                    Cerrar a nuevas solicitudes
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
