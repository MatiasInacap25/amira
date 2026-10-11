"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { PROVIDER_REQUEST_DETAIL_LAYOUT, MarketplaceSkeleton } from "@/components/marketplace/marketplace-skeleton";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { decideProviderRequest, getProviderRequest, type ProviderRequest, type ProviderRequestDecision } from "@/lib/marketplace-api";
import { currentAccessToken, isSignInRequired, requestErrorMessage } from "@/lib/provider-request-access";
import { customerDisplayName, formatRouteEndpoint, type ProviderRequestStatus } from "@/lib/provider-requests";

const STATUS_LABEL: Record<ProviderRequestStatus, string> = {
  pending: "Pendiente",
  accepted: "Aceptada",
  rejected: "Rechazada",
};
const dateFormatter = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium" });

class RequestNotFoundError extends Error {}

function formatDate(value: string | null) {
  return value ? dateFormatter.format(new Date(value)) : "No indicada";
}

function decisionErrorMessage(cause: unknown) {
  if (isSignInRequired(cause)) return requestErrorMessage(cause);
  if (cause instanceof Error && cause.message === "already-decided") return "La solicitud ya fue respondida. Actualiza la página.";
  if (cause instanceof Error && cause.message === "provider-role") return "Esta cuenta no puede administrar solicitudes de prestadores.";
  if (cause instanceof Error && cause.message === "not-found") return "La solicitud ya no está disponible para este perfil.";
  return "No pudimos responder la solicitud. Inténtalo nuevamente.";
}

export function ProviderRequestDetail({ requestId }: { requestId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<"accept" | "reject" | null>(null);
  const [actionError, setActionError] = useState("");

  const requestQuery = useQuery({
    queryKey: ["provider-request", requestId],
    queryFn: async () => {
      const response = await getProviderRequest(await currentAccessToken(), requestId);
      if (response.status === 404) throw new RequestNotFoundError();
      if (!response.ok) throw new Error(`Provider request failed (${response.status})`);
      return response.json() as Promise<ProviderRequest>;
    },
    retry: false,
  });

  const item = requestQuery.data;
  const queryError = requestQuery.error;

  async function decide(decision: "accept" | "reject") {
    if (busy || !item) return;
    setBusy(decision === "accept" ? "accept" : "reject");
    setActionError("");
    try {
      const response = await decideProviderRequest(item.requestId, decision, await currentAccessToken());
      if (response.status === 401) throw new Error("session");
      if (response.status === 403) throw new Error("provider-role");
      if (response.status === 404) throw new Error("not-found");
      if (response.status === 409) throw new Error("already-decided");
      if (!response.ok) throw new Error("request-failed");
      const decided = await response.json() as ProviderRequestDecision;
      await queryClient.invalidateQueries({ queryKey: ["provider-requests"] });
      await queryClient.invalidateQueries({ queryKey: ["provider-request", requestId] });
      await queryClient.invalidateQueries({ queryKey: ["provider-nav-pending"] });
      if (decision === "accept" && decided.chatId) {
        router.push(`/mensajes/${encodeURIComponent(decided.chatId)}`);
        return;
      }
      await requestQuery.refetch();
    } catch (cause) {
      setActionError(decisionErrorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  const route = item
    ? {
      origin: formatRouteEndpoint(item.originCommuneName, item.originRegionName, item.origin),
      destination: formatRouteEndpoint(item.destinationCommuneName, item.destinationRegionName, item.destination),
    }
    : null;
  const hasCargo = Boolean(item && (item.description || item.cargoMeasurements || item.estimatedWeight || item.estimatedVolume));

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main provider-inbox-page" id="contenido">
        <section aria-labelledby="provider-request-title" className="provider-inbox provider-request-detail">
          <Link className="provider-request-back" href="/solicitudes"><ArrowLeft aria-hidden="true" size={15} /> Volver a solicitudes</Link>

          {isSignInRequired(queryError) && (
            <div className="marketplace-state">
              <p role="alert">{requestErrorMessage(queryError)}</p>
              <Link className="button button-primary" href={`/login?next=${encodeURIComponent(`/solicitudes/${requestId}`)}`}>Iniciar sesión</Link>
            </div>
          )}
          {queryError instanceof RequestNotFoundError && (
            <div className="marketplace-state marketplace-empty" role="alert">
              <h2>Solicitud no disponible</h2>
              <p>La solicitud ya no está disponible para este perfil.</p>
            </div>
          )}
          {queryError && !isSignInRequired(queryError) && !(queryError instanceof RequestNotFoundError) && (
            <div className="marketplace-state marketplace-error" role="alert">
              <p>No pudimos cargar la solicitud. Inténtalo nuevamente.</p>
              <button className="button button-secondary" onClick={() => void requestQuery.refetch()} type="button">Reintentar</button>
            </div>
          )}

          {!queryError && (
            <MarketplaceSkeleton
              label="Cargando solicitud…"
              layout={PROVIDER_REQUEST_DETAIL_LAYOUT}
              loading={requestQuery.isPending}
              name="provider-request-detail"
            >
              {item && route && (
                <>
                  <div className="provider-request-card-heading">
                    <div>
                      <p className="eyebrow">{item.serviceName}</p>
                      <h1 id="provider-request-title">{route.origin} <span aria-hidden="true">→</span> {route.destination}</h1>
                    </div>
                    <span className={`provider-request-status provider-request-status-${item.status}`}>{STATUS_LABEL[item.status as ProviderRequestStatus] ?? "Estado desconocido"}</span>
                  </div>

                  <div className="provider-request-panel">
                    <h2>Resumen</h2>
                    <dl className="provider-request-facts">
                      <div><dt>Origen</dt><dd>{route.origin}</dd></div>
                      <div><dt>Destino</dt><dd>{route.destination}</dd></div>
                      <div><dt>Cliente</dt><dd>{customerDisplayName(item)}</dd></div>
                      <div><dt>Modalidad</dt><dd>{item.isExclusive ? "Servicio exclusivo" : "Servicio compartido"}</dd></div>
                      <div><dt>Fecha solicitada</dt><dd>{formatDate(item.requestedAt)}</dd></div>
                      <div><dt>Recibida</dt><dd>{formatDate(item.createdAt)}</dd></div>
                    </dl>
                    {item.status === "pending" && (
                      <p className="provider-request-privacy">Verás el apellido del cliente después de aceptar la solicitud.</p>
                    )}
                  </div>

                  <div className="provider-request-panel">
                    <h2>Detalle de la carga</h2>
                    {hasCargo ? (
                      <dl className="provider-request-facts">
                        {item.description && <div><dt>Descripción</dt><dd>{item.description}</dd></div>}
                        {item.cargoMeasurements && <div><dt>Medidas</dt><dd>{item.cargoMeasurements}</dd></div>}
                        {item.estimatedWeight && <div><dt>Peso estimado</dt><dd>{item.estimatedWeight} kg</dd></div>}
                        {item.estimatedVolume && <div><dt>Volumen estimado</dt><dd>{item.estimatedVolume} m³</dd></div>}
                      </dl>
                    ) : (
                      <p className="provider-request-muted">El cliente no especificó detalles de la carga.</p>
                    )}
                  </div>

                  {actionError && <p className="provider-inbox-error" role="alert">{actionError}</p>}
                  <div className="provider-request-actions">
                    {item.status === "pending" && <>
                      <button className="button button-secondary" disabled={busy !== null} onClick={() => void decide("reject")} type="button">{busy === "reject" ? "Guardando…" : "Rechazar"}</button>
                      <button className="button button-primary" disabled={busy !== null} onClick={() => void decide("accept")} type="button">{busy === "accept" ? "Guardando…" : "Aceptar y abrir chat"}</button>
                    </>}
                    {item.status === "accepted" && item.chatId && <Link className="button button-primary" href={`/mensajes/${encodeURIComponent(item.chatId)}`}>Abrir chat</Link>}
                    {item.status === "rejected" && <span className="provider-request-closed">Solicitud cerrada</span>}
                  </div>
                </>
              )}
            </MarketplaceSkeleton>
          )}
        </section>
      </main>
      <MarketplaceFooter />
    </>
  );
}
