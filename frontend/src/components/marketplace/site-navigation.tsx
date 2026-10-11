"use client";

import { ArrowRight, Menu, Truck, X } from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { accountApiFetch } from "@/lib/auth/account-api";
import { getProviderRequests } from "@/lib/marketplace-api";
import { currentAccessToken } from "@/lib/provider-request-access";
import { isProviderRole, pendingBadgeLabel } from "@/lib/provider-requests";
import { createClient } from "@/lib/supabase/client";

// Shown only to provider accounts with an active session; anonymous and client visitors get nothing.
function ProviderRequestsLink({ className, onNavigate }: { className?: string; onNavigate?: () => void }) {
  const roleQuery = useQuery({
    queryKey: ["provider-nav-role"],
    queryFn: async () => {
      const { data: session } = await createClient().auth.getSession();
      if (!session.session) return null;
      const response = await accountApiFetch("/api/account/me", await currentAccessToken(), process.env.NEXT_PUBLIC_API_URL);
      if (!response.ok) return null;
      const body = await response.json() as { role?: string };
      return body.role ?? null;
    },
    retry: false,
    staleTime: 5 * 60_000,
  });
  const provider = isProviderRole(roleQuery.data);

  const pendingQuery = useQuery({
    queryKey: ["provider-nav-pending"],
    queryFn: async () => {
      const page = await getProviderRequests(await currentAccessToken(), { status: "pending", limit: 1, offset: 0 });
      return page.counts.pending;
    },
    enabled: provider,
    retry: false,
    staleTime: 60_000,
  });

  if (!provider) return null;
  const pending = pendingQuery.data ?? 0;
  const badge = pendingBadgeLabel(pending);
  return (
    <Link className={className} href="/solicitudes" onClick={onNavigate}>
      Mis solicitudes
      {badge && <span aria-label={`${pending} pendientes`} className="nav-badge">{badge}</span>}
    </Link>
  );
}

export function MarketplaceHeader() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="site-header">
      <div className="header-inner">
        <Link aria-label="Amira, inicio" className="brand" href="/">
          <span className="brand-mark"><Truck aria-hidden="true" size={20} strokeWidth={2.2} /></span>
          <span>amira<span className="brand-period">.</span></span>
        </Link>
        <nav aria-label="Navegación principal" className="desktop-nav">
          <Link className="button button-secondary header-nav-button" href="/servicios">Buscar servicios</Link>
          <Link className="button button-secondary header-nav-button" href="/rutas-compartidas">Rutas compartidas</Link>
          <ProviderRequestsLink />
          <Link href="/cuenta/servicios">Valorar servicios</Link>
          <Link href="/#como-funciona">Cómo funciona</Link>
        </nav>
        <div className="header-actions">
          <div className="header-auth-links">
            <Link className="login-link" href="/login">Iniciar sesión</Link>
            <Link className="button button-secondary header-nav-button" href="/registro">Crear cuenta</Link>
          </div>
          <Link className="button button-primary header-cta" href="/servicios">Buscar un servicio <ArrowRight aria-hidden="true" size={16} /></Link>
          <button
            aria-controls="marketplace-mobile-navigation"
            aria-expanded={menuOpen}
            aria-label={menuOpen ? "Cerrar menú" : "Abrir menú"}
            className="mobile-menu-toggle"
            onClick={() => setMenuOpen((open) => !open)}
            type="button"
          >
            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </div>
      {menuOpen && (
        <nav aria-label="Navegación móvil" className="mobile-nav" id="marketplace-mobile-navigation">
          <Link className="header-nav-button" href="/servicios" onClick={() => setMenuOpen(false)}>Buscar servicios</Link>
          <Link className="header-nav-button" href="/rutas-compartidas" onClick={() => setMenuOpen(false)}>Rutas compartidas</Link>
          <ProviderRequestsLink className="header-nav-button" onNavigate={() => setMenuOpen(false)} />
          <Link className="header-nav-button" href="/cuenta/servicios" onClick={() => setMenuOpen(false)}>Valorar servicios</Link>
          <Link className="header-nav-button" href="/login" onClick={() => setMenuOpen(false)}>Iniciar sesión</Link>
          <Link className="header-nav-button" href="/registro" onClick={() => setMenuOpen(false)}>Crear cuenta</Link>
          <Link href="/#como-funciona" onClick={() => setMenuOpen(false)}>Cómo funciona</Link>
        </nav>
      )}
    </header>
  );
}

export function MarketplaceFooter() {
  return (
    <footer className="marketplace-footer">
      <div className="marketplace-footer-inner">
        <Link aria-label="Amira, inicio" className="brand" href="/">
          <span className="brand-mark"><Truck aria-hidden="true" size={18} strokeWidth={2.2} /></span>
          <span>amira<span className="brand-period">.</span></span>
        </Link>
        <p>Amira no procesa pagos ni confirma reservas. Coordina las condiciones directamente con el prestador.</p>
        <Link className="text-link" href="/">Volver al inicio <ArrowRight aria-hidden="true" size={15} /></Link>
      </div>
    </footer>
  );
}
