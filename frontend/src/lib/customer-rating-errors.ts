export type RatingFieldErrors = {
  rating?: string;
  comment?: string;
};

export type RatingRejection = {
  fieldErrors: RatingFieldErrors;
  submitError: string;
};

const COMPLETED_SERVICE_MESSAGE = "Solo puedes valorar servicios completados.";
const GENERIC_MESSAGE = "No pudimos guardar la valoración. Revisa los datos e inténtalo nuevamente.";
// Pydantic messages are English, so inline copy is Spanish and keyed by field instead.
const FIELD_MESSAGES: Record<"rating" | "comment", string> = {
  rating: "Elige una calificación de 1 a 5 estrellas.",
  comment: "El comentario no es válido. Acórtalo e inténtalo nuevamente.",
};

type ErrorDetail = { loc: unknown[]; type?: unknown };

function readDetails(body: unknown): ErrorDetail[] {
  if (typeof body !== "object" || body === null || !("detail" in body)) return [];
  const detail = (body as { detail: unknown }).detail;
  if (!Array.isArray(detail)) return [];
  return detail.filter(
    (entry): entry is ErrorDetail => typeof entry === "object" && entry !== null && Array.isArray((entry as { loc?: unknown }).loc),
  );
}

// Maps a rejected 422 body from the rating route to inline field errors or a submit-level message.
export function mapRatingRejection(body: unknown): RatingRejection {
  const details = readDetails(body);
  if (details.some((entry) => entry.type === "service_not_completed")) {
    return { fieldErrors: {}, submitError: COMPLETED_SERVICE_MESSAGE };
  }

  const fieldErrors: RatingFieldErrors = {};
  for (const entry of details) {
    const field = entry.loc[entry.loc.length - 1];
    if (field === "rating" || field === "comment") fieldErrors[field] = FIELD_MESSAGES[field];
  }
  const hasFieldErrors = Object.keys(fieldErrors).length > 0;
  return { fieldErrors, submitError: hasFieldErrors ? "" : GENERIC_MESSAGE };
}
