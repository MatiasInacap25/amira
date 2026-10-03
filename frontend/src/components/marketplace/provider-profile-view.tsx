"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, MapPin, Truck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { QuoteRequestDialog } from "@/components/marketplace/quote-request-dialog";
import { getProviderProfile } from "@/lib/marketplace-api";

export function ProviderProfileView({ profileId }: { profileId: string }) {
  const [quoteDialogOpen, setQuoteDialogOpen] = useState(false);
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const query = useQuery({
    queryKey: ["provider-profile", profileId],
    queryFn: ({ signal }) => getProviderProfile(profileId, signal),
    retry: false,
    staleTime: 30_000,
  });

  function requestQuote(serviceTypeId: string) {
    setSelectedServiceId(serviceTypeId);
    setQuoteDialogOpen(true);
  }

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main provider-profile-page" id="contenido">
        <a className="skip-link" href="#provider-profile-content">Ir al perfil</a>
        <section aria-labelledby="provider-profile-title" className="marketplace-hero provider-profile-hero">
          <div className="marketplace-hero-inner">
            <p className="eyebrow"><span className="eyebrow-dot" /> PERFIL DE PRESTADOR</p>
            <h1 id="provider-profile-title">{query.data?.providerName ?? "Información del prestador"}</h1>
            <p>Conoce los servicios publicados y envía una solicitud para conversar condiciones con el prestador.</p>
            <Link className="marketplace-back-link" href="/servicios"><ArrowLeft aria-hidden="true" size={16} /> Volver a servicios</Link>
          </div>
        </section>

        <div className="marketplace-content" id="provider-profile-content">
          {query.isPending && <div aria-label="Cargando perfil" aria-busy="true" className="marketplace-state" role="status"><span aria-hidden="true" className="state-spinner" />Cargando perfil…</div>}
          {query.isError && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos cargar este perfil</h2>
              <p>El perfil puede no estar publicado o el servicio no está disponible. Inténtalo nuevamente.</p>
              <button className="button button-secondary" onClick={() => void query.refetch()} type="button">Reintentar</button>
            </div>
          )}
          {query.data && (
            <div className="provider-profile-layout">
              <section aria-labelledby="provider-about-title" className="provider-profile-card">
                <div className="provider-profile-heading">
                  <span aria-hidden="true" className="provider-mark"><Truck size={23} strokeWidth={1.8} /></span>
                  <div><p className="eyebrow">{query.data.kind === "company" ? "EMPRESA" : "CONDUCTOR INDEPENDIENTE"}</p><h2 id="provider-about-title">{query.data.providerName}</h2></div>
                </div>
                {query.data.description && <p className="provider-profile-description">{query.data.description}</p>}
                {query.data.location && <p className="provider-profile-location"><MapPin aria-hidden="true" size={16} />{query.data.location}</p>}
                <p className="provider-owner-name"><span>Responsable del perfil</span>{query.data.ownerName}</p>
                {query.data.drivers.length > 0 && (
                  <div className="provider-team">
                    <h3>Conductores vinculados</h3>
                    <ul>{query.data.drivers.map((driver) => <li key={`${driver.firstName}-${driver.lastName}`}>{driver.firstName} {driver.lastName}</li>)}</ul>
                  </div>
                )}
              </section>

              <section aria-labelledby="provider-services-title" className="provider-profile-section">
                <div className="provider-section-heading"><p className="eyebrow">SERVICIOS PUBLICADOS</p><h2 id="provider-services-title">¿Qué necesitas transportar?</h2></div>
                {query.data.services.length === 0 ? (
                  <div className="marketplace-state marketplace-empty" role="status"><h3>No hay servicios publicados</h3><p>Este prestador todavía no ofrece servicios para solicitar.</p></div>
                ) : (
                  <div className="provider-services-list">
                    {query.data.services.map((service) => (
                      <article className="provider-service-item" key={service.serviceTypeId}>
                        <div><h3>{service.name}</h3><p>Solicita una cotización para coordinar detalles y disponibilidad.</p></div>
                        <button className="button button-primary" onClick={() => requestQuote(service.serviceTypeId)} type="button">Solicitar cotización</button>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              {query.data.vehicles.length > 0 && (
                <section aria-labelledby="provider-vehicles-title" className="provider-profile-section provider-vehicles-section">
                  <div className="provider-section-heading"><p className="eyebrow">FLOTA</p><h2 id="provider-vehicles-title">Vehículos informados</h2></div>
                  <ul className="provider-vehicle-list">
                    {query.data.vehicles.map((vehicle, index) => (
                      <li key={`${vehicle.brand}-${vehicle.model}-${vehicle.year ?? "n-a"}-${index}`}>
                        <Truck aria-hidden="true" size={20} />
                        <span><strong>{vehicle.brand} {vehicle.model}</strong><small>{[vehicle.year, vehicle.maximumWeight ? `Carga máxima ${vehicle.maximumWeight} kg` : null].filter(Boolean).join(" · ") || "Datos del vehículo"}</small></span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}
          <p className="marketplace-transparency">Enviar una solicitud no crea una reserva ni realiza un pago. El prestador debe responder y acordar las condiciones.</p>
        </div>
      </main>
      <MarketplaceFooter />
      {query.data && quoteDialogOpen && (
        <QuoteRequestDialog
          onClose={() => setQuoteDialogOpen(false)}
          open={quoteDialogOpen}
          profile={query.data}
          selectedServiceId={selectedServiceId}
        />
      )}
    </>
  );
}
