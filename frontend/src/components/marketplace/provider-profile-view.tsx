"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, MapPin, Package, Truck, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { QuoteRequestDialog } from "@/components/marketplace/quote-request-dialog";
import { getProviderProfile } from "@/lib/marketplace-api";

export function ProviderProfileView({ profileId }: { profileId: string }) {
  const [quoteDialogOpen, setQuoteDialogOpen] = useState(false);
  const query = useQuery({
    queryKey: ["provider-profile", profileId],
    queryFn: ({ signal }) => getProviderProfile(profileId, signal),
    retry: false,
    staleTime: 30_000,
  });

  function requestQuote() {
    setQuoteDialogOpen(true);
  }

  const profile = query.data;
  const sections = [
    { id: "resumen", label: "Resumen" },
    { id: "flota", label: "Flota" },
    { id: "conductores", label: "Conductores" },
    { id: "servicios", label: "Servicios" },
    { id: "valoraciones", label: "Valoraciones" },
  ];

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main provider-profile-page" id="contenido">
        <a className="skip-link" href="#provider-profile-content">Ir al perfil</a>
        <div className="provider-profile-stage" id="provider-profile-content" tabIndex={-1}>
          {query.isPending && <div aria-label="Cargando perfil" aria-busy="true" className="marketplace-state" role="status"><span aria-hidden="true" className="state-spinner" />Cargando perfil…</div>}
          {query.isError && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos cargar este perfil</h2>
              <p>El perfil puede no estar publicado o el servicio no está disponible. Inténtalo nuevamente.</p>
              <button className="button button-secondary" onClick={() => void query.refetch()} type="button">Reintentar</button>
            </div>
          )}
          {profile && (
            <div className="provider-profile-shell">
            <aside className="provider-profile-sidebar">
              <Link className="provider-profile-back" href="/servicios"><ArrowLeft aria-hidden="true" size={15} /> Volver a servicios</Link>
              <div className="provider-sidebar-identity">
                <span aria-hidden="true" className="provider-mark"><Truck size={23} strokeWidth={1.8} /></span>
                <p className="provider-sidebar-provider-name">{profile.providerName}</p>
              </div>
              <nav aria-label="Secciones del perfil" className="provider-profile-nav">
                {sections.map((section) => <a href={`#${section.id}`} key={section.id}>{section.label}</a>)}
              </nav>
            </aside>

            <div className="provider-profile-content">
              <nav aria-label="Secciones del perfil" className="provider-profile-mobile-nav">
                <Link href="/servicios"><ArrowLeft aria-hidden="true" size={14} /> Volver a servicios</Link>
                {sections.map((section) => <a href={`#${section.id}`} key={section.id}>{section.label}</a>)}
              </nav>

              <section aria-labelledby="provider-profile-title" className="provider-profile-hero" id="resumen">
                <div className="provider-profile-hero-copy">
                  <p className="eyebrow">PERFIL DE PRESTADOR</p>
                  <h1 id="provider-profile-title">{profile.providerName}</h1>
                  <div className="provider-profile-identity-details">
                    <span>{profile.kind === "company" ? "Empresa" : "Conductor independiente"}</span>
                    {profile.location && <span><MapPin aria-hidden="true" size={14} />{profile.location}</span>}
                  </div>
                  {profile.description && <p className="provider-profile-description">{profile.description}</p>}
                  <p className="provider-owner-name">{profile.ownerName}</p>
                  <button className="button button-primary provider-profile-hero-quote" disabled={!profile.services.length} onClick={requestQuote} type="button">Solicitar cotización</button>
                </div>
                <div aria-label="Inventario informado" className="provider-profile-metrics">
                  <div><Truck aria-hidden="true" size={19} /><strong>{profile.vehicles.length}</strong><span>{profile.vehicles.length === 1 ? "vehículo" : "vehículos"}</span></div>
                  <div><Users aria-hidden="true" size={19} /><strong>{profile.drivers.length}</strong><span>{profile.drivers.length === 1 ? "conductor" : "conductores"}</span></div>
                  <div><Package aria-hidden="true" size={19} /><strong>{profile.services.length}</strong><span>{profile.services.length === 1 ? "servicio" : "servicios"}</span></div>
                </div>
              </section>

              <section aria-labelledby="provider-vehicles-title" className="provider-profile-section" id="flota">
                <div className="provider-section-heading"><div><p className="eyebrow">FLOTA</p><h2 id="provider-vehicles-title">Vehículos informados</h2></div><span>{profile.vehicles.length} registrados</span></div>
                {profile.vehicles.length ? (
                  <ul className="provider-vehicle-grid">
                    {profile.vehicles.map((vehicle, index) => (
                      <li key={`${vehicle.brand}-${vehicle.model}-${vehicle.year ?? "n-a"}-${index}`}>
                        <span aria-hidden="true" className="provider-item-icon"><Truck size={22} /></span>
                        <strong>{vehicle.brand} {vehicle.model}</strong>
                        <small>{[vehicle.year, vehicle.maximumWeight ? `Carga máxima ${vehicle.maximumWeight} kg` : null].filter(Boolean).join(" · ") || "Sin más datos informados"}</small>
                      </li>
                    ))}
                  </ul>
                ) : <div className="provider-profile-empty"><Truck aria-hidden="true" size={19} /><p>Este prestador no ha informado vehículos.</p></div>}
              </section>

              <section aria-labelledby="provider-drivers-title" className="provider-profile-section" id="conductores">
                <div className="provider-section-heading"><div><p className="eyebrow">EQUIPO</p><h2 id="provider-drivers-title">Conductores vinculados</h2></div><span>{profile.drivers.length} informados</span></div>
                {profile.drivers.length ? (
                  <ul className="provider-driver-grid">
                    {profile.drivers.map((driver, index) => <li key={`${driver.firstName}-${driver.lastName}-${index}`}><span aria-hidden="true" className="provider-driver-avatar">{driver.firstName.charAt(0)}{driver.lastName.charAt(0)}</span><span><strong>{driver.firstName} {driver.lastName}</strong><small>Conductor vinculado al perfil</small></span></li>)}
                  </ul>
                ) : <div className="provider-profile-empty"><Users aria-hidden="true" size={19} /><p>Este prestador no ha informado conductores vinculados.</p></div>}
              </section>

              <section aria-labelledby="provider-services-title" className="provider-profile-section" id="servicios">
                <div className="provider-section-heading"><div><p className="eyebrow">SERVICIOS PUBLICADOS</p><h2 id="provider-services-title">¿Qué necesitas transportar?</h2></div><span>{profile.services.length} publicados</span></div>
                {profile.services.length ? (
                  <div className="provider-services-list">
                    {profile.services.map((service) => (
                      <article className="provider-service-item" key={service.serviceTypeId}>
                        <div><span aria-hidden="true" className="provider-item-icon"><Package size={20} /></span><h3>{service.name}</h3><p>Solicita una cotización para coordinar detalles y disponibilidad.</p></div>
                      </article>
                    ))}
                  </div>
                ) : <div className="marketplace-state marketplace-empty" role="status"><h3>No hay servicios publicados</h3><p>Este prestador todavía no ofrece servicios para solicitar.</p></div>}
              </section>
              <section aria-labelledby="provider-ratings-title" className="provider-profile-section" id="valoraciones">
                <div className="provider-section-heading"><div><p className="eyebrow">EXPERIENCIAS DE CLIENTES</p><h2 id="provider-ratings-title">Valoraciones</h2></div><span>{profile.ratings ? `${profile.ratings.ratingCount} ${profile.ratings.ratingCount === 1 ? "valoración" : "valoraciones"}` : "Datos no disponibles"}</span></div>
                {!profile.ratings ? (
                  <div className="provider-profile-empty"><p>Las valoraciones no están disponibles en este momento.</p></div>
                ) : profile.ratings.ratingCount === 0 ? (
                  <div className="provider-profile-empty"><p>Este prestador aún no tiene valoraciones.</p></div>
                ) : (
                  <>
                    <div aria-label={`${profile.ratings.ratingCount} valoraciones`} className="provider-rating-summary">
                      <strong>{profile.ratings.averageRating === null ? "Promedio no disponible" : `${formatRating(profile.ratings.averageRating)} de 5`}</strong>
                      <span>Promedio de clientes con servicios completados</span>
                    </div>
                    {profile.ratings.recent.length ? (
                      <ul className="provider-rating-list">
                        {profile.ratings.recent.map((rating, index) => (
                          <li key={`${rating.createdAt}-${rating.rating}-${index}`}>
                            <div><strong>{rating.rating} de 5</strong><time dateTime={rating.createdAt}>{formatRatingDate(rating.createdAt)}</time></div>
                            <p>{rating.comment?.trim() || "Sin comentario"}</p>
                          </li>
                        ))}
                      </ul>
                    ) : <p className="provider-rating-empty-recent">No hay comentarios recientes.</p>}
                  </>
                )}
              </section>
              <p className="marketplace-transparency">Enviar una solicitud no crea una reserva ni realiza un pago. El prestador debe responder y acordar las condiciones.</p>
            </div>
          </div>
          )}
        </div>
      </main>
      <MarketplaceFooter />
      {profile && quoteDialogOpen && <QuoteRequestDialog onClose={() => setQuoteDialogOpen(false)} open={quoteDialogOpen} profile={profile} selectedServiceId="" />}
    </>
  );
}

function formatRating(value: number) {
  return new Intl.NumberFormat("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatRatingDate(value: string) {
  return new Intl.DateTimeFormat("es-CL", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}
