// Provider shared-trip helpers. Messages are Spanish; the backend stays the authority for every rule.
import { authenticatedApiFetch } from "@/lib/auth/account-api";

export const SHARED_TRIPS_PAGE_SIZE = 20;

export type SharedTripStatus = "open" | "closed";

export type ProviderSharedTrip = {
  tripId: string;
  status: SharedTripStatus;
  origin: string;
  destination: string;
  departureAt: string | null;
  joinedServices: number;
};

export type ProviderSharedTripPage = {
  items: ProviderSharedTrip[];
  total: number;
  limit: number;
  offset: number;
};

export type ProviderDriver = {
  driverId: string;
  name: string;
  // false while the driver's certificates are not verified; such a driver cannot be put on a trip.
  verified?: boolean;
};

export type SharedTripPublishInput = {
  vehicleId: string;
  driverId: string;
};

export function requestProviderSharedTrips(accessToken: string, offset: number, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(SHARED_TRIPS_PAGE_SIZE), offset: String(offset) });
  return authenticatedApiFetch(
    `/api/provider/shared-trips?${params.toString()}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, cache: "no-store", signal },
  );
}

export function requestProviderSharedTripClose(accessToken: string, tripId: string) {
  return authenticatedApiFetch(
    `/api/provider/shared-trips/${encodeURIComponent(tripId)}/close`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { method: "POST", headers: { Accept: "application/json" }, cache: "no-store" },
  );
}

export function requestProviderDrivers(accessToken: string, signal?: AbortSignal) {
  return authenticatedApiFetch(
    "/api/provider/drivers",
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, cache: "no-store", signal },
  );
}

export function requestSharedTripPublish(accessToken: string, serviceId: string, input: SharedTripPublishInput) {
  return authenticatedApiFetch(
    `/api/provider/services/${encodeURIComponent(serviceId)}/shared-trip`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      cache: "no-store",
      body: JSON.stringify(input),
    },
  );
}

// 409 means the service cannot become a trip (exclusive, already linked, no date or no route). Every 409 gets one message.
export function sharedTripPublishErrorMessage(status: number): string {
  if (status === 409) return "No se puede publicar este servicio como viaje compartido. Revisa que el cliente acepte compartir, que no tenga un viaje previo y que tenga fecha y ruta.";
  if (status === 404) return "El vehículo o el conductor ya no están disponibles. Actualiza la página e inténtalo nuevamente.";
  if (status === 403) return "Solo los proveedores pueden publicar viajes compartidos.";
  if (status === 422) return "Revisa el vehículo y el conductor elegidos.";
  return "No pudimos publicar el viaje. Inténtalo nuevamente.";
}

export function joinedServicesLabel(count: number): string {
  return count === 1 ? "1 servicio" : `${count} servicios`;
}
