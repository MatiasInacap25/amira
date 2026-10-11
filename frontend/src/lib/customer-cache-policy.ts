// Clears per-user customer data on sign-out or when another account becomes the session user.
// Token refreshes and re-sign-ins of the same account keep the cache.
export function shouldClearCustomerCache(
  event: string,
  cachedUserId: string | undefined,
  nextUserId: string | undefined,
): boolean {
  if (event === "SIGNED_OUT") return true;
  return cachedUserId !== undefined && nextUserId !== cachedUserId;
}
