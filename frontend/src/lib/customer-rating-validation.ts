export const RATING_COMMENT_MAX_LENGTH = 1000;

export type RatingDraft = {
  rating: number | null;
  comment: string;
};

export type RatingDraftErrors = {
  rating?: string;
  comment?: string;
};

export function normalizeRatingComment(comment: string): string | null {
  const trimmed = comment.trim();
  return trimmed ? trimmed : null;
}

// Counts code points, not UTF-16 units, so the limit matches the API's character count.
export function validateRatingDraft(draft: RatingDraft): RatingDraftErrors {
  const errors: RatingDraftErrors = {};
  if (draft.rating === null || !Number.isInteger(draft.rating) || draft.rating < 1 || draft.rating > 5) {
    errors.rating = "Elige una calificación de 1 a 5 estrellas.";
  }
  if ([...draft.comment.trim()].length > RATING_COMMENT_MAX_LENGTH) {
    errors.comment = "El comentario no puede superar los 1000 caracteres.";
  }
  return errors;
}
