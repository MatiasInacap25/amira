import { notFound } from "next/navigation";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { SimulatedCheckoutView } from "@/components/marketplace/simulated-checkout-view";

// The simulated provider exists only for development. Production builds never serve this page.
export default async function SimulatedCheckoutPage({ searchParams }: { searchParams: Promise<{ paymentId?: string; token?: string }> }) {
  if (process.env.NODE_ENV === "production") notFound();
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
