import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Créditos de fotografías | Amira",
  description: "Autores y licencias de las fotografías que muestra la página de inicio de Amira.",
};

// Licensed stand-in photographs used on the landing page (src/app/page.tsx), from Wikimedia Commons.
const credits = [
  { what: "Volquete en una demolición", by: "order_242 from Chile", licence: "CC BY-SA 2.0", href: "https://commons.wikimedia.org/wiki/File:Mercedes_Benz_1525_Cab_1988_(9612382184).jpg" },
  { what: "Camión plano con carga", by: "Bmveiga", licence: "CC BY-SA 4.0", href: "https://commons.wikimedia.org/wiki/File:My_truck_makes_it_moving_here.jpg" },
  { what: "Caja de mudanza cerrada", by: "HireAHelper", licence: "CC BY 2.0", href: "https://commons.wikimedia.org/wiki/File:Large_Cardboard_Moving_Box_Taped_Closed_(32067345357).jpg" },
] as const;

export default function CreditsPage() {
  return (
    <main id="contenido" style={{ display: "grid", gap: 16, width: "min(100% - 48px, 720px)", margin: "0 auto", padding: "96px 0" }}>
      <h1>Créditos de fotografías</h1>
      <p>Las fotografías de la página de inicio provienen de Wikimedia Commons y se usan según su licencia.</p>
      <ul>
        {credits.map((credit) => (
          <li key={credit.href}>
            <a href={credit.href} rel="noreferrer" target="_blank">{credit.what}</a>: {credit.by}, {credit.licence}
          </li>
        ))}
      </ul>
      <p><Link href="/">Volver al inicio</Link></p>
    </main>
  );
}
