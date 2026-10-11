"use client";

import Link from "next/link";
import { CustomerServicesView } from "@/components/marketplace/customer-services-view";
import { MarketplaceSkeleton, CUSTOMER_SERVICES_LAYOUT } from "@/components/marketplace/marketplace-skeleton";
import { ProviderServicesView } from "@/components/marketplace/provider-services-view";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { useServiceAccountRole } from "@/components/marketplace/service-detail-view";
import { CustomerSessionError } from "@/lib/customer-session";

const SIGN_IN_HREF = "/login?next=%2Fcuenta%2Fservicios";

// Picks the list by account role. While the role is unknown nothing is fetched, so a provider never sees the customer list.
// A failed role lookup shows an error with a retry, never the customer list, because the role decides which list is correct.
export default function CustomerServicesPage() {
  const roleQuery = useServiceAccountRole();

  if (roleQuery.isPending) {
    return (
      <>
        <MarketplaceHeader />
        <main className="marketplace-main customer-services-page" id="contenido">
          <div className="customer-services-wrap">
            <h1>Mis servicios</h1>
            <MarketplaceSkeleton label="Cargando tus servicios…" layout={CUSTOMER_SERVICES_LAYOUT} loading name="services-account">
              {null}
            </MarketplaceSkeleton>
          </div>
        </main>
        <MarketplaceFooter />
      </>
    );
  }

  if (roleQuery.isError) {
    const needsSignIn = roleQuery.error instanceof CustomerSessionError;
    return (
      <>
        <MarketplaceHeader />
        <main className="marketplace-main customer-services-page" id="contenido">
          <div className="customer-services-wrap">
            <h1>Mis servicios</h1>
            {needsSignIn ? (
              <div className="marketplace-state marketplace-error" role="alert">
                <h2>No pudimos verificar tu sesión</h2>
                <p>Inicia sesión de nuevo para ver tus servicios.</p>
                <Link className="button button-secondary" href={SIGN_IN_HREF}>Iniciar sesión</Link>
              </div>
            ) : (
              <div className="marketplace-state marketplace-error" role="alert">
                <h2>No pudimos cargar tus servicios</h2>
                <p>Inténtalo nuevamente en unos minutos.</p>
                <button className="button button-secondary" onClick={() => void roleQuery.refetch()} type="button">
                  Reintentar
                </button>
              </div>
            )}
          </div>
        </main>
        <MarketplaceFooter />
      </>
    );
  }

  return roleQuery.data?.provider ? <ProviderServicesView /> : <CustomerServicesView />;
}
