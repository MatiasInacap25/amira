"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, MapPin, Search, Truck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { getServices, type ServiceFilters } from "@/lib/marketplace-api";

const categories = [
  { value: "mudanza", label: "Mudanzas" },
  { value: "mercaderia", label: "Transporte de mercadería" },
  { value: "flete", label: "Fletes y traslados" },
  { value: "escombros", label: "Recolección de escombros" },
  { value: "grua", label: "Servicios de grúa" },
];

const initialFilters: ServiceFilters = { q: "", category: "", location: "", offset: 0 };

function categoryName(category: string) {
  return categories.find((item) => item.value === category)?.label ?? category;
}

export default function ServicesPage() {
  const [filters, setFilters] = useState(initialFilters);
  const [query, setQuery] = useState(initialFilters);
  const servicesQuery = useQuery({
    queryKey: ["services", query],
    queryFn: ({ signal }) => getServices(query, signal),
    retry: false,
    staleTime: 30_000,
  });

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextFilters = { ...filters, offset: 0 };
    setFilters(nextFilters);
    setQuery(nextFilters);
  }

  function movePage(offset: number) {
    const nextQuery = { ...query, offset };
    setQuery(nextQuery);
    setFilters(nextQuery);
  }

  const page = servicesQuery.data;
  const canGoBack = Boolean(page && page.offset > 0);
  const canGoForward = Boolean(page && page.offset + page.items.length < page.total);

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main" id="contenido">
        <a className="skip-link" href="#resultados">Ir a los resultados</a>
        <section aria-labelledby="services-title" className="marketplace-hero">
          <div className="marketplace-hero-inner">
            <p className="eyebrow"><span className="eyebrow-dot" /> SERVICIOS DE TRANSPORTE</p>
            <h1 id="services-title">Encuentra el servicio que necesitas.</h1>
            <p>Busca prestadores por tipo de servicio o comuna. Los resultados reflejan la información publicada y no incluyen calificaciones ni verificaciones.</p>
            <Link className="marketplace-back-link" href="/"><ArrowLeft aria-hidden="true" size={16} /> Volver a Amira</Link>
          </div>
        </section>

        <div className="marketplace-content">
          <form aria-label="Filtros de servicios" className="marketplace-filter" onSubmit={search}>
            <div className="filter-heading">
              <span className="filter-icon"><Search aria-hidden="true" size={19} /></span>
              <div><h2>Buscar servicios</h2><p>Usa uno o más filtros para acotar los resultados.</p></div>
            </div>
            <div className="filter-fields service-filter-fields">
              <label className="marketplace-field" htmlFor="service-query">
                <span>Buscar por servicio o prestador</span>
                <input autoComplete="off" id="service-query" onChange={(event) => setFilters({ ...filters, q: event.target.value })} placeholder="Por ejemplo, mudanza" value={filters.q} />
              </label>
              <label className="marketplace-field" htmlFor="service-category">
                <span>Categoría</span>
                <select id="service-category" onChange={(event) => setFilters({ ...filters, category: event.target.value })} value={filters.category}>
                  <option value="">Todas las categorías</option>
                  {categories.map((category) => <option key={category.value} value={category.value}>{category.label}</option>)}
                </select>
              </label>
              <label className="marketplace-field" htmlFor="service-location">
                <span>Comuna o ciudad</span>
                <span className="marketplace-input-icon"><MapPin aria-hidden="true" size={16} /><input autoComplete="address-level2" id="service-location" onChange={(event) => setFilters({ ...filters, location: event.target.value })} placeholder="Por ejemplo, Santiago" value={filters.location} /></span>
              </label>
              <button className="button button-primary filter-submit" type="submit"><Search aria-hidden="true" size={16} /> Buscar servicios</button>
            </div>
          </form>

          <section aria-labelledby="results-title" className="marketplace-results" id="resultados">
            <div className="results-heading"><div><p className="eyebrow">PRESTADORES PUBLICADOS</p><h2 id="results-title">Servicios disponibles</h2></div>{page && <p className="results-count">{page.total} {page.total === 1 ? "resultado" : "resultados"}</p>}</div>

            {servicesQuery.isPending && <div className="marketplace-state" role="status"><span className="state-spinner" aria-hidden="true" />Cargando servicios…</div>}
            {servicesQuery.isError && (
              <div className="marketplace-state marketplace-error" role="alert">
                <h3>No pudimos cargar los servicios</h3>
                <p>Comprueba tu conexión e inténtalo nuevamente. No mostraremos información de ejemplo como si fuera una oferta activa.</p>
                <button className="button button-secondary" onClick={() => void servicesQuery.refetch()} type="button">Reintentar</button>
              </div>
            )}
            {servicesQuery.isSuccess && page?.items.length === 0 && (
              <div className="marketplace-state marketplace-empty" role="status">
                <span className="empty-icon"><Truck aria-hidden="true" size={23} /></span>
                <h3>No encontramos servicios con esos filtros</h3>
                <p>Prueba con otra categoría o comuna. Los resultados dependen de los prestadores publicados en Amira.</p>
              </div>
            )}
            {servicesQuery.isSuccess && page && page.items.length > 0 && (
              <div className="service-results-grid">
                {page.items.map((service) => (
                  <article className="marketplace-card service-result-card" key={service.profileId}>
                    <div className="service-result-top">
                      <span aria-hidden="true" className="provider-mark"><Truck size={21} strokeWidth={1.8} /></span>
                      <span className="service-result-category">{categoryName(service.category)}</span>
                    </div>
                    <h3>{service.providerName}</h3>
                    <p className="service-result-description">{service.description || "El prestador no agregó una descripción."}</p>
                    {service.location && <p className="service-result-location"><MapPin aria-hidden="true" size={15} />{service.location}</p>}
                    <p className="service-result-note">La disponibilidad y las condiciones se coordinan directamente con el prestador.</p>
                  </article>
                ))}
              </div>
            )}

            {page && page.total > 20 && (
              <nav aria-label="Páginas de resultados" className="pagination-controls">
                <button className="button button-secondary" disabled={!canGoBack} onClick={() => movePage(Math.max(0, query.offset - 20))} type="button"><ArrowLeft aria-hidden="true" size={15} /> Anterior</button>
                <span>Resultados {page.offset + 1}–{page.offset + page.items.length} de {page.total}</span>
                <button className="button button-secondary" disabled={!canGoForward} onClick={() => movePage(query.offset + 20)} type="button">Siguiente <ArrowRight aria-hidden="true" size={15} /></button>
              </nav>
            )}
          </section>
          <p className="marketplace-transparency">No se muestran calificaciones ni verificaciones que Amira no ofrece. Amira no procesa pagos ni confirma reservas.</p>
        </div>
      </main>
      <MarketplaceFooter />
    </>
  );
}
