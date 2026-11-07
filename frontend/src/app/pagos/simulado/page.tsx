import { notFound } from "next/navigation";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { SimulatedCheckoutView } from "@/components/marketplace/simulated-checkout-view";
import { isDevelopmentAppEnv } from "@/lib/auth/dev-mfa";

// The simulated provider exists only for development. It is served only when NEXT_PUBLIC_APP_ENV is in the
// dev allowlist (development, local, test); any other or unset value stays 404.
// NEXT_PUBLIC_APP_ENV is read as a literal so Next.js inlines it at build time.
export default async function SimulatedCheckoutPage({ searchParams }: { searchParams: Promise<{ paymentId?: string; token?: string }> }) {
  if (!isDevelopmentAppEnv(process.env.NEXT_PUBLIC_APP_ENV)) notFound();
  const { paymentId = "", token = "" } = await searchParams;
  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main chat-page" id="contenido">
        <SimulatedCheckoutView paymentId={paymentId} token={token} />
      </main>
      <MarketplaceFooter />
    </>
  );
}
