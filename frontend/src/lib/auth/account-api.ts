export class ApiConfigurationError extends Error {
  constructor() {
    super("La API todavía no está configurada correctamente. Contacta al equipo de Amira.");
    this.name = "ApiConfigurationError";
  }
}

export function resolveApiBaseUrl(value: string | undefined) {
  if (!value?.trim()) throw new ApiConfigurationError();
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new ApiConfigurationError();
  }
  if (!["http:", "https:"].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) {
    throw new ApiConfigurationError();
  }
  return url.toString().replace(/\/$/, "");
}

export async function accountApiFetch(
  path: "/api/account/me" | "/api/account/provision" | "/api/service-requests",
  accessToken: string,
  apiUrl: string | undefined,
  options: RequestInit = {},
  fetcher: typeof fetch = fetch,
) {
  return authenticatedApiFetch(path, accessToken, apiUrl, options, fetcher);
}

export async function authenticatedApiFetch(
  path: string,
  accessToken: string,
  apiUrl: string | undefined,
  options: RequestInit = {},
  fetcher: typeof fetch = fetch,
) {
  const baseUrl = resolveApiBaseUrl(apiUrl);
  return fetcher(`${baseUrl}${path}`, {
    ...options,
    headers: { ...options.headers, Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
}
