// Query keys for the header's provider link. Role and pending data belong to one account, so every
// per-user key carries the Supabase user id and is removed when the session changes accounts.
// Keep this module free of imports so node unit tests can load it directly.

export const PROVIDER_NAV_ROOT_KEY = ["provider-nav"] as const;
export const PROVIDER_NAV_USER_KEY = [...PROVIDER_NAV_ROOT_KEY, "user"] as const;

export function providerNavRoleKey(userId: string) {
  return [...PROVIDER_NAV_ROOT_KEY, "role", userId] as const;
}

export function providerNavPendingKey(userId: string) {
  return [...PROVIDER_NAV_ROOT_KEY, "pending", userId] as const;
}

// Prefixes removed when the account changes. The session user key is refetched, not removed.
export function providerNavStaleKeys() {
  return [
    [...PROVIDER_NAV_ROOT_KEY, "role"] as const,
    [...PROVIDER_NAV_ROOT_KEY, "pending"] as const,
  ];
}
