import type { Metadata } from "next";
import Link from "next/link";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";

export const metadata: Metadata = {
  title: "Página no encontrada | Amira",
};

export default function NotFound() {
  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main" id="contenido">
        <section className="marketplace-state not-found-state">
          <h1>Página no encontrada</h1>
          <p>La página que buscas no existe o fue movida.</p>
          <div className="not-found-actions">
            <Link className="button button-primary" href="/">
              Volver al inicio
            </Link>
            <Link className="button button-secondary" href="/servicios">
              Buscar servicios
            </Link>
          </div>
        </section>
      </main>
      <MarketplaceFooter />
    </>
  );
}
