// Pure rules for the chat composer, quotations and the payment return. Keep this module free of imports so node unit tests can load it.
// The contact filter is a heuristic pre-check; the backend enforces the same rule and remains the authority.

export const CHAT_MESSAGE_MAX_LENGTH = 2000;

// TanStack Query refetchInterval: no interval while the stream delivers events, the fallback poll otherwise.
export function chatRefetchInterval(streamConnected: boolean): number | false {
  return streamConnected ? false : CHAT_POLL_INTERVAL_MS;
}
// Polling only backs up the real-time stream: while it is disconnected, chat views refetch at this interval.
export const CHAT_POLL_INTERVAL_MS = 10_000;
export const QUOTATION_MIN_VALIDITY_HOURS = 1;
export const QUOTATION_MAX_VALIDITY_HOURS = 168;
export const QUOTATION_DEFAULT_VALIDITY_HOURS = 48;

export type ContactDetailKind = "phone" | "email" | "link" | "social";

const PHONE_PATTERN = /\+?\d(?:[\s.\-()]*\d){7,}/;
const EMAIL_PATTERN = /[^\s@]+@[^\s@]+\.[^\s@]+/;
const LINK_PATTERN = /https?:\/\/|\bwww\.|\b[a-z0-9-]+\.(?:com|cl|net|org|io|app|me|co)\b/i;
const SOCIAL_PATTERN = /@[\p{L}\d._]{2,}|\b(?:instagram|facebook|whatsapp|telegram|tiktok|snapchat|twitter)\b/iu;

// Order matters: an email address also contains a dot-separated domain, so it is checked before links.
export function findContactDetailKind(content: string): ContactDetailKind | null {
  if (PHONE_PATTERN.test(content)) return "phone";
  if (EMAIL_PATTERN.test(content)) return "email";
  if (LINK_PATTERN.test(content)) return "link";
  if (SOCIAL_PATTERN.test(content)) return "social";
  return null;
}

const CONTACT_MESSAGES: Record<ContactDetailKind, string> = {
  phone: "No compartas números de teléfono en el chat.",
  email: "No compartas correos electrónicos en el chat.",
  link: "No compartas enlaces en el chat.",
  social: "No compartas redes sociales en el chat.",
};

export function contactDetailMessage(kind: ContactDetailKind): string {
  return CONTACT_MESSAGES[kind];
}

// Returns the Spanish error for a draft, or null when it can be sent.
export function validateMessageDraft(raw: string): string | null {
  const content = raw.trim();
  if (!content) return "Escribe un mensaje antes de enviarlo.";
  if (content.length > CHAT_MESSAGE_MAX_LENGTH) return `El mensaje no puede superar los ${CHAT_MESSAGE_MAX_LENGTH} caracteres.`;
  const kind = findContactDetailKind(content);
  return kind ? contactDetailMessage(kind) : null;
}

export type QuotationDraft = {
  amount: number;
  serviceAt: string;
  description: string;
  validityHours: number;
};

export function validateQuotationDraft(draft: QuotationDraft): string | null {
  if (!Number.isFinite(draft.amount) || draft.amount <= 0) return "Ingresa un monto mayor a cero.";
  if (!Number.isInteger(draft.amount)) return "El monto debe ser un número entero de pesos.";
  if (!draft.serviceAt.trim()) return "Indica la fecha del servicio.";
  if (!draft.description.trim()) return "Describe el servicio que ofreces.";
  if (
    !Number.isInteger(draft.validityHours) ||
    draft.validityHours < QUOTATION_MIN_VALIDITY_HOURS ||
    draft.validityHours > QUOTATION_MAX_VALIDITY_HOURS
  ) {
    return `La vigencia debe estar entre ${QUOTATION_MIN_VALIDITY_HOURS} y ${QUOTATION_MAX_VALIDITY_HOURS} horas.`;
  }
  return null;
}

// Deterministic thousands separator, independent of the runtime's ICU data.
export function formatClp(amount: number): string {
  return `$${Math.trunc(amount).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".")}`;
}

export function quotationStatusLabel(status: string): string {
  if (status === "pending") return "Pendiente de pago";
  if (status === "paid") return "Pagada";
  if (status === "rejected") return "Rechazada";
  if (status === "expired") return "Vencida";
  if (status === "superseded") return "Reemplazada";
  return "Estado desconocido";
}

type QuotationWindow = { status: string; expiresAt: string };

export function canPayQuotation(quotation: QuotationWindow, now: Date): boolean {
  return quotation.status === "pending" && new Date(quotation.expiresAt).getTime() > now.getTime();
}

export function canRejectQuotation(quotation: QuotationWindow, now: Date): boolean {
  return canPayQuotation(quotation, now);
}

// Payment statuses are not enumerated by the contract, so only an explicit "rejected" is a failure.
// A paid quotation is the single source of truth for success.
export function paymentResultState(input: { quotationStatus: string; status?: string }): "success" | "failure" | "pending" {
  if (input.quotationStatus === "paid") return "success";
  if (input.status === "rejected") return "failure";
  return "pending";
}
