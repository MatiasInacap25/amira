"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { requestCompanyDrivers, type CompanyDriver } from "@/lib/shared-trip-api";

const NOT_PROVIDED = "No indicado";
const LOAD_ERROR = "No pudimos cargar los conductores.";
const FORBIDDEN = "Esta sección solo está disponible para dueños de empresa.";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; drivers: CompanyDriver[] }
  | { kind: "forbidden" }
  | { kind: "error" };

/** Presentational list of the drivers linked to the company. */
export function LinkedDriversList({ drivers }: { drivers: CompanyDriver[] }) {
  if (drivers.length === 0) {
    return (
      <div className="marketplace-state marketplace-empty" role="status">
        <p>Todavía no tienes conductores enlazados.</p>
        <Link className="auth-secondary-action" href="/cuenta/invitaciones">Invitar conductores</Link>
      </div>
    );
  }
  return (
    <ul aria-label="Conductores enlazados" className="linked-drivers-list">
      {drivers.map((driver) => (
        <li className="linked-driver" key={driver.driverId}>
          <p className="linked-driver-name">
            <strong>{driver.firstName} {driver.lastName}</strong>
            {driver.isOwner && <span className="linked-driver-tag">Dueño</span>}
          </p>
          <dl className="linked-driver-facts">
            <div><dt>Correo</dt><dd>{driver.email}</dd></div>
            <div><dt>Teléfono</dt><dd>{driver.phone ?? NOT_PROVIDED}</dd></div>
            <div>
              <dt>Verificación</dt>
              <dd className={driver.verified ? "linked-driver-verified" : "linked-driver-unverified"}>
                {driver.verified ? "Verificado" : "Sin verificar"}
              </dd>
            </div>
          </dl>
        </li>
      ))}
    </ul>
  );
}

/** Container: loads the company's drivers with the caller's token. */
export function LinkedDriversPanel({ token }: { token: string }) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const load = useCallback(async (signal?: AbortSignal) => {
    setState({ kind: "loading" });
    try {
      const response = await requestCompanyDrivers(token, signal);
      if (response.status === 403) {
        setState({ kind: "forbidden" });
        return;
      }
      if (!response.ok) throw new Error(LOAD_ERROR);
      const body = await response.json() as { items: CompanyDriver[] };
      setState({ kind: "ready", drivers: body.items });
    } catch {
      if (!signal?.aborted) setState({ kind: "error" });
    }
  }, [token]);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => load(controller.signal));
    return () => controller.abort();
  }, [load]);

  if (state.kind === "loading") return <p role="status">Cargando conductores…</p>;
  if (state.kind === "forbidden") return <p className="auth-error" role="alert">{FORBIDDEN}</p>;
  if (state.kind === "error") {
    return (
      <div>
        <p className="auth-error" role="alert">{LOAD_ERROR}</p>
        <button className="auth-secondary-action" onClick={() => void load()} type="button">Reintentar</button>
      </div>
    );
  }
  return <LinkedDriversList drivers={state.drivers} />;
}
