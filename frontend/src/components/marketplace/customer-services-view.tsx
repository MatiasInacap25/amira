"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { CUSTOMER_SERVICES_LAYOUT, MarketplaceSkeleton } from "@/components/marketplace/marketplace-skeleton";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import {
  createCustomerServiceRating,
  requestCustomerServices,
  type CustomerServicePage,
  type CustomerService,
} from "@/lib/marketplace-api";
import { normalizeRatingComment, RATING_COMMENT_MAX_LENGTH, validateRatingDraft, type RatingDraftErrors } from "@/lib/customer-rating-validation";
import { nextCustomerServicesOffset } from "@/lib/customer-services-pagination";
import { shouldClearCustomerCache } from "@/lib/customer-cache-policy";
import { sendWithTokenRetry } from "@/lib/customer-request-retry";
import {
  CustomerSessionError,
  readAccessToken,
  readCustomerUserId,
  refreshAccessToken,
} from "@/lib/customer-session";
import { createClient } from "@/lib/supabase/client";

// Services are cached per user. The auth query holds only the user id; tokens are read per request.
const AUTH_QUERY_KEY = ["customer-auth"];
const SERVICES_QUERY_KEY = ["customer-services"];
const SIGN_IN_HREF = "/login?next=%2Fcuenta%2Fservicios";

export function CustomerServicesView() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const sessionQuery = useQuery({
    queryKey: AUTH_QUERY_KEY,
    queryFn: async () => ({ userId: await readCustomerUserId() }),
    retry: false,
    staleTime: 60_000,
  });
  const userId = sessionQuery.data?.userId ?? "";
  const servicesQuery = useInfiniteQuery({
    queryKey: [...SERVICES_QUERY_KEY, userId],
    queryFn: async ({ pageParam, signal }) => {
      const response = await sendWithTokenRetry(
        (accessToken) => requestCustomerServices(accessToken, pageParam, signal),
        readAccessToken,
        refreshAccessToken,
      );
      if (response.status === 401) throw new CustomerSessionError();
      if (!response.ok) throw new Error(`Customer services failed (${response.status})`);
      return response.json() as Promise<CustomerServicePage>;
    },
    initialPageParam: 0,
    getNextPageParam: nextCustomerServicesOffset,
    enabled: Boolean(userId),
    retry: false,
  });

  useEffect(() => {
    const { data } = createClient().auth.onAuthStateChange((event, session) => {
      if (event === "INITIAL_SESSION") return;
      const cachedUserId = queryClient.getQueryData<{ userId: string }>(AUTH_QUERY_KEY)?.userId;
      if (!shouldClearCustomerCache(event, cachedUserId, session?.user.id)) return;
      queryClient.removeQueries({ queryKey: SERVICES_QUERY_KEY });
      void queryClient.resetQueries({ queryKey: AUTH_QUERY_KEY });
    });
    return () => data.subscription.unsubscribe();
  }, [queryClient]);

  const sessionExpired = sessionQuery.error instanceof CustomerSessionError;
  useEffect(() => {
    if (sessionExpired) router.replace(SIGN_IN_HREF);
  }, [router, sessionExpired]);

  const services = servicesQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const needsSignIn = sessionQuery.isError || servicesQuery.error instanceof CustomerSessionError;
  const servicesFailed = servicesQuery.isError && !(servicesQuery.error instanceof CustomerSessionError);

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main customer-services-page" id="contenido">
        <div className="customer-services-wrap">
          <h1>Mis servicios</h1>
          <p className="customer-services-intro">Valora los servicios completados. Tu valoración aparece en el perfil del prestador.</p>

          {needsSignIn && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos verificar tu sesión</h2>
              <p>Inicia sesión de nuevo para ver tus servicios.</p>
              <Link className="button button-secondary" href={SIGN_IN_HREF}>Iniciar sesión</Link>
            </div>
          )}
          {servicesFailed && (
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

          <MarketplaceSkeleton label="Cargando tus servicios…" layout={CUSTOMER_SERVICES_LAYOUT} loading={sessionQuery.isPending || Boolean(userId && servicesQuery.isPending)} name="customer-services">
          {services.length > 0 && (
            <ul className="customer-service-list">
              {services.map((service) => (
                <li className="customer-service-row" key={service.serviceId}>
                  <ServiceRatingRow service={service} />
                </li>
              ))}
            </ul>
          )}
          </MarketplaceSkeleton>

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

function ServiceRatingRow({ service }: { service: CustomerService }) {
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
        <RatingForm serviceId={service.serviceId} />
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

function RatingForm({ serviceId }: { serviceId: string }) {
  const queryClient = useQueryClient();
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [fieldErrors, setFieldErrors] = useState<RatingDraftErrors>({});
  const [submitError, setSubmitError] = useState("");
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const errors = validateRatingDraft({ rating, comment });
    setFieldErrors(errors);
    setSubmitError("");
    setNeedsSignIn(false);
    if (errors.rating !== undefined || rating === null) return;

    setBusy(true);
    try {
      const response = await sendWithTokenRetry(
        (accessToken) => createCustomerServiceRating(serviceId, { rating, comment: normalizeRatingComment(comment) }, accessToken),
        readAccessToken,
        refreshAccessToken,
      );
      if (response.ok) {
        await queryClient.invalidateQueries({ queryKey: SERVICES_QUERY_KEY });
        return;
      }
      if (response.status === 401) {
        setNeedsSignIn(true);
        setSubmitError("Tu sesión expiró. Inicia sesión nuevamente para continuar.");
      }
      else if (response.status === 404) setSubmitError("No encontramos este servicio en tu cuenta. Actualiza la página e inténtalo nuevamente.");
      else if (response.status === 409) {
        setSubmitError("Este servicio ya fue valorado.");
        await queryClient.invalidateQueries({ queryKey: SERVICES_QUERY_KEY });
      } else if (response.status === 422) setSubmitError("Solo puedes valorar servicios completados.");
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
