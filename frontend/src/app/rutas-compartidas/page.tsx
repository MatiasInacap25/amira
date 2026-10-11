"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CalendarDays, Route, Truck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { RegionCommuneSelect, type RegionCommuneValue } from "@/components/marketplace/region-commune-select";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { getSharedRoutes, type SharedRouteFilters } from "@/lib/marketplace-api";

const initialFilters: SharedRouteFilters = { originCommuneCode: "", destinationCommuneCode: "", departureFrom: "", departureTo: "", offset: 0 };
const emptyLocation: RegionCommuneValue = { regionCode: "", communeCode: "" };

function formatDeparture(value: string | null | undefined) {
  if (!value) return "Fecha por confirmar";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Fecha por confirmar";
  return new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" }).format(date);
}

export default function SharedRoutesPage() {
  const [filters, setFilters] = useState(initialFilters);
  const [query, setQuery] = useState(initialFilters);
  const [dateError, setDateError] = useState("");
  const [originLocation, setOriginLocation] = useState<RegionCommuneValue>(emptyLocation);
  const [destinationLocation, setDestinationLocation] = useState<RegionCommuneValue>(emptyLocation);
  const routesQuery = useQuery({
    queryKey: ["shared-routes", query],
    queryFn: ({ signal }) => getSharedRoutes(query, signal),
    retry: false,
    staleTime: 30_000,
  });

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (filters.departureFrom && filters.departureTo && filters.departureFrom > filters.departureTo) {
      setDateError("La fecha de término debe ser igual o posterior a la fecha de inicio.");
      return;
    }
    setDateError("");
    const nextFilters = {
      ...filters,
      originCommuneCode: originLocation.communeCode,
      destinationCommuneCode: destinationLocation.communeCode,
      offset: 0,
    };
    setFilters(nextFilters);
    setQuery(nextFilters);
  }

  function movePage(offset: number) {
    const nextQuery = { ...query, offset };
    setQuery(nextQuery);
    setFilters(nextQuery);
  }

  const page = routesQuery.data;
  const canGoBack = Boolean(page && page.offset > 0);
  const canGoForward = Boolean(page && page.offset + page.items.length < page.total);

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main" id="contenido">
        <a className="skip-link" href="#resultados">Ir a los resultados</a>
        <section aria-labelledby="routes-title" className="marketplace-hero routes-hero">
          <div className="marketplace-hero-inner">
            <p className="eyebrow"><span className="eyebrow-dot" /> VIAJES COMPARTIDOS</p>
            <h1 id="routes-title">Encuentra una ruta publicada.</h1>
            <p>Consulta viajes que aceptan solicitudes de espacio. La disponibilidad y compatibilidad de cada carga las confirma el transportista.</p>
            <Link className="marketplace-back-link" href="/"><ArrowLeft aria-hidden="true" size={16} /> Volver a Amira</Link>
          </div>
        </section>

        <div className="marketplace-content">
          <form aria-label="Filtros de rutas compartidas" className="marketplace-filter" onSubmit={search}>
            <div className="filter-heading">
              <span className="filter-icon"><Route aria-hidden="true" size={19} /></span>
              <div><h2>Buscar viajes en ruta</h2><p>Filtra por origen, destino y fecha de salida.</p></div>
            </div>
            <div className="filter-fields route-filter-fields">
              <RegionCommuneSelect
                communeLabel="Comuna de origen"
                idPrefix="route-origin"
                onChange={setOriginLocation}
                optional
                regionLabel="Región de origen"
                value={originLocation}
              />
              <RegionCommuneSelect
                communeLabel="Comuna de destino"
                idPrefix="route-destination"
                onChange={setDestinationLocation}
                optional
                regionLabel="Región de destino"
                value={destinationLocation}
              />
              <label className="marketplace-field" htmlFor="departure-from">
                <span>Desde la fecha</span>
                <span className="marketplace-input-icon"><CalendarDays aria-hidden="true" size={16} /><input aria-describedby={dateError ? "route-date-error" : undefined} aria-invalid={dateError ? true : undefined} id="departure-from" onChange={(event) => { setFilters({ ...filters, departureFrom: event.target.value }); setDateError(""); }} type="date" value={filters.departureFrom} /></span>
              </label>
              <label className="marketplace-field" htmlFor="departure-to">
                <span>Hasta la fecha</span>
                <span className="marketplace-input-icon"><CalendarDays aria-hidden="true" size={16} /><input aria-describedby={dateError ? "route-date-error" : undefined} aria-invalid={dateError ? true : undefined} id="departure-to" onChange={(event) => { setFilters({ ...filters, departureTo: event.target.value }); setDateError(""); }} type="date" value={filters.departureTo} /></span>
              </label>
              <button className="button button-primary filter-submit" type="submit"><Route aria-hidden="true" size={16} /> Buscar rutas</button>
            </div>
            {dateError && <p className="filter-validation" id="route-date-error" role="alert">{dateError}</p>}
          </form>

          <section aria-labelledby="results-title" className="marketplace-results" id="resultados">
            <div className="results-heading"><div><p className="eyebrow">PUBLICADAS Y DISPONIBLES</p><h2 id="results-title">Rutas compartidas</h2></div>{page && <p className="results-count">{page.total} {page.total === 1 ? "ruta" : "rutas"}</p>}</div>

            {routesQuery.isPending && <div className="marketplace-state" role="status"><span className="state-spinner" aria-hidden="true" />Cargando rutas…</div>}
            {routesQuery.isError && (
              <div className="marketplace-state marketplace-error" role="alert">
                <h3>No pudimos cargar las rutas</h3>
                <p>Comprueba tu conexión e inténtalo nuevamente. No mostraremos rutas de ejemplo como si estuvieran disponibles.</p>
                <button className="button button-secondary" onClick={() => void routesQuery.refetch()} type="button">Reintentar</button>
              </div>
            )}
            {routesQuery.isSuccess && page?.items.length === 0 && (
              <div className="marketplace-state marketplace-empty" role="status">
                <span className="empty-icon"><Route aria-hidden="true" size={23} /></span>
                <h3>No encontramos rutas con esos filtros</h3>
                <p>Prueba con otra combinación o fecha. La lista muestra solo viajes publicados que aceptan solicitudes.</p>
              </div>
            )}
            {routesQuery.isSuccess && page && page.items.length > 0 && (
              <div className="route-results-grid">
                {page.items.map((route) => (
                  <article aria-labelledby={`route-${route.tripId}`} className="marketplace-card shared-route-card" key={route.tripId}>
                    <div className="route-result-top"><span className="provider-mark"><Truck aria-hidden="true" size={21} strokeWidth={1.8} /></span><span className="route-published-label">Ruta publicada</span></div>
                    <h3 id={`route-${route.tripId}`}>{route.origin} a {route.destination}</h3>
                    <p className="route-provider">Transportista: <strong><Link className="route-provider-link" href={`/prestadores/${encodeURIComponent(route.profileId)}`}>{route.providerName}</Link></strong></p>
                    <p className="route-departure"><CalendarDays aria-hidden="true" size={15} />Salida: {formatDeparture(route.departureAt)}</p>
                    {route.stops && route.stops.length > 0 && (
                      <div className="route-stops">
                        <h4>Paradas informadas</h4>
                        <ol>{route.stops.map((stop) => <li key={stop.stopNumber}><span>Parada intermedia {stop.stopNumber}</span>{stop.estimatedAt && <time dateTime={stop.estimatedAt}>{formatDeparture(stop.estimatedAt)}</time>}</li>)}</ol>
                      </div>
                    )}
                    <p className="route-confirmation-note">No es una reserva: el transportista debe confirmar espacio, carga compatible y condiciones del viaje.</p>
                  </article>
                ))}
              </div>
            )}

            {page && page.total > 20 && (
              <nav aria-label="Páginas de rutas" className="pagination-controls">
                <button className="button button-secondary" disabled={!canGoBack} onClick={() => movePage(Math.max(0, query.offset - 20))} type="button"><ArrowLeft aria-hidden="true" size={15} /> Anterior</button>
                <span>Resultados {page.offset + 1}–{page.offset + page.items.length} de {page.total}</span>
                <button className="button button-secondary" disabled={!canGoForward} onClick={() => movePage(query.offset + 20)} type="button">Siguiente <ArrowRight aria-hidden="true" size={15} /></button>
              </nav>
            )}
          </section>
          <p className="marketplace-transparency">Consultar una ruta no reserva espacio ni inicia una solicitud. Amira no procesa pagos ni confirma reservas.</p>
        </div>
      </main>
      <MarketplaceFooter />
    </>
  );
}
