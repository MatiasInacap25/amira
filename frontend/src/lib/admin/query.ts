export type AdminFilters = Record<string, string>;

export function readFilters(params: Pick<URLSearchParams, "get">, allowed: readonly string[]): AdminFilters {
  return Object.fromEntries(allowed.flatMap((key) => {
    const value = params.get(key)?.trim();
    return value ? [[key, value]] : [];
  }));
}

export function writeFilters(filters: AdminFilters) {
  return new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== ""));
}

export function updateFilter(filters: AdminFilters, key: string, value: string): AdminFilters {
  const next = { ...filters };
  if (key !== "offset") delete next.offset;
  if (value.trim()) next[key] = value.trim();
  else delete next[key];
  return next;
}
