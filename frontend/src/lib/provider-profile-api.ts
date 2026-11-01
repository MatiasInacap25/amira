import { authenticatedApiFetch } from "@/lib/auth/account-api";

// "name" is not a backend missing key; the form adds it for companies so the publish gate and checklist cover it.
export type ProviderProfileMissingItem = "description" | "commune" | "service_types" | "name";

export type ProviderProfile = {
  name: string;
  kind: string;
  description: string | null;
  commune_code: string | null;
  service_type_ids: string[];
  published: boolean;
  missing: ProviderProfileMissingItem[];
};

export type ProviderProfileInput = {
  description: string;
  commune_code: string | null;
  service_type_ids: string[];
  name?: string;
};

export class ProviderProfileError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`Provider profile request failed (${status})`);
    this.name = "ProviderProfileError";
    this.status = status;
    this.body = body;
  }
}

const PROFILE_PATH = "/api/provider/profile";
const GENERIC_REJECTION_MESSAGE = "No pudimos guardar tu perfil. Revisa los datos e inténtalo nuevamente.";
const MISSING_LABELS: Record<ProviderProfileMissingItem, string> = {
  description: "Escribe una descripción",
  commune: "Elige tu comuna",
  service_types: "Elige al menos un tipo de servicio",
  name: "Escribe el nombre de la empresa",
};

// Responses are parsed here so every caller gets the same typed error for non-2xx statuses.
async function parseProfileResponse(response: Response): Promise<ProviderProfile> {
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ProviderProfileError(response.status, body);
  return body as ProviderProfile;
}

const JSON_HEADERS = { Accept: "application/json", "Content-Type": "application/json" };

export async function requestProviderProfile(accessToken: string, signal?: AbortSignal) {
  const response = await authenticatedApiFetch(PROFILE_PATH, accessToken, process.env.NEXT_PUBLIC_API_URL, {
    headers: { Accept: "application/json" },
    signal,
  });
  return parseProfileResponse(response);
}

export async function saveProviderProfile(accessToken: string, input: ProviderProfileInput) {
  const response = await authenticatedApiFetch(PROFILE_PATH, accessToken, process.env.NEXT_PUBLIC_API_URL, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  });
  return parseProfileResponse(response);
}

export async function publishProviderProfile(accessToken: string) {
  const response = await authenticatedApiFetch(`${PROFILE_PATH}/publish`, accessToken, process.env.NEXT_PUBLIC_API_URL, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  return parseProfileResponse(response);
}

export async function unpublishProviderProfile(accessToken: string) {
  const response = await authenticatedApiFetch(`${PROFILE_PATH}/unpublish`, accessToken, process.env.NEXT_PUBLIC_API_URL, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  return parseProfileResponse(response);
}

// Maps the backend's missing-item keys to the Spanish checklist copy. Unknown keys are dropped, never rendered raw.
export function missingProfileLabels(missing: readonly string[]): string[] {
  return missing.flatMap((item) => (Object.hasOwn(MISSING_LABELS, item) ? [MISSING_LABELS[item as ProviderProfileMissingItem]] : []));
}

// Backend detail strings are English, so the UI maps the known ones to Spanish and never renders the raw text.
const KNOWN_REJECTION_MESSAGES: Record<string, string> = {
  "Only company profiles have a name.": "Solo las empresas pueden cambiar el nombre.",
  "Unknown commune.": "La comuna elegida no existe.",
  "Unknown service type.": "Uno de los tipos de servicio no existe.",
};

// Pydantic field errors name the field as the last `loc` segment. Only the known field and error type get Spanish copy.
const FIELD_REJECTION_MESSAGES: Array<{ field: string; type: string; message: string }> = [
  { field: "name", type: "value_error", message: "Escribe el nombre de la empresa." },
  { field: "description", type: "string_too_long", message: "La descripción no puede tener más de 2000 caracteres." },
];

function fieldRejectionMessage(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("loc" in error) || !("type" in error)) return null;
  const { loc, type } = error as { loc: unknown; type: unknown };
  if (!Array.isArray(loc) || typeof type !== "string") return null;
  const field = loc.at(-1);
  const known = FIELD_REJECTION_MESSAGES.find((entry) => entry.field === field && entry.type === type);
  return known ? known.message : null;
}

// Maps a 422 body from the provider profile routes to Spanish copy. Unknown shapes and strings get the generic message.
export function profileRejectionMessage(body: unknown): string {
  if (typeof body !== "object" || body === null || !("detail" in body)) return GENERIC_REJECTION_MESSAGE;
  const detail = (body as { detail: unknown }).detail;

  if (typeof detail === "string") {
    return Object.hasOwn(KNOWN_REJECTION_MESSAGES, detail) ? KNOWN_REJECTION_MESSAGES[detail] : GENERIC_REJECTION_MESSAGE;
  }

  if (Array.isArray(detail)) {
    for (const error of detail) {
      const message = fieldRejectionMessage(error);
      if (message) return message;
    }
    return GENERIC_REJECTION_MESSAGE;
  }

  if (typeof detail === "object" && detail !== null && "missing" in detail && Array.isArray(detail.missing)) {
    const labels = missingProfileLabels(detail.missing.filter((item): item is string => typeof item === "string"));
    if (labels.length > 0) return `Para publicar tu perfil falta: ${labels.join(", ")}.`;
  }

  return GENERIC_REJECTION_MESSAGE;
}
