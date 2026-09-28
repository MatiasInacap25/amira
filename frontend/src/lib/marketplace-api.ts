export type ServiceProfile = {
  profileId: string;
  providerName: string;
  category: string;
  description?: string | null;
  location?: string | null;
  logoUrl?: string | null;
};

export type SharedRouteStop = {
  stopNumber: number;
  estimatedAt?: string | null;
};

export type SharedRoute = {
  tripId: string;
  providerName: string;
  origin: string;
  destination: string;
  departureAt?: string | null;
  stops?: SharedRouteStop[] | null;
};

export type PagedResponse<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type ServiceFilters = {
  q: string;
  category: string;
  location: string;
  offset: number;
};

export type SharedRouteFilters = {
  origin: string;
  destination: string;
  departureFrom: string;
  departureTo: string;
  offset: number;
};

const PAGE_SIZE = 20;
const apiBaseUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

function addNonEmpty(params: URLSearchParams, key: string, value: string) {
  const normalized = value.trim();
  if (normalized) params.set(key, normalized);
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { headers: { Accept: "application/json" }, signal });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export function getServices(filters: ServiceFilters, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(filters.offset) });
  addNonEmpty(params, "q", filters.q);
  addNonEmpty(params, "category", filters.category);
  addNonEmpty(params, "location", filters.location);
  return getJson<PagedResponse<ServiceProfile>>(`/api/services?${params.toString()}`, signal);
}

export function getSharedRoutes(filters: SharedRouteFilters, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(filters.offset) });
  addNonEmpty(params, "origin", filters.origin);
  addNonEmpty(params, "destination", filters.destination);
  addNonEmpty(params, "departureFrom", dateBoundary(filters.departureFrom, "00:00:00"));
  addNonEmpty(params, "departureTo", dateBoundary(filters.departureTo, "23:59:59.999"));
  return getJson<PagedResponse<SharedRoute>>(`/api/shared-routes?${params.toString()}`, signal);
}

function dateBoundary(date: string, time: string) {
  if (!date) return "";
  const reference = new Date(`${date}T12:00:00Z`);
  const offsetPart = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Santiago",
    timeZoneName: "longOffset",
  }).formatToParts(reference).find((part) => part.type === "timeZoneName")?.value;
  const offset = offsetPart === "GMT" ? "+00:00" : offsetPart?.replace(/^GMT/, "") ?? "";
  return `${date}T${time}${offset}`;
}
