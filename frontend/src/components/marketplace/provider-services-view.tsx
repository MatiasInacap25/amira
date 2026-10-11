"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { MarketplaceSkeleton, PROVIDER_SERVICES_LAYOUT } from "@/components/marketplace/marketplace-skeleton";
import { ServiceCard } from "@/components/marketplace/service-card";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import {
  parseServiceResponse,
  requestProviderServices,
  ServiceRequestError,
  type ServiceListPage,
  type ServiceStatus,
} from "@/lib/marketplace-api";
import { nextProviderRequestOffset } from "@/lib/provider-requests";
import { CustomerSessionError, readAccessToken, refreshAccessToken } from "@/lib/customer-session";
import { sendWithTokenRetry } from "@/lib/customer-request-retry";
import { SERVICE_STATUSES, serviceStatusLabel } from "@/lib/service-status";

const PAGE_SIZE = 20;
const SIGN_IN_HREF = "/login?next=%2Fcuenta%2Fservicios";

type StatusFilter = ServiceStatus | "all";
const FILTERS: readonly StatusFilter[] = ["all", ...SERVICE_STATUSES];

// Plural phrasing for the empty state of each filter ("No tienes servicios confirmados").
const EMPTY_FILTER_LABEL: Record<ServiceStatus, string> = {
  confirmed: "confirmados",
  in_progress: "en curso",
  completed: "finalizados",
  disputed: "en reclamo",
};

function filterLabel(filter: StatusFilter) {
  return filter === "all" ? "Todos" : serviceStatusLabel(filter);
}

/** Provider view of "Mis servicios": paginated list with a status filter. */
export function ProviderServicesView() {
  const [filter, setFilter] = useState<StatusFilter>("all");
  const servicesQuery = useInfiniteQuery({
    queryKey: ["provider-services", filter],
    queryFn: async ({ pageParam, signal }) => {
      const response = await sendWithTokenRetry(
        (accessToken) => requestProviderServices(
          accessToken,
          { status: filter === "all" ? undefined : filter, limit: PAGE_SIZE, offset: pageParam },
          signal,
        ),
        readAccessToken,
        refreshAccessToken,
      );
      if (response.status === 401) throw new CustomerSessionError();
      return parseServiceResponse<ServiceListPage>(response);
    },
    initialPageParam: 0,
    getNextPageParam: nextProviderRequestOffset,
    retry: false,
  });

  const services = servicesQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const error = servicesQuery.error;
  const needsSignIn = error instanceof CustomerSessionError;
  const failed = servicesQuery.isError && !needsSignIn;
  const forbidden = failed && error instanceof ServiceRequestError && error.status === 403;

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main customer-services-page" id="contenido">
        <div className="customer-services-wrap">
          <h1>Mis servicios</h1>
          <p className="customer-services-intro">Revisa los servicios que tienes contratados como prestador.</p>

          <div aria-label="Filtrar servicios por estado" className="account-service-filters" role="group">
            {FILTERS.map((option) => (
              <button
                aria-pressed={filter === option}
                className="account-service-filter"
                key={option}
                onClick={() => setFilter(option)}
                type="button"
              >
                {filterLabel(option)}
              </button>
            ))}
          </div>

          {needsSignIn && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos verificar tu sesión</h2>
              <p>Inicia sesión de nuevo para ver tus servicios.</p>
              <Link className="button button-secondary" href={SIGN_IN_HREF}>Iniciar sesión</Link>
            </div>
          )}
          {forbidden && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>Esta cuenta no tiene servicios de prestador</h2>
              <p>Los servicios como prestador solo están disponibles para conductores y empresas de transporte.</p>
            </div>
          )}
          {failed && !forbidden && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos cargar tus servicios</h2>
              <p>Inténtalo nuevamente en unos minutos.</p>
              <button className="button button-secondary" onClick={() => void servicesQuery.refetch()} type="button">Reintentar</button>
            </div>
          )}

          {!servicesQuery.isError && (
            <MarketplaceSkeleton label="Cargando tus servicios…" layout={PROVIDER_SERVICES_LAYOUT} loading={servicesQuery.isPending} name="provider-services">
              {servicesQuery.isSuccess && services.length === 0 && (
                <div className="marketplace-state marketplace-empty" role="status">
                  <h2>{filter === "all" ? "Aún no tienes servicios" : `No tienes servicios ${EMPTY_FILTER_LABEL[filter]}`}</h2>
                  <p>Cuando un cliente confirme un servicio contigo, aparecerá aquí.</p>
                </div>
              )}
              {services.length > 0 && (
                <ul className="account-service-list">
                  {services.map((service) => (
                    <li key={service.serviceId}>
                      <ServiceCard counterpartLabel="Cliente" service={service} />
                    </li>
                  ))}
                </ul>
              )}
            </MarketplaceSkeleton>
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
