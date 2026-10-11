"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { decideProviderRequest, getProviderRequests, type ProviderRequest } from "@/lib/marketplace-api";
import { createClient } from "@/lib/supabase/client";

async function currentAccessToken() {
  const client = createClient();
  const { data: userData, error: userError } = await client.auth.getUser();
  if (userError || !userData.user?.email_confirmed_at) throw new Error("sign-in");
  const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
  if (assuranceError) throw assuranceError;
  if (assurance.currentLevel !== "aal2") throw new Error("aal2");
  const { data, error } = await client.auth.getSession();
  if (error || !data.session?.access_token) throw new Error("session");
  return data.session.access_token;
}

function requestError(cause: unknown) {
  if (cause instanceof Error && cause.message === "sign-in") return "Inicia sesión con tu correo confirmado para ver las solicitudes.";
  if (cause instanceof Error && cause.message === "aal2") return "Verifica tu teléfono por SMS para administrar solicitudes.";
  if (cause instanceof Error && /API todavía no está configurada/i.test(cause.message)) return cause.message;
  return "No pudimos cargar las solicitudes. Inténtalo nuevamente.";
}

export function ProviderRequestInbox() {
  const [actionError, setActionError] = useState("");
  const requestQuery = useQuery({
    queryKey: ["provider-requests"],
    queryFn: async () => getProviderRequests(await currentAccessToken()),
    retry: false,
  });
  const items = requestQuery.data?.items ?? [];
  const error = requestQuery.error instanceof Error ? requestQuery.error : null;
  const state = requestQuery.isPending ? "loading" : requestQuery.isError
    ? error?.message && ["sign-in", "aal2", "session"].includes(error.message) ? "unauthenticated" : "error"
    : "ready";
  const [busyRequest, setBusyRequest] = useState<string | null>(null);

  async function decide(item: ProviderRequest, decision: "accept" | "reject") {
    if (busyRequest) return;
    setBusyRequest(item.requestId);
    setActionError("");
    try {
      const token = await currentAccessToken();
      const response = await decideProviderRequest(item.requestId, decision, token);
      if (!response.ok) {
        if (response.status === 401) throw new Error("session");
        if (response.status === 403) throw new Error("provider-role");
        if (response.status === 404) throw new Error("not-found");
        if (response.status === 409) throw new Error("already-decided");
        throw new Error("request-failed");
      }
      await requestQuery.refetch();
    } catch (cause) {
      if (cause instanceof Error && cause.message === "aal2") setActionError("Verifica tu teléfono por SMS para administrar solicitudes.");
      else if (cause instanceof Error && cause.message === "session") setActionError("Tu sesión expiró. Inicia sesión nuevamente.");
      else if (cause instanceof Error && cause.message === "provider-role") setActionError("Esta cuenta no puede administrar solicitudes de prestadores.");
      else if (cause instanceof Error && cause.message === "not-found") setActionError("La solicitud ya no está disponible para este perfil.");
      else if (cause instanceof Error && cause.message === "already-decided") setActionError("La solicitud ya fue respondida. Actualiza la lista.");
      else setActionError("No pudimos responder la solicitud. Inténtalo nuevamente.");
    } finally {
      setBusyRequest(null);
    }
  }

  return (
    <section aria-labelledby="provider-inbox-title" className="provider-inbox">
      <div className="provider-inbox-heading">
        <div><p className="eyebrow">PANEL DEL PRESTADOR</p><h1 id="provider-inbox-title">Solicitudes recibidas</h1></div>
        <button className="button button-secondary" disabled={requestQuery.isFetching} onClick={() => void requestQuery.refetch()} type="button">Actualizar</button>
      </div>
      {state === "loading" && <p className="marketplace-state" role="status">Cargando solicitudes…</p>}
      {state === "unauthenticated" && <div className="marketplace-state"><p role="alert">{requestError(error)}</p><Link className="button button-primary" href={`/login?next=${encodeURIComponent("/solicitudes")}`}>Iniciar sesión</Link></div>}
      {state === "error" && <div className="marketplace-state marketplace-error" role="alert"><p>{requestError(error)}</p><button className="button button-secondary" onClick={() => void requestQuery.refetch()} type="button">Reintentar</button></div>}
      {state === "ready" && actionError && <p className="provider-inbox-error" role="alert">{actionError}</p>}
      {state === "ready" && items.length === 0 && <div className="marketplace-state marketplace-empty" role="status"><h2>No tienes solicitudes todavía</h2><p>Cuando un cliente solicite una cotización para tu perfil, aparecerá aquí.</p></div>}
      {state === "ready" && items.length > 0 && (
        <div className="provider-request-list">
          {items.map((item) => (
            <article className="provider-request-card" key={item.requestId}>
              <div className="provider-request-card-heading"><div><p className="eyebrow">{item.serviceName}</p><h2>{item.origin} <span aria-hidden="true">→</span> {item.destination}</h2></div><span className={`provider-request-status provider-request-status-${item.status}`}>{item.status === "pending" ? "Pendiente" : item.status === "accepted" ? "Aceptada" : "Rechazada"}</span></div>
              <p className="provider-request-date">Recibida {new Intl.DateTimeFormat("es-CL", { dateStyle: "medium" }).format(new Date(item.createdAt))}{item.requestedAt && ` · Fecha solicitada ${new Intl.DateTimeFormat("es-CL", { dateStyle: "medium" }).format(new Date(item.requestedAt))}`}</p>
              {(item.description || item.cargoMeasurements || item.estimatedWeight || item.estimatedVolume) && <div className="provider-request-details">{item.description && <p>{item.description}</p>}{item.cargoMeasurements && <p><strong>Medidas:</strong> {item.cargoMeasurements}</p>}{item.estimatedWeight && <p><strong>Peso estimado:</strong> {item.estimatedWeight} kg</p>}{item.estimatedVolume && <p><strong>Volumen estimado:</strong> {item.estimatedVolume} m³</p>}</div>}
              <div className="provider-request-actions">
                {item.status === "pending" && <>
                  <button className="button button-secondary" disabled={busyRequest !== null} onClick={() => void decide(item, "reject")} type="button">{busyRequest === item.requestId ? "Guardando…" : "Rechazar"}</button>
                  <button className="button button-primary" disabled={busyRequest !== null} onClick={() => void decide(item, "accept")} type="button">{busyRequest === item.requestId ? "Guardando…" : "Aceptar y abrir chat"}</button>
                </>}
                {item.status === "accepted" && item.chatId && <Link className="button button-primary" href={`/mensajes/${encodeURIComponent(item.chatId)}`}>Abrir chat</Link>}
                {item.status === "rejected" && <span className="provider-request-closed">Solicitud cerrada</span>}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
