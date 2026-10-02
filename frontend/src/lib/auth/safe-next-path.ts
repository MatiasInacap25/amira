const DEFAULT_NEXT_PATH = "/servicios";

/** Accept only same-origin absolute paths; reject protocol-relative and ambiguous paths. */
export function safeNextPath(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return DEFAULT_NEXT_PATH;
  }

  try {
    const parsed = new URL(value, "https://amira.invalid");
    if (parsed.origin !== "https://amira.invalid") return DEFAULT_NEXT_PATH;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return DEFAULT_NEXT_PATH;
  }
}
