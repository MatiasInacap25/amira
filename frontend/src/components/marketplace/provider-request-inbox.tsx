"use client";

import Link from "next/link";
import { useRef, useState, type KeyboardEvent } from "react";
import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { MarketplaceSkeleton, PROVIDER_REQUESTS_LAYOUT } from "@/components/marketplace/marketplace-skeleton";
import { getProviderRequests, type ProviderRequest } from "@/lib/marketplace-api";
import { currentAccessToken, isSignInRequired, requestErrorMessage } from "@/lib/provider-request-access";
import {
  customerDisplayName,
  formatRouteEndpoint,
  nextProviderRequestOffset,
  resolveInboxPanel,
  type ProviderRequestStatus,
} from "@/lib/provider-requests";

const PAGE_SIZE = 20;
const TABS: { status: ProviderRequestStatus; label: string; empty: string }[] = [
  { status: "pending", label: "Pendientes", empty: "No tienes solicitudes pendientes por responder." },
  { status: "accepted", label: "Aceptadas", empty: "Todavía no has aceptado solicitudes." },
  { status: "rejected", label: "Rechazadas", empty: "No tienes solicitudes rechazadas." },
];
const STATUS_LABEL: Record<ProviderRequestStatus, string> = {
  pending: "Pendiente",
  accepted: "Aceptada",
  rejected: "Rechazada",
};
const dateFormatter = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium" });

function statusLabel(status: string) {
  return STATUS_LABEL[status as ProviderRequestStatus] ?? "Estado desconocido";
}

function routeLabel(item: ProviderRequest) {
  const origin = formatRouteEndpoint(item.originCommuneName, item.originRegionName, item.origin);
  const destination = formatRouteEndpoint(item.destinationCommuneName, item.destinationRegionName, item.destination);
  return { origin, destination };
}

export function ProviderRequestInbox() {
  const [status, setStatus] = useState<ProviderRequestStatus>("pending");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const requestsQuery = useInfiniteQuery({
    queryKey: ["provider-requests", status],
    queryFn: async ({ pageParam }) => getProviderRequests(await currentAccessToken(), { status, limit: PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: nextProviderRequestOffset,
    // Keeps the previous tab's counts while the next tab loads. Its rows are hidden via resolveInboxPanel.
    placeholderData: keepPreviousData,
    retry: false,
  });

  const pages = requestsQuery.data?.pages ?? [];
  const items = pages.flatMap((page) => page.items);
  const counts = pages[0]?.counts;
  const panel = resolveInboxPanel({
    pending: requestsQuery.isPending,
    placeholder: requestsQuery.isPlaceholderData,
    hasItems: items.length > 0,
    hasNextPage: Boolean(requestsQuery.hasNextPage),
  });
  const rows = panel.showRows ? items : [];
  const error = requestsQuery.isError ? requestsQuery.error : null;
  const activeTab = TABS.find((tab) => tab.status === status) ?? TABS[0];

  function focusTab(index: number) {
    const next = (index + TABS.length) % TABS.length;
    setStatus(TABS[next].status);
    tabRefs.current[next]?.focus();
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "ArrowRight") focusTab(index + 1);
    else if (event.key === "ArrowLeft") focusTab(index - 1);
    else if (event.key === "Home") focusTab(0);
    else if (event.key === "End") focusTab(TABS.length - 1);
  }

  return (
    <section aria-labelledby="provider-inbox-title" className="provider-inbox">
      <div className="provider-inbox-heading">
        <div><p className="eyebrow">PANEL DEL PRESTADOR</p><h1 id="provider-inbox-title">Solicitudes recibidas</h1></div>
        <button className="button button-secondary" disabled={requestsQuery.isFetching} onClick={() => void requestsQuery.refetch()} type="button">Actualizar</button>
      </div>

      <div aria-label="Filtrar solicitudes por estado" className="provider-inbox-tabs" role="tablist">
        {TABS.map((tab, index) => {
          const selected = tab.status === status;
          const count = counts?.[tab.status];
          return (
            <button
              aria-controls="provider-inbox-panel"
              aria-selected={selected}
              className="provider-inbox-tab"
              id={`provider-tab-${tab.status}`}
              key={tab.status}
              onClick={() => setStatus(tab.status)}
              onKeyDown={(event) => handleTabKeyDown(event, index)}
              ref={(node) => { tabRefs.current[index] = node; }}
              role="tab"
              tabIndex={selected ? 0 : -1}
              type="button"
            >
              {tab.label}
              {count !== undefined && <span className="provider-inbox-count">{count}</span>}
            </button>
          );
        })}
      </div>

      <div aria-busy={panel.busy} aria-labelledby={`provider-tab-${status}`} className="provider-inbox-panel" id="provider-inbox-panel" role="tabpanel">
        {isSignInRequired(error) && (
          <div className="marketplace-state">
            <p role="alert">{requestErrorMessage(error)}</p>
            <Link className="button button-primary" href={`/login?next=${encodeURIComponent("/solicitudes")}`}>Iniciar sesión</Link>
          </div>
        )}
        {error && !isSignInRequired(error) && (
          <div className="marketplace-state marketplace-error" role="alert">
            <p>{requestErrorMessage(error)}</p>
            <button className="button button-secondary" onClick={() => void requestsQuery.refetch()} type="button">Reintentar</button>
          </div>
        )}

        {!error && (
          <MarketplaceSkeleton
            label="Cargando solicitudes…"
            layout={PROVIDER_REQUESTS_LAYOUT}
            loading={panel.busy}
            name="provider-requests"
          >
            {rows.length === 0 ? (
              <div className="marketplace-state marketplace-empty" role="status">
                <h2>{activeTab.empty}</h2>
                <p>Cuando un cliente solicite una cotización para tu perfil, aparecerá aquí.</p>
              </div>
            ) : (
              <>
                <ul className="provider-request-list">
                  {rows.map((item) => {
                    const route = routeLabel(item);
                    return (
                      <li key={item.requestId}>
                        <article className="provider-request-card">
                          <div className="provider-request-card-heading">
                            <div>
                              <p className="eyebrow">{item.serviceName}</p>
                              <h2>
                                <Link className="provider-request-card-link" href={`/solicitudes/${encodeURIComponent(item.requestId)}`}>
                                  {route.origin} <span aria-hidden="true">→</span> {route.destination}
                                </Link>
                              </h2>
                            </div>
                            <span className={`provider-request-status provider-request-status-${item.status}`}>{statusLabel(item.status)}</span>
                          </div>
                          <p className="provider-request-customer">Cliente: {customerDisplayName(item)}</p>
                          <p className="provider-request-date">Recibida {dateFormatter.format(new Date(item.createdAt))}</p>
                        </article>
                      </li>
                    );
                  })}
                </ul>
                {panel.showLoadMore && (
                  <div className="provider-inbox-more">
                    <button
                      className="button button-secondary"
                      disabled={requestsQuery.isFetchingNextPage}
                      onClick={() => void requestsQuery.fetchNextPage()}
                      type="button"
                    >
                      {requestsQuery.isFetchingNextPage ? "Cargando…" : "Cargar más"}
                    </button>
                  </div>
                )}
              </>
            )}
          </MarketplaceSkeleton>
        )}
      </div>
    </section>
  );
}
