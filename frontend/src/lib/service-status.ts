import { ServiceRequestError, type ServiceStatus } from "@/lib/marketplace-api";

// Pure display rules for "Mis servicios". Kept free of React so they can be reused by list and detail views.

export const SERVICE_STATUSES: readonly ServiceStatus[] = ["confirmed", "in_progress", "completed", "disputed"];

const STATUS_LABELS: Record<ServiceStatus, string> = {
  confirmed: "Confirmado",
  in_progress: "En curso",
  completed: "Finalizado",
  disputed: "En reclamo",
};

const NO_VALUE_LABEL = "No indicado";
const UNKNOWN_STATUS_LABEL = "Estado desconocido";
const clpFormatter = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });
const dateFormatter = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeZone: "America/Santiago" });
const dateTimeFormatter = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" });

export function serviceStatusLabel(status: string): string {
  return STATUS_LABELS[status as ServiceStatus] ?? UNKNOWN_STATUS_LABEL;
}

export function formatServiceAmount(amount: number | null): string {
  return amount === null ? NO_VALUE_LABEL : clpFormatter.format(amount);
}

export function formatServiceDate(value: string | null): string {
  return value ? dateFormatter.format(new Date(value)) : NO_VALUE_LABEL;
}

export function formatServiceDateTime(value: string | null): string {
  return value ? dateTimeFormatter.format(new Date(value)) : NO_VALUE_LABEL;
}

// Shows both endpoints when known; a missing side is labelled instead of silently dropped.
export function serviceRouteLabel(origin: string | null, destination: string | null): string {
  if (!origin && !destination) return NO_VALUE_LABEL;
  return `${origin ?? NO_VALUE_LABEL} → ${destination ?? NO_VALUE_LABEL}`;
}

// Mirrors the backend limits (SERVICE_EVIDENCE_MAX_BYTES default, and the JPEG/PNG/WebP magic-byte check).
export const DELIVERY_PHOTO_MAX_BYTES = 8 * 1024 * 1024;
export const DELIVERY_PHOTO_ACCEPT = "image/jpeg,image/png,image/webp";
const DELIVERY_PHOTO_TYPES: readonly string[] = ["image/jpeg", "image/png", "image/webp"];

export function deliveryPhotoRejection(photo: Pick<File, "type" | "size">): string | null {
  if (!DELIVERY_PHOTO_TYPES.includes(photo.type)) return "La foto debe ser JPEG, PNG o WebP.";
  if (photo.size > DELIVERY_PHOTO_MAX_BYTES) return "La foto supera el tamaño máximo de 8 MB.";
  return null;
}

export type ServiceAction = "load-options" | "assign" | "start" | "complete" | "delivery-photo";

const SESSION_EXPIRED_MESSAGE = "Tu sesión expiró. Inicia sesión nuevamente para continuar.";
const NOT_FOUND_MESSAGE = "Este servicio no existe o ya no está disponible en tu cuenta.";
const NO_CONNECTION_MESSAGE = "No pudimos conectarnos. Revisa tu conexión e inténtalo nuevamente.";
const GENERIC_MESSAGE = "No pudimos completar la acción. Inténtalo nuevamente.";
const OWNER_ONLY_MESSAGE = "Solo el dueño del perfil puede gestionar este servicio.";
const STORAGE_NOT_CONFIGURED_MESSAGE = "El almacenamiento de fotos no está configurado. Contacta al equipo de Amira.";

// Status-specific copy per action. Anything not listed falls back to the generic message.
const ACTION_STATUS_MESSAGES: Record<ServiceAction, Partial<Record<number, string>>> = {
  "load-options": { 403: OWNER_ONLY_MESSAGE },
  assign: {
    403: OWNER_ONLY_MESSAGE,
    409: "Solo se pueden asignar servicios confirmados.",
    422: "Revisa los conductores y vehículos seleccionados. Cada conductor y cada vehículo solo pueden usarse una vez.",
  },
  start: {
    403: "No tienes permiso para iniciar este servicio.",
    409: "Solo se pueden iniciar servicios confirmados con al menos un conductor y un vehículo asignados.",
  },
  complete: {
    403: "Solo un conductor asignado puede finalizar este servicio.",
    409: "Este servicio ya no está en curso. Actualiza la página.",
    413: "La foto de entrega supera el tamaño permitido.",
    415: "La foto debe ser JPEG, PNG o WebP.",
    422: "Selecciona una foto de entrega para finalizar el servicio.",
    502: "No pudimos guardar la foto de entrega. El servicio sigue en curso; inténtalo nuevamente.",
    503: STORAGE_NOT_CONFIGURED_MESSAGE,
  },
  "delivery-photo": {
    404: "Todavía no hay foto de entrega para este servicio.",
    502: "No pudimos obtener la foto de entrega. Inténtalo nuevamente.",
    503: STORAGE_NOT_CONFIGURED_MESSAGE,
  },
};

export function serviceActionErrorMessage(cause: unknown, action: ServiceAction): string {
  if (cause instanceof TypeError) return NO_CONNECTION_MESSAGE;
  if (!(cause instanceof ServiceRequestError)) return GENERIC_MESSAGE;
  const { status } = cause;
  if (status === 401) return SESSION_EXPIRED_MESSAGE;
  if (status === 404) return ACTION_STATUS_MESSAGES[action][status] ?? NOT_FOUND_MESSAGE;
  return ACTION_STATUS_MESSAGES[action][status] ?? GENERIC_MESSAGE;
}
