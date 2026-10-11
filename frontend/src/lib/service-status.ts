import type { ServiceStatus } from "@/lib/marketplace-api";

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
