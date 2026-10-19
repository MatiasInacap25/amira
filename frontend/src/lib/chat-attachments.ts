// Pure rules for chat photo attachments. Keep this module free of imports so node unit tests can load it.
// The backend checks type, size and storage again and remains the authority.

export const CHAT_ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024;
export const CHAT_ATTACHMENT_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
export const CHAT_ATTACHMENT_ACCEPT = CHAT_ATTACHMENT_TYPES.join(",");

const TYPE_MESSAGE = "Solo puedes adjuntar fotos en formato JPEG, PNG o WebP.";
const SIZE_MESSAGE = "La foto no puede superar los 5 MB.";
const GENERIC_MESSAGE = "No pudimos enviar la foto. Revisa tu conexión e inténtalo nuevamente.";

// Returns the Spanish error for a photo the user picked, or null when it can be uploaded.
export function validateChatAttachment(file: { type: string; size: number }): string | null {
  if (!(CHAT_ATTACHMENT_TYPES as readonly string[]).includes(file.type)) return TYPE_MESSAGE;
  if (file.size > CHAT_ATTACHMENT_MAX_BYTES) return SIZE_MESSAGE;
  return null;
}

// Maps a failed photo upload to a Spanish message. A 422 carries the backend's contact-filter detail, shown verbatim.
export function chatAttachmentErrorMessage(status: number, detailMessage: string | null): string {
  if (status === 404) return "Esta conversación ya no está disponible.";
  if (status === 413) return SIZE_MESSAGE;
  if (status === 415) return TYPE_MESSAGE;
  if (status === 422 && detailMessage) return detailMessage;
  if (status === 502) return "No pudimos subir la foto. Inténtalo nuevamente.";
  if (status === 503) return "El envío de fotos no está disponible en este momento.";
  return GENERIC_MESSAGE;
}
