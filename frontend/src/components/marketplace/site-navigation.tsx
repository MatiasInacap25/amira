"use client";

import { ArrowRight, Menu, Truck, X } from "lucide-react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { CHAT_ROOT_KEY } from "@/lib/chats";
import { shouldClearCustomerCache } from "@/lib/customer-cache-policy";
import { accountApiFetch } from "@/lib/auth/account-api";
import { getProviderRequests } from "@/lib/marketplace-api";
import {
  PROVIDER_NAV_USER_KEY,
  providerNavPendingKey,
  providerNavRoleKey,
  providerNavStaleKeys,
} from "@/lib/provider-nav-cache";
import { currentAccessToken } from "@/lib/provider-request-access";
import { isProviderRole, pendingBadgeLabel } from "@/lib/provider-requests";
import { ACCOUNT_ROLE_KEY } from "@/lib/service-query-keys";
import { createClient } from "@/lib/supabase/client";

type NavAccount = { userId: string | null };

// Drops the header's per-account data (provider and chat queries) on sign-out or account change, and re-reads the session user.
function useProviderNavAccountScope() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const { data } = createClient().auth.onAuthStateChange((event, session) => {
      if (event === "INITIAL_SESSION") return;
      const cachedUserId = queryClient.getQueryData<NavAccount>(PROVIDER_NAV_USER_KEY)?.userId ?? undefined;
      if (shouldClearCustomerCache(event, cachedUserId, session?.user.id)) {
        for (const key of providerNavStaleKeys()) queryClient.removeQueries({ queryKey: key });
        queryClient.removeQueries({ queryKey: CHAT_ROOT_KEY });
        // The "Mis servicios" role decides which list an account may see, so it never outlives the account.
        queryClient.removeQueries({ queryKey: ACCOUNT_ROLE_KEY });
      }
      void queryClient.invalidateQueries({ queryKey: PROVIDER_NAV_USER_KEY });
    });
    return () => data.subscription.unsubscribe();
  }, [queryClient]);
}

// The signed-in user id shared by the header and the chat views; userId is null for anonymous visitors.
export function useNavUserId(): { userId: string | null; pending: boolean } {
  const userQuery = useQuery({
    queryKey: PROVIDER_NAV_USER_KEY,
    queryFn: async (): Promise<NavAccount> => {
      const { data } = await createClient().auth.getSession();
      return { userId: data.session?.user.id ?? null };
    },
    retry: false,
    staleTime: 0,
  });
  return { userId: userQuery.data?.userId ?? null, pending: userQuery.isPending };
}

// Shown to every signed-in account, customers and providers alike.
function ChatsLink({ className, onNavigate }: { className?: string; onNavigate?: () => void }) {
  const { userId } = useNavUserId();
  if (!userId) return null;
  return (
    <Link className={className} href="/mensajes" onClick={onNavigate}>
      Mensajes
    </Link>
  );
}

// Shown only to provider accounts with an active session; anonymous and client visitors get nothing.
function ProviderRequestsLink({ className, onNavigate }: { className?: string; onNavigate?: () => void }) {
  const { userId } = useNavUserId();

  const roleQuery = useQuery({
    queryKey: providerNavRoleKey(userId ?? ""),
    queryFn: async () => {
      const response = await accountApiFetch("/api/account/me", await currentAccessToken(), process.env.NEXT_PUBLIC_API_URL);
      if (!response.ok) return null;
      const body = await response.json() as { role?: string };
      return body.role ?? null;
    },
    enabled: Boolean(userId),
    retry: false,
    staleTime: 60_000,
  });
  const provider = isProviderRole(roleQuery.data);

  const pendingQuery = useQuery({
    queryKey: providerNavPendingKey(userId ?? ""),
    queryFn: async () => {
      const page = await getProviderRequests(await currentAccessToken(), { status: "pending", limit: 1, offset: 0 });
      return page.counts.pending;
    },
    enabled: provider && Boolean(userId),
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
  useProviderNavAccountScope();

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
          <ChatsLink />
          <ProviderRequestsLink />
          <Link href="/cuenta/servicios">Mis servicios</Link>
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
          <ChatsLink className="header-nav-button" onNavigate={() => setMenuOpen(false)} />
          <ProviderRequestsLink className="header-nav-button" onNavigate={() => setMenuOpen(false)} />
          <Link className="header-nav-button" href="/cuenta/servicios" onClick={() => setMenuOpen(false)}>Mis servicios</Link>
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
