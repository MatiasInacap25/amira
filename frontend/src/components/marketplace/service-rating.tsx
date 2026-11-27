"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { createCustomerServiceRating, type CustomerServiceRating } from "@/lib/marketplace-api";
import { mapRatingRejection } from "@/lib/customer-rating-errors";
import { normalizeRatingComment, RATING_COMMENT_MAX_LENGTH, validateRatingDraft, type RatingDraftErrors } from "@/lib/customer-rating-validation";
import { sendWithTokenRetry } from "@/lib/customer-request-retry";
import { CustomerSessionError, readAccessToken, refreshAccessToken } from "@/lib/customer-session";
import { CUSTOMER_SERVICES_KEY, SERVICE_DETAIL_KEY } from "@/lib/service-query-keys";

const SIGN_IN_HREF = "/login?next=%2Fcuenta%2Fservicios";

/**
 * The customer's rating of a completed service. Shows the form until the service is rated, then the stored rating read-only.
 * The "already rated" notice lives here, not in the form, so it survives the detail refetch that unmounts the form.
 */
export function ServiceRating({ rating, serviceId }: { rating: CustomerServiceRating | null; serviceId: string }) {
  const [alreadyRated, setAlreadyRated] = useState(false);

  return (
    <div className="customer-service-rating-block">
      {rating ? <StoredRating rating={rating} /> : <RatingForm onAlreadyRated={() => setAlreadyRated(true)} serviceId={serviceId} />}
      {alreadyRated && (
        <div className="customer-submit-error" role="alert">
          <p>Este servicio ya fue valorado.</p>
        </div>
      )}
    </div>
  );
}

function StoredRating({ rating }: { rating: CustomerServiceRating }) {
  return (
    <div className="customer-service-rating">
      <h3>Tu valoración</h3>
      <StarDisplay value={rating.rating} />
      {rating.comment && <p>{rating.comment}</p>}
      <time dateTime={rating.createdAt}>Valorado el {formatDate(rating.createdAt)}</time>
    </div>
  );
}

function StarDisplay({ value }: { value: number }) {
  return (
    <p aria-label={`Valoración: ${value} de 5 estrellas`} className="customer-star-display" role="img">
      {[1, 2, 3, 4, 5].map((star) => (
        <Star aria-hidden="true" fill={star <= value ? "currentColor" : "none"} key={star} size={16} />
      ))}
    </p>
  );
}

function RatingForm({ onAlreadyRated, serviceId }: { onAlreadyRated: () => void; serviceId: string }) {
  const queryClient = useQueryClient();
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [fieldErrors, setFieldErrors] = useState<RatingDraftErrors>({});
  const [submitError, setSubmitError] = useState("");
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const [busy, setBusy] = useState(false);

  function refreshRatingViews() {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: SERVICE_DETAIL_KEY }),
      queryClient.invalidateQueries({ queryKey: CUSTOMER_SERVICES_KEY }),
    ]);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const errors = validateRatingDraft({ rating, comment });
    setFieldErrors(errors);
    setSubmitError("");
    setNeedsSignIn(false);
    if (rating === null || Object.keys(errors).length > 0) return;

    setBusy(true);
    try {
      const response = await sendWithTokenRetry(
        (accessToken) => createCustomerServiceRating(serviceId, { rating, comment: normalizeRatingComment(comment) }, accessToken),
        readAccessToken,
        refreshAccessToken,
      );
      if (response.ok) {
        await refreshRatingViews();
        return;
      }
      if (response.status === 401) {
        setNeedsSignIn(true);
        setSubmitError("Tu sesión expiró. Inicia sesión nuevamente para continuar.");
      }
      else if (response.status === 404) setSubmitError("No encontramos este servicio en tu cuenta. Actualiza la página e inténtalo nuevamente.");
      else if (response.status === 409) {
        onAlreadyRated();
        await refreshRatingViews();
      } else if (response.status === 422) {
        const rejection = mapRatingRejection(await response.json().catch(() => null));
        setFieldErrors(rejection.fieldErrors);
        setSubmitError(rejection.submitError);
      }
      else setSubmitError("No pudimos guardar la valoración. Inténtalo nuevamente.");
    } catch (cause) {
      if (cause instanceof CustomerSessionError) {
        setNeedsSignIn(true);
        setSubmitError("Tu sesión expiró. Inicia sesión nuevamente para continuar.");
      } else {
        setSubmitError("No pudimos guardar la valoración. Revisa tu conexión e inténtalo nuevamente.");
      }
    } finally {
      setBusy(false);
    }
  }

  const ratingErrorId = `rating-${serviceId}-error`;
  const commentErrorId = `rating-${serviceId}-comment-error`;

  return (
    <form className="customer-rating-form" noValidate onSubmit={submit}>
      <fieldset aria-describedby={fieldErrors.rating ? ratingErrorId : undefined} className="customer-rating-fieldset">
        <legend>Calificación</legend>
        <div className="customer-star-picker">
          {[1, 2, 3, 4, 5].map((star) => (
            <label className="customer-star-option" key={star}>
              <input checked={rating === star} className="customer-star-input" name={`rating-${serviceId}`} onChange={() => { setRating(star); setFieldErrors({}); }} type="radio" value={star} />
              <Star aria-hidden="true" className={star <= (rating ?? 0) ? "customer-star-filled" : undefined} fill={star <= (rating ?? 0) ? "currentColor" : "none"} size={22} />
              <span className="customer-star-label">{star} de 5</span>
            </label>
          ))}
        </div>
        {fieldErrors.rating && <p className="customer-field-error" id={ratingErrorId}>{fieldErrors.rating}</p>}
      </fieldset>
      <div className="customer-rating-comment">
        <label htmlFor={`rating-${serviceId}-comment`}>Comentario (opcional)</label>
        <textarea
          aria-describedby={fieldErrors.comment ? commentErrorId : undefined}
          aria-invalid={fieldErrors.comment ? true : undefined}
          id={`rating-${serviceId}-comment`}
          maxLength={RATING_COMMENT_MAX_LENGTH}
          onChange={(event) => { setComment(event.target.value); setFieldErrors((current) => ({ ...current, comment: undefined })); }}
          rows={3}
          value={comment}
        />
        {fieldErrors.comment && <p className="customer-field-error" id={commentErrorId}>{fieldErrors.comment}</p>}
      </div>
      {submitError && (
        <div className="customer-submit-error" role="alert">
          <p>{submitError}</p>
          {needsSignIn && <Link href={SIGN_IN_HREF}>Iniciar sesión</Link>}
        </div>
      )}
      <button className="button button-primary customer-rating-submit" disabled={busy} type="submit">{busy ? "Guardando…" : "Enviar valoración"}</button>
    </form>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("es-CL", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}
