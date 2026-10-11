"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, MapPin, Package, Star, Truck, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { QuoteRequestDialog } from "@/components/marketplace/quote-request-dialog";
import { MarketplaceSkeleton, PROFILE_LAYOUT } from "@/components/marketplace/marketplace-skeleton";
import { getProviderProfile, type ProviderProfile } from "@/lib/marketplace-api";

export function ProviderProfileView({ profileId }: { profileId: string }) {
  const [quoteRequest, setQuoteRequest] = useState<{ serviceId: string } | null>(null);
  const query = useQuery({
    queryKey: ["provider-profile", profileId],
    queryFn: ({ signal }) => getProviderProfile(profileId, signal),
    retry: false,
    staleTime: 30_000,
  });

  const profile = query.data;
  const isCompany = profile?.kind === "company";
  const ratings = profile?.ratings ?? null;
  const sections = [
    { id: "servicios", label: "Servicios" },
    { id: "flota", label: "Vehículos" },
    { id: "valoraciones", label: "Valoraciones" },
    ...(isCompany ? [{ id: "conductores", label: "Conductores" }] : []),
  ];

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main provider-profile-page" id="contenido">
        <a className="skip-link" href="#provider-profile-content">Ir al perfil</a>
        <div className="provider-profile-stage" id="provider-profile-content" tabIndex={-1}>
          {query.isError && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos cargar este perfil</h2>
              <p>El perfil puede no estar publicado o el servicio no está disponible. Inténtalo nuevamente.</p>
              <button className="button button-secondary" onClick={() => void query.refetch()} type="button">Reintentar</button>
            </div>
          )}
          <MarketplaceSkeleton label="Cargando perfil…" layout={PROFILE_LAYOUT} loading={query.isPending} name="provider-profile">
          {profile && (
            <div className="provider-profile-shell">
              <aside className="provider-profile-sidebar">
                <Link className="provider-profile-back" href="/servicios"><ArrowLeft aria-hidden="true" size={15} /> Volver a servicios</Link>
                <nav aria-label="Secciones del perfil" className="provider-profile-nav">
                  {sections.map((section) => <a href={`#${section.id}`} key={section.id}>{section.label}</a>)}
                </nav>
              </aside>

              <div className="provider-profile-content">
                <nav aria-label="Secciones del perfil" className="provider-profile-mobile-nav">
                  <Link href="/servicios"><ArrowLeft aria-hidden="true" size={14} /> Volver a servicios</Link>
                  {sections.map((section) => <a href={`#${section.id}`} key={section.id}>{section.label}</a>)}
                </nav>

                <section aria-labelledby="provider-profile-title" className="provider-profile-hero">
                  <span aria-hidden="true" className="provider-avatar">{initialsOf(profile.providerName)}</span>
                  <div className="provider-profile-hero-copy">
                    <div className="provider-profile-hero-heading">
                      <h1 id="provider-profile-title">{profile.providerName}</h1>
                      <span className="provider-kind-badge">{isCompany ? "Empresa" : "Conductor independiente"}</span>
                    </div>
                    {profile.location && <p className="provider-profile-location"><MapPin aria-hidden="true" size={14} />{profile.location}</p>}
                    <RatingLine ratings={ratings} />
                    {profile.description && <p className="provider-profile-description">{profile.description}</p>}
                    <button className="button button-primary provider-profile-hero-quote" disabled={!profile.services.length} onClick={() => setQuoteRequest({ serviceId: "" })} type="button">Cotizar</button>
                    {!profile.services.length && <p className="provider-profile-quote-note">Este prestador no tiene servicios publicados para cotizar.</p>}
                  </div>
                </section>

                <section aria-labelledby="provider-services-title" className="provider-profile-section" id="servicios">
                  <h2 id="provider-services-title">Servicios</h2>
                  {profile.services.length ? (
                    <ul className="provider-services-list">
                      {profile.services.map((service) => (
                        <li className="provider-service-item" key={service.serviceTypeId}>
                          <span aria-hidden="true" className="provider-item-icon"><Package size={20} /></span>
                          <strong>{service.name}</strong>
                          <button aria-label={`Cotizar ${service.name}`} className="button button-secondary provider-service-quote" onClick={() => setQuoteRequest({ serviceId: service.serviceTypeId })} type="button">Cotizar</button>
                        </li>
                      ))}
                    </ul>
                  ) : <div className="marketplace-state marketplace-empty" role="status"><h3>No hay servicios publicados</h3><p>Este prestador todavía no ofrece servicios para solicitar.</p></div>}
                </section>

                <section aria-labelledby="provider-vehicles-title" className="provider-profile-section" id="flota">
                  <h2 id="provider-vehicles-title">Vehículos</h2>
                  {profile.vehicles.length ? (
                    <ul className="provider-vehicle-grid">
                      {profile.vehicles.map((vehicle, index) => (
                        <li className="provider-vehicle-item" key={`${vehicle.brand}-${vehicle.model}-${vehicle.year ?? "n-a"}-${index}`}>
                          <span aria-hidden="true" className="provider-item-icon"><Truck size={20} /></span>
                          <span>
                            <strong>{vehicle.brand} {vehicle.model}</strong>
                            <small>{[vehicle.year, vehicle.maximumWeight ? `Carga máxima ${vehicle.maximumWeight} kg` : null].filter(Boolean).join(" · ") || "Sin más datos informados"}</small>
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : <div className="provider-profile-empty"><Truck aria-hidden="true" size={19} /><p>Este prestador no ha informado vehículos.</p></div>}
                </section>

                <section aria-labelledby="provider-ratings-title" className="provider-profile-section" id="valoraciones">
                  <h2 id="provider-ratings-title">Valoraciones</h2>
                  {!ratings || ratings.ratingCount === 0 ? (
                    <div className="provider-profile-empty"><Star aria-hidden="true" size={19} /><p>Aún no hay valoraciones</p></div>
                  ) : (
                    <>
                      <div className="provider-rating-summary">
                        <strong>{ratings.averageRating === null ? "Promedio no disponible" : `${formatRating(ratings.averageRating)} de 5`}</strong>
                        <span>Promedio de clientes con servicios completados</span>
                      </div>
                      {ratings.recent.length ? (
                        <ul className="provider-rating-list">
                          {ratings.recent.map((rating, index) => (
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

                {isCompany && (
                  <section aria-labelledby="provider-drivers-title" className="provider-profile-section" id="conductores">
                    <h2 id="provider-drivers-title">Conductores</h2>
                    {profile.drivers.length ? (
                      <ul className="provider-driver-grid">
                        {profile.drivers.map((driver, index) => (
                          <li key={`${driver.firstName}-${driver.lastName}-${index}`}>
                            <span aria-hidden="true" className="provider-avatar provider-avatar-small">{initialsOf(`${driver.firstName} ${driver.lastName}`)}</span>
                            <span>
                              <strong>{driver.firstName} {driver.lastName}</strong>
                              {driver.isOwner && <span className="provider-owner-badge">Titular</span>}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : <div className="provider-profile-empty"><Users aria-hidden="true" size={19} /><p>Este prestador no ha informado conductores vinculados.</p></div>}
                  </section>
                )}

                <p className="marketplace-transparency">Enviar una solicitud no crea una reserva ni realiza un pago. El prestador debe responder y acordar las condiciones.</p>
              </div>
            </div>
          )}
          </MarketplaceSkeleton>
        </div>
        {profile && (
          <div className="provider-quote-bar">
            <p><strong>{profile.providerName}</strong><span>{profile.services.length} {profile.services.length === 1 ? "servicio publicado" : "servicios publicados"}</span></p>
            <button className="button button-primary" disabled={!profile.services.length} onClick={() => setQuoteRequest({ serviceId: "" })} type="button">Cotizar</button>
          </div>
        )}
      </main>
      <MarketplaceFooter />
      {profile && quoteRequest && (
        <QuoteRequestDialog
          key={quoteRequest.serviceId || "any-service"}
          onClose={() => setQuoteRequest(null)}
          open
          profile={profile}
          selectedServiceId={quoteRequest.serviceId}
        />
      )}
    </>
  );
}

function RatingLine({ ratings }: { ratings: ProviderProfile["ratings"] }) {
  if (!ratings || ratings.ratingCount === 0 || ratings.averageRating === null) {
    return <p className="provider-profile-rating-line provider-profile-rating-empty">Aún no hay valoraciones</p>;
  }
  return (
    <p className="provider-profile-rating-line">
      <Star aria-hidden="true" fill="currentColor" size={15} />
      <span><strong>{formatRating(ratings.averageRating)}</strong> de 5 · {ratings.ratingCount} {ratings.ratingCount === 1 ? "valoración" : "valoraciones"}</span>
    </p>
  );
}

function initialsOf(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  return words.slice(0, 2).map((word) => word.charAt(0).toUpperCase()).join("");
}

function formatRating(value: number) {
  return new Intl.NumberFormat("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatRatingDate(value: string) {
  return new Intl.DateTimeFormat("es-CL", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}
