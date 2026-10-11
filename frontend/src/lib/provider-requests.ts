// Pure rules for the provider request inbox. Keep this module free of imports so node unit tests can load it.

export const PROVIDER_REQUEST_STATUSES = ["pending", "accepted", "rejected"] as const;
export type ProviderRequestStatus = (typeof PROVIDER_REQUEST_STATUSES)[number];

const PROVIDER_ROLES = ["company_owner", "independent_driver"] as const;
const NO_LOCATION_LABEL = "Ubicación no indicada";

type PageLike = {
  offset: number;
  items: readonly unknown[];
  total: number;
};

// Stops on an empty page so a total/items mismatch cannot cause endless requests.
export function nextProviderRequestOffset(page: PageLike): number | undefined {
  if (page.items.length === 0) return undefined;
  const nextOffset = page.offset + page.items.length;
  return nextOffset < page.total ? nextOffset : undefined;
}

// The "all" view sends no status parameter so the API returns every status.
export function buildProviderRequestsQuery(options: { status?: ProviderRequestStatus; limit: number; offset: number }): string {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  params.set("limit", String(options.limit));
  params.set("offset", String(options.offset));
  return params.toString();
}

export function parseProviderRequestStatus(value: string | null | undefined): ProviderRequestStatus | undefined {
  return (PROVIDER_REQUEST_STATUSES as readonly string[]).includes(value ?? "") ? (value as ProviderRequestStatus) : undefined;
}

// Prefers the catalog commune and region; falls back to the free-text address written by the customer.
export function formatRouteEndpoint(communeName: string | null, regionName: string | null, freeText: string | null): string {
  const commune = communeName?.trim() ?? "";
  if (commune) {
    const region = regionName?.trim() ?? "";
    return region ? `${commune}, ${region}` : commune;
  }
  const text = freeText?.trim() ?? "";
  return text || NO_LOCATION_LABEL;
}

// Before acceptance the API returns only the first name; the last name arrives with acceptance.
export function customerDisplayName(item: { customerFirstName: string; customerLastName: string | null }): string {
  const parts = [item.customerFirstName, item.customerLastName ?? ""].map((part) => part.trim()).filter(Boolean);
  return parts.join(" ");
}

export function isProviderRole(role: string | null | undefined): boolean {
  return (PROVIDER_ROLES as readonly string[]).includes(role ?? "");
}

export function pendingBadgeLabel(count: number): string | undefined {
  if (count <= 0) return undefined;
  return count > 99 ? "99+" : String(count);
}
