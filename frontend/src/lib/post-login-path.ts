const DEFAULT_NEXT_PATH = "/servicios";
const PROVIDER_DASHBOARD_PATH = "/panel";
const DASHBOARD_ROLES = new Set(["independent_driver", "company_owner", "company_driver"]);
const ORIGIN = "https://amira.invalid";

/** Same-origin absolute paths only; returns null for anything unsafe or ambiguous. */
function parseSafeNextPath(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return null;
  try {
    const parsed = new URL(value, ORIGIN);
    if (parsed.origin !== ORIGIN) return null;
    // Normalization can collapse dot segments into a protocol-relative path, e.g. "/..//evil.example".
    if (parsed.pathname.startsWith("//") || parsed.pathname.includes("\\")) return null;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return null;
  }
}

/** Single source of the same-origin "safe next" rule. Accept only same-origin absolute paths; reject protocol-relative and ambiguous paths. */
export function safeNextPath(value: string | null | undefined): string {
  return parseSafeNextPath(value) ?? DEFAULT_NEXT_PATH;
}

export function postLoginPath({
  role,
  explicitNext,
  fallback,
}: {
  role: string | null | undefined;
  explicitNext: string | null | undefined;
  fallback: string;
}): string {
  const next = parseSafeNextPath(explicitNext);
  if (next) return next;
  if (role && DASHBOARD_ROLES.has(role)) return PROVIDER_DASHBOARD_PATH;
  return fallback;
}
