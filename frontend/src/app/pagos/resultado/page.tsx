import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { PaymentResultView } from "@/components/marketplace/payment-result-view";

export default async function PaymentResultPage({ searchParams }: { searchParams: Promise<{ paymentId?: string; status?: string }> }) {
  const { paymentId = "", status } = await searchParams;
  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main chat-page" id="contenido">
        <PaymentResultView paymentId={paymentId} status={status} />
      </main>
      <MarketplaceFooter />
    </>
  );
}
