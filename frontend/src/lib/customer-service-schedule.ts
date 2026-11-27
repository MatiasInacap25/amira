// Schedule and route labels for "Mis servicios" rows. Dates are shown in Chile's time zone, not the browser's.
const SANTIAGO_TIME_ZONE = "America/Santiago";
const UNCONFIRMED_DATE_LABEL = "Fecha por confirmar";
const NO_ADDRESS_LABEL = "Sin dirección";

const dateTimeParts = new Intl.DateTimeFormat("es-CL", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: SANTIAGO_TIME_ZONE,
});

/** `dd-mm-aaaa · HH:mm` in America/Santiago, or the placeholder when the request has no date. */
export function formatServiceSchedule(scheduledAt: string | null): string {
  if (!scheduledAt) return UNCONFIRMED_DATE_LABEL;
  const parts = Object.fromEntries(dateTimeParts.formatToParts(new Date(scheduledAt)).map((part) => [part.type, part.value]));
  return `${parts.day}-${parts.month}-${parts.year} · ${parts.hour}:${parts.minute}`;
}

/** `origen → destino`; each missing or blank side reads as "Sin dirección". */
export function formatServiceRoute(origin: string | null, destination: string | null): string {
  return `${origin?.trim() || NO_ADDRESS_LABEL} → ${destination?.trim() || NO_ADDRESS_LABEL}`;
}
