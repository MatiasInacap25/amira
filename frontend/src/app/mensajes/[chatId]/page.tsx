import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";

export default async function MessagePlaceholderPage({ params }: { params: Promise<{ chatId: string }> }) {
  const { chatId } = await params;
  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main provider-inbox-page" id="contenido">
        <section aria-labelledby="chat-placeholder-title" className="chat-placeholder">
          <p className="eyebrow">CONVERSACIÓN</p>
          <h1 id="chat-placeholder-title">El chat está listo para continuar</h1>
          <p>La solicitud fue aceptada. La mensajería estará disponible en una próxima actualización.</p>
          <p className="chat-placeholder-id">Referencia: {chatId}</p>
          <Link className="button button-secondary" href="/solicitudes"><ArrowLeft aria-hidden="true" size={16} /> Volver a solicitudes</Link>
        </section>
      </main>
      <MarketplaceFooter />
    </>
  );
}
