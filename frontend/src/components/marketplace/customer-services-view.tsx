"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { CUSTOMER_SERVICES_LAYOUT, MarketplaceSkeleton } from "@/components/marketplace/marketplace-skeleton";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import {
  requestCustomerServices,
  type CustomerServicePage,
  type CustomerService,
} from "@/lib/marketplace-api";
import { nextCustomerServicesOffset } from "@/lib/customer-services-pagination";
import { formatServiceRoute, formatServiceSchedule } from "@/lib/customer-service-schedule";
import { serviceStatusLabel } from "@/lib/service-status";
import { CUSTOMER_SERVICES_KEY } from "@/lib/service-query-keys";
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
    queryKey: [...CUSTOMER_SERVICES_KEY, userId],
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
      queryClient.removeQueries({ queryKey: CUSTOMER_SERVICES_KEY });
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
      <main className="marketplace-main lp-app customer-services-page" id="contenido">
        <div className="customer-services-wrap">
          <h1>Mis servicios</h1>
          <p className="customer-services-intro">Revisa tus servicios. Entra a un servicio completado para valorarlo.</p>

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
                  <ServiceRow service={service} />
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

// The whole row is the link to the detail page, where the customer rates a completed service.
function ServiceRow({ service }: { service: CustomerService }) {
  const schedule = formatServiceSchedule(service.scheduledAt);
  const route = formatServiceRoute(service.origin, service.destination);
  return (
    <Link
      aria-label={`${service.serviceTypeName}, ${schedule}`}
      className="customer-service-card"
      href={`/cuenta/servicios/${encodeURIComponent(service.serviceId)}`}
    >
      <span className="customer-service-main">
        <h2>{service.serviceTypeName}</h2>
        <span className="customer-service-provider">{service.providerName}</span>
        <time className="customer-service-schedule" dateTime={service.scheduledAt ?? undefined}>{schedule}</time>
        <span className="customer-service-route">{route}</span>
      </span>
      <span className="customer-service-badges">
        <span className={`account-service-status account-service-status-${service.status}`}>{serviceStatusLabel(service.status)}</span>
        {service.completedAt && (
          <span className={`customer-service-chip ${service.rating ? "customer-service-chip-rated" : "customer-service-chip-pending"}`}>
            {service.rating ? "Valorado" : "Pendiente de valorar"}
          </span>
        )}
      </span>
    </Link>
  );
}
