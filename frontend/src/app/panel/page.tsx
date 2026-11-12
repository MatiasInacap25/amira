"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { ProviderServicesBody } from "@/components/marketplace/provider-services-view";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { accountApiFetch } from "@/lib/auth/account-api";
import { accountAccessMessage, currentAccessToken, ProviderRequestAccessError } from "@/lib/provider-request-access";

const SIGN_IN_HREF = `/login?next=${encodeURIComponent("/panel")}`;

// Reads the account role from the backend. Throws the typed access error when signed out.
async function fetchPanelRole(): Promise<string | null> {
  const token = await currentAccessToken();
  const response = await accountApiFetch("/api/account/me", token, process.env.NEXT_PUBLIC_API_URL);
  if (!response.ok) throw new Error("No pudimos cargar tu cuenta.");
  const body = await response.json() as { role?: string | null };
  return body.role ?? null;
}

function PanelShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main lp-app customer-services-page" id="contenido">
        <div className="customer-services-wrap">
          <h1>Panel del proveedor</h1>
          {children}
        </div>
      </main>
      <MarketplaceFooter />
    </>
  );
}

// Role decides the dashboard: providers get action buttons, company drivers see their assigned services, clients go to /servicios.
export default function PanelPage() {
  const router = useRouter();
  const roleQuery = useQuery({
    queryKey: ["panel-account-role"],
    queryFn: fetchPanelRole,
    retry: false,
    staleTime: 60_000,
  });
  const role = roleQuery.data;

  useEffect(() => {
    if (role === "client") router.replace("/servicios");
  }, [role, router]);

  if (roleQuery.isPending) {
    return <PanelShell><p role="status">Cargando tu panel…</p></PanelShell>;
  }

  if (roleQuery.error instanceof ProviderRequestAccessError) {
    return (
      <PanelShell>
        <div className="marketplace-state">
          <p role="alert">{accountAccessMessage(roleQuery.error.reason, "panel")}</p>
          <Link className="button button-primary" href={SIGN_IN_HREF}>Iniciar sesión</Link>
        </div>
      </PanelShell>
    );
  }

  if (roleQuery.isError) {
    return (
      <PanelShell>
        <div className="marketplace-state marketplace-error" role="alert">
          <p>No pudimos cargar tu panel. Inténtalo nuevamente.</p>
          <button className="button button-secondary" onClick={() => void roleQuery.refetch()} type="button">Reintentar</button>
        </div>
      </PanelShell>
    );
  }

  if (role === "client") {
    return <PanelShell><p role="status">Redirigiendo a tus servicios…</p></PanelShell>;
  }

  if (role === "company_driver") {
    return (
      <PanelShell>
        <nav aria-label="Acciones del conductor">
          <ul className="panel-action-list">
            <li><Link className="panel-action" href="/cuenta/perfil">Mi perfil <ArrowRight aria-hidden="true" size={16} /></Link></li>
          </ul>
        </nav>
        <ProviderServicesBody />
      </PanelShell>
    );
  }

  if (role === "independent_driver" || role === "company_owner") {
    return (
      <PanelShell>
        <nav aria-label="Acciones del proveedor">
          <ul className="panel-action-list">
            <li><Link className="panel-action" href="/mensajes">Mensajes <ArrowRight aria-hidden="true" size={16} /></Link></li>
            <li><Link className="panel-action" href="/cuenta/servicios">Servicios <ArrowRight aria-hidden="true" size={16} /></Link></li>
            <li><Link className="panel-action" href="/cuenta/vehiculos">Vehículos <ArrowRight aria-hidden="true" size={16} /></Link></li>
            <li><Link className="panel-action" href="/cuenta/viajes-compartidos">Viajes compartidos <ArrowRight aria-hidden="true" size={16} /></Link></li>
            <li><Link className="panel-action" href="/cuenta/perfil">Configuración del perfil <ArrowRight aria-hidden="true" size={16} /></Link></li>
            {role === "company_owner" && (
              <li><Link className="panel-action" href="/cuenta/invitaciones">Invitaciones <ArrowRight aria-hidden="true" size={16} /></Link></li>
            )}
          </ul>
        </nav>
      </PanelShell>
    );
  }

  return (
    <PanelShell>
      <div className="marketplace-state marketplace-empty" role="status">
        <p>Tu tipo de cuenta no tiene un panel disponible.</p>
      </div>
    </PanelShell>
  );
}
