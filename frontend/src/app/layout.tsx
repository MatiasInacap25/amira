import type { Metadata } from "next";
import "./globals.css";
import "@/styles/lp-tokens.css";
import "@/styles/lp-app.css";
import "@/styles/lp-pages.css";
import { geist } from "./fonts";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "Amira | Transporte para cada carga",
  description:
    "Conecta con conductores independientes y empresas de transporte para mudanzas, fletes y carga en Chile.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className={`h-full antialiased ${geist.variable}`}>
      <body className="flex min-h-full flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
