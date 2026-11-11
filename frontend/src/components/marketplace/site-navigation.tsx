"use client";

import { ArrowRight, Menu, Truck, X } from "lucide-react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { geist } from "@/app/fonts";
import { ChatNotifications } from "@/components/marketplace/chat-notifications";
import { LpMark } from "@/components/marketplace/lp-mark";
import { ProfileMenu, useSignOut } from "@/components/marketplace/profile-menu";
import { useChatEvents } from "@/components/marketplace/use-chat-events";
import { CHAT_ROOT_KEY, chatUnreadTotalKey } from "@/lib/chats";
import { chatRefetchInterval } from "@/lib/chat-quotations";
import { formatUnreadBadge, unreadAccessibleLabel } from "@/lib/chat-unread";
import { shouldClearCustomerCache } from "@/lib/customer-cache-policy";
import { accountApiFetch } from "@/lib/auth/account-api";
import { getChatUnreadTotal, getProviderRequests } from "@/lib/marketplace-api";
import {
  PROVIDER_NAV_USER_KEY,
  providerNavPendingKey,
  providerNavRoleKey,
  providerNavStaleKeys,
} from "@/lib/provider-nav-cache";
import { currentAccessToken } from "@/lib/provider-request-access";
import { isProviderRole, pendingBadgeLabel } from "@/lib/provider-requests";
import { clearAccountScopedQueries } from "@/lib/service-query-keys";
import { createClient } from "@/lib/supabase/client";

type NavAccount = { userId: string | null };

// Drops the header's per-account data (provider and chat queries) on sign-out or account change, and re-reads the session user.
export function useProviderNavAccountScope() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const { data } = createClient().auth.onAuthStateChange((event, session) => {
      if (event === "INITIAL_SESSION") return;
      const cachedUserId = queryClient.getQueryData<NavAccount>(PROVIDER_NAV_USER_KEY)?.userId ?? undefined;
      if (shouldClearCustomerCache(event, cachedUserId, session?.user.id)) {
        for (const key of providerNavStaleKeys()) queryClient.removeQueries({ queryKey: key });
        queryClient.removeQueries({ queryKey: CHAT_ROOT_KEY });
        clearAccountScopedQueries(queryClient);
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

// Shown to every signed-in account, customers and providers alike. The badge carries the caller's total unread chats.
function ChatsLink({ className, onNavigate }: { className?: string; onNavigate?: () => void }) {
  const { userId } = useNavUserId();
  const streamConnected = useChatEvents(userId);

  const unreadQuery = useQuery({
    queryKey: chatUnreadTotalKey(userId ?? ""),
    queryFn: async () => (await getChatUnreadTotal(await currentAccessToken())).total,
    enabled: Boolean(userId),
    retry: false,
    refetchInterval: chatRefetchInterval(streamConnected),
  });

  if (!userId) return null;
  const total = unreadQuery.data ?? 0;
  const badge = formatUnreadBadge(total);
  return (
    <Link className={className} href="/mensajes" onClick={onNavigate}>
      Mensajes
      {badge && <span aria-label={unreadAccessibleLabel(total)} className="nav-badge">{badge}</span>}
    </Link>
  );
}

// Role of the signed-in account, shared by every header link that depends on it. Null while unknown and for anonymous visitors.
export function useNavAccountRole(): string | null {
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
  return roleQuery.data ?? null;
}

// Roles that work in the provider and company panel. Their header drops the public search links.
// Kept in sync with DASHBOARD_ROLES in lib/post-login-path.ts; company_driver is included here on purpose.
const PANEL_NAV_ROLES = new Set(["independent_driver", "company_owner", "company_driver"]);

export function usesPanelNavigation(role: string | null): boolean {
  return role !== null && PANEL_NAV_ROLES.has(role);
}

// Shown only to provider accounts with an active session; anonymous and client visitors get nothing.
function ProviderRequestsLink({ className, onNavigate }: { className?: string; onNavigate?: () => void }) {
  const { userId } = useNavUserId();
  const role = useNavAccountRole();
  const provider = isProviderRole(role);

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

// variant "lp": the taste-skill look (styles in src/styles/lp-app.css), opted into by the redesigned pages only.
type NavigationVariant = "default" | "lp";

function BrandLabel({ variant, size }: { variant: NavigationVariant; size: number }) {
  if (variant === "lp") return <><LpMark /><span>amira</span></>;
  return (
    <>
      <span className="brand-mark"><Truck aria-hidden="true" size={size} strokeWidth={2.2} /></span>
      <span>amira<span className="brand-period">.</span></span>
    </>
  );
}

export function MarketplaceHeader({ variant = "default" }: { variant?: NavigationVariant } = {}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { userId, pending } = useNavUserId();
  const { signOut, signingOut, error: signOutError } = useSignOut(() => setMenuOpen(false));
  useProviderNavAccountScope();
  const panelNav = usesPanelNavigation(useNavAccountRole());
  // Hidden links wait for a confirmed panel role, so anonymous visitors and customers never see them flicker out.

  return (
    <header className={variant === "lp" ? `site-header lp-app-header ${geist.variable}` : "site-header"}>
      <ChatNotifications userId={userId} />
      <div className="header-inner">
        <Link aria-label="Amira, inicio" className="brand" href="/">
          <BrandLabel size={20} variant={variant} />
        </Link>
        <nav aria-label="Navegación principal" className="desktop-nav">
          {!panelNav && <Link className="button button-secondary header-nav-button" href="/servicios">Buscar servicios</Link>}
          {!panelNav && <Link className="button button-secondary header-nav-button" href="/rutas-compartidas">Rutas compartidas</Link>}
          <ChatsLink />
          <ProviderRequestsLink />
          <Link href="/cuenta/servicios">Mis servicios</Link>
          {!panelNav && <Link href="/#como-funciona">Cómo funciona</Link>}
        </nav>
        <div className="header-actions">
          {!pending && (userId ? (
            <ProfileMenu />
          ) : (
            <div className="header-auth-links">
              <Link className="login-link" href="/login">Iniciar sesión</Link>
              <Link className="button button-secondary header-nav-button" href="/registro">Crear cuenta</Link>
            </div>
          ))}
          {!panelNav && <Link className="button button-primary header-cta" href="/servicios">Buscar un servicio <ArrowRight aria-hidden="true" size={16} /></Link>}
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
          {!panelNav && <Link className="header-nav-button" href="/servicios" onClick={() => setMenuOpen(false)}>Buscar servicios</Link>}
          {!panelNav && <Link className="header-nav-button" href="/rutas-compartidas" onClick={() => setMenuOpen(false)}>Rutas compartidas</Link>}
          <ChatsLink className="header-nav-button" onNavigate={() => setMenuOpen(false)} />
          <ProviderRequestsLink className="header-nav-button" onNavigate={() => setMenuOpen(false)} />
          <Link className="header-nav-button" href="/cuenta/servicios" onClick={() => setMenuOpen(false)}>Mis servicios</Link>
          {!pending && (userId ? (
            <>
              <Link className="header-nav-button" href="/cuenta/perfil" onClick={() => setMenuOpen(false)}>Configuración del perfil</Link>
              <button className="header-nav-button" disabled={signingOut} onClick={signOut} type="button">
                {signingOut ? "Cerrando sesión…" : "Cerrar sesión"}
              </button>
              {signOutError && <p className="profile-menu-error" role="alert">{signOutError}</p>}
            </>
          ) : (
            <>
              <Link className="header-nav-button" href="/login" onClick={() => setMenuOpen(false)}>Iniciar sesión</Link>
              <Link className="header-nav-button" href="/registro" onClick={() => setMenuOpen(false)}>Crear cuenta</Link>
            </>
          ))}
          {!panelNav && <Link href="/#como-funciona" onClick={() => setMenuOpen(false)}>Cómo funciona</Link>}
        </nav>
      )}
    </header>
  );
}

export function MarketplaceFooter({ variant = "default" }: { variant?: NavigationVariant } = {}) {
  return (
    <footer className={variant === "lp" ? `marketplace-footer lp-app-footer ${geist.variable}` : "marketplace-footer"}>
      <div className="marketplace-footer-inner">
        <Link aria-label="Amira, inicio" className="brand" href="/">
          <BrandLabel size={18} variant={variant} />
        </Link>
        <p>Amira no procesa pagos ni confirma reservas. Coordina las condiciones directamente con el prestador.</p>
        <Link className="text-link" href="/">Volver al inicio <ArrowRight aria-hidden="true" size={15} /></Link>
      </div>
    </footer>
  );
}
