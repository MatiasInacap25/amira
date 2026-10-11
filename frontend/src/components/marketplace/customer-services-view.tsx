"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import {
  createCustomerServiceRating,
  getCustomerServices,
  type CustomerService,
} from "@/lib/marketplace-api";
import { normalizeRatingComment, RATING_COMMENT_MAX_LENGTH, validateRatingDraft, type RatingDraftErrors } from "@/lib/customer-rating-validation";
import { createClient } from "@/lib/supabase/client";

const SERVICES_QUERY_KEY = ["customer-services"];

class CustomerSessionError extends Error {}

async function readAccessToken(): Promise<string> {
  const client = createClient();
  const { data: userData, error: userError } = await client.auth.getUser();
  if (userError || !userData.user?.email_confirmed_at) throw new CustomerSessionError();
  const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
  if (assuranceError || assurance.currentLevel !== "aal2") throw new CustomerSessionError();
  const { data: sessionData, error: sessionError } = await client.auth.getSession();
  if (sessionError || !sessionData.session?.access_token) throw new CustomerSessionError();
  return sessionData.session.access_token;
}

export function CustomerServicesView() {
  const router = useRouter();
  const sessionQuery = useQuery({
    queryKey: ["customer-access-token"],
    queryFn: readAccessToken,
    retry: false,
    staleTime: 60_000,
  });
  const token = sessionQuery.data ?? "";
  const servicesQuery = useInfiniteQuery({
    queryKey: SERVICES_QUERY_KEY,
    queryFn: ({ pageParam, signal }) => getCustomerServices(token, pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset = lastPage.offset + lastPage.items.length;
      return nextOffset < lastPage.total ? nextOffset : undefined;
    },
    enabled: Boolean(token),
    retry: false,
  });

  const sessionExpired = sessionQuery.error instanceof CustomerSessionError;
  useEffect(() => {
    if (sessionExpired) router.replace("/login?next=%2Fcuenta%2Fservicios");
  }, [router, sessionExpired]);

  const services = servicesQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const sessionFailed = sessionQuery.isError && !(sessionQuery.error instanceof CustomerSessionError);

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main customer-services-page" id="contenido">
        <div className="customer-services-wrap">
          <h1>Mis servicios</h1>
          <p className="customer-services-intro">Valora los servicios completados. Tu valoración aparece en el perfil del prestador.</p>

          {(sessionQuery.isPending || (token && servicesQuery.isPending)) && (
            <div aria-busy="true" className="marketplace-state" role="status"><span aria-hidden="true" className="state-spinner" />Cargando tus servicios…</div>
          )}
          {sessionFailed && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos verificar tu sesión</h2>
              <p>Inicia sesión de nuevo para ver tus servicios.</p>
              <Link className="button button-secondary" href="/login?next=%2Fcuenta%2Fservicios">Iniciar sesión</Link>
            </div>
          )}
          {servicesQuery.isError && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos cargar tus servicios</h2>
              <p>Inténtalo nuevamente en unos minutos.</p>
              <button className="button button-secondary" onClick={() => void servicesQuery.refetch()} type="button">Reintentar</button>
            </div>
          )}
          {servicesQuery.isSuccess && services.length === 0 && (
            <div className="marketplace-state marketplace-empty" role="status">
              <h2>Aún no tienes servicios</h2>
              <p>Cuando un prestador confirme un servicio contigo, podrás valorarlo desde aquí.</p>
              <Link className="button button-secondary" href="/servicios">Buscar servicios</Link>
            </div>
          )}

          {services.length > 0 && (
            <ul className="customer-service-list">
              {services.map((service) => (
                <li className="customer-service-row" key={service.serviceId}>
                  <ServiceRatingRow service={service} token={token} />
                </li>
              ))}
            </ul>
          )}

          {servicesQuery.hasNextPage && (
            <button className="button button-secondary customer-services-more" disabled={servicesQuery.isFetchingNextPage} onClick={() => void servicesQuery.fetchNextPage()} type="button">
              {servicesQuery.isFetchingNextPage ? "Cargando…" : "Cargar más servicios"}
            </button>
          )}
        </div>
      </main>
      <MarketplaceFooter />
    </>
  );
}

function ServiceRatingRow({ service, token }: { service: CustomerService; token: string }) {
  return (
    <article aria-labelledby={`service-${service.serviceId}-title`} className="customer-service-card">
      <header>
        <h2 id={`service-${service.serviceId}-title`}>{service.serviceTypeName}</h2>
        <p>{service.providerName}{service.completedAt ? ` · Completado el ${formatDate(service.completedAt)}` : ""}</p>
      </header>
      {service.rating ? (
        <div className="customer-service-rating">
          <StarDisplay value={service.rating.rating} />
          {service.rating.comment && <p>{service.rating.comment}</p>}
          <time dateTime={service.rating.createdAt}>Valorado el {formatDate(service.rating.createdAt)}</time>
        </div>
      ) : service.completedAt ? (
        <RatingForm serviceId={service.serviceId} token={token} />
      ) : (
        <p className="customer-service-pending">Podrás valorar este servicio cuando esté completado.</p>
      )}
    </article>
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

function RatingForm({ serviceId, token }: { serviceId: string; token: string }) {
  const queryClient = useQueryClient();
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [fieldErrors, setFieldErrors] = useState<RatingDraftErrors>({});
  const [submitError, setSubmitError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const errors = validateRatingDraft({ rating, comment });
    setFieldErrors(errors);
    setSubmitError("");
    if (errors.rating !== undefined || rating === null) return;

    setBusy(true);
    try {
      const response = await createCustomerServiceRating(serviceId, { rating, comment: normalizeRatingComment(comment) }, token);
      if (response.ok) {
        await queryClient.invalidateQueries({ queryKey: SERVICES_QUERY_KEY });
        return;
      }
      if (response.status === 401) setSubmitError("Tu sesión expiró. Inicia sesión nuevamente para continuar.");
      else if (response.status === 404) setSubmitError("No encontramos este servicio en tu cuenta. Actualiza la página e inténtalo nuevamente.");
      else if (response.status === 409) {
        setSubmitError("Este servicio ya fue valorado.");
        await queryClient.invalidateQueries({ queryKey: SERVICES_QUERY_KEY });
      } else if (response.status === 422) setSubmitError("Solo puedes valorar servicios completados.");
      else setSubmitError("No pudimos guardar la valoración. Inténtalo nuevamente.");
    } catch {
      setSubmitError("No pudimos guardar la valoración. Revisa tu conexión e inténtalo nuevamente.");
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
      {submitError && <p className="customer-submit-error" role="alert">{submitError}</p>}
      <button className="button button-primary customer-rating-submit" disabled={busy} type="submit">{busy ? "Guardando…" : "Enviar valoración"}</button>
    </form>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("es-CL", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}
