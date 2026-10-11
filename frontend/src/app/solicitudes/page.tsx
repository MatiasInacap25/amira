import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { ProviderRequestInbox } from "@/components/marketplace/provider-request-inbox";

export default function ProviderRequestsPage() {
  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main provider-inbox-page" id="contenido">
        <a className="skip-link" href="#provider-inbox-title">Ir a las solicitudes</a>
        <ProviderRequestInbox />
      </main>
      <MarketplaceFooter />
    </>
  );
}
