"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { accountApiFetch } from "@/lib/auth/account-api";
import { accountRoleLabel } from "@/lib/account-role-labels";
import { accountAccessMessage, currentAccessToken, ProviderRequestAccessError } from "@/lib/provider-request-access";
import { createClient } from "@/lib/supabase/client";

const SIGN_IN_HREF = `/login?next=${encodeURIComponent("/cuenta/perfil")}`;
const MISSING_VALUE = "No registrado";

type ProfileData = { email: string; phone: string; role: string | null };

// Reads the session user for contact data and the backend account for the role. Throws the typed access error when signed out.
async function fetchProfile(): Promise<ProfileData> {
  const token = await currentAccessToken();
  const { data, error } = await createClient().auth.getUser();
  if (error || !data.user) throw new Error("No pudimos verificar tu sesión.");

  const response = await accountApiFetch("/api/account/me", token, process.env.NEXT_PUBLIC_API_URL);
  if (!response.ok) throw new Error("No pudimos cargar tu perfil.");
  const body = await response.json() as { role?: string | null };

  return { email: data.user.email ?? "", phone: data.user.phone ?? "", role: body.role ?? null };
}

export default function ProfileSettingsPage() {
  const profileQuery = useQuery({
    queryKey: ["account-profile"],
    queryFn: fetchProfile,
    retry: false,
    staleTime: 60_000,
  });

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main customer-services-page" id="contenido">
        <div className="customer-services-wrap">
          <h1>Configuración del perfil</h1>
          {profileQuery.isPending && <p role="status">Cargando tu perfil…</p>}
          {profileQuery.error instanceof ProviderRequestAccessError && (
            <div className="marketplace-state">
              <p role="alert">{accountAccessMessage(profileQuery.error.reason, "profile")}</p>
              <Link className="button button-primary" href={SIGN_IN_HREF}>Iniciar sesión</Link>
            </div>
          )}
          {profileQuery.isError && !(profileQuery.error instanceof ProviderRequestAccessError) && (
            <div className="marketplace-state marketplace-error" role="alert">
              <p>No pudimos cargar tu perfil. Inténtalo nuevamente.</p>
              <button className="button button-secondary" onClick={() => void profileQuery.refetch()} type="button">Reintentar</button>
            </div>
          )}
          {profileQuery.isSuccess && (
            <dl>
              <dt>Correo</dt>
              <dd>{profileQuery.data.email || MISSING_VALUE}</dd>
              <dt>Teléfono</dt>
              <dd>{profileQuery.data.phone || MISSING_VALUE}</dd>
              <dt>Tipo de cuenta</dt>
              <dd>{accountRoleLabel(profileQuery.data.role)}</dd>
            </dl>
          )}
        </div>
      </main>
      <MarketplaceFooter />
    </>
  );
}
