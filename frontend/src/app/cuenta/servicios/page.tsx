"use client";

import { CustomerServicesView } from "@/components/marketplace/customer-services-view";
import { MarketplaceSkeleton, CUSTOMER_SERVICES_LAYOUT } from "@/components/marketplace/marketplace-skeleton";
import { ProviderServicesView } from "@/components/marketplace/provider-services-view";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { useServiceAccountRole } from "@/components/marketplace/service-detail-view";

// Picks the list by account role. While the role is unknown nothing is fetched, so a provider never sees the customer list.
// A failed role lookup falls back to the customer view, which reports its own sign-in and error states.
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

  return roleQuery.data?.provider ? <ProviderServicesView /> : <CustomerServicesView />;
}
