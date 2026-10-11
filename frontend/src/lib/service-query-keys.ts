import type { QueryClient } from "@tanstack/react-query";

// Shared TanStack Query keys for "Mis servicios". Every view that reads or invalidates these lists imports them from here.
export const ACCOUNT_ROLE_KEY = ["services-account-role"];
export const SERVICE_DETAIL_KEY = ["service-detail"];
export const PROVIDER_SERVICES_KEY = ["provider-services"];
// Prefix of the customer list key; the list adds the user id as its last segment.
export const CUSTOMER_SERVICES_KEY = ["customer-services"];

// Drops every "Mis servicios" query that belongs to the previous account. The role decides which list is visible, so it goes too.
export function clearAccountScopedQueries(queryClient: QueryClient): void {
  for (const key of [ACCOUNT_ROLE_KEY, PROVIDER_SERVICES_KEY, SERVICE_DETAIL_KEY, CUSTOMER_SERVICES_KEY]) {
    queryClient.removeQueries({ queryKey: key });
  }
}
