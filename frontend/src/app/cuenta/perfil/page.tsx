"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhoneChangeForm } from "@/components/account/phone-change-form";
import { ProviderProfileForm } from "@/components/account/provider-profile-form";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { accountApiFetch } from "@/lib/auth/account-api";
import { accountAccessMessage, currentAccessToken, ProviderRequestAccessError } from "@/lib/provider-request-access";
import { createClient } from "@/lib/supabase/client";

const SIGN_IN_HREF = `/login?next=${encodeURIComponent("/cuenta/perfil")}`;
const MISSING_VALUE = "No registrado";
// Clients and company drivers keep the read-only view; only these roles own a public profile.
const PROVIDER_ROLES = new Set(["independent_driver", "company_owner"]);

type ProfileData = {
  email: string;
  phone: string | null;
  role: string | null;
  firstName: string;
  lastName: string;
  nationalId: string | null;
};

type AccountBody = {
  role?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  national_id?: string | null;
  phone?: string | null;
};

// Reads the session user for the email and the backend account for the identity, phone and role. Throws the typed access error when signed out.
async function fetchProfile(): Promise<ProfileData> {
  const token = await currentAccessToken();
  const { data, error } = await createClient().auth.getUser();
  if (error || !data.user) throw new Error("No pudimos verificar tu sesión.");

  const response = await accountApiFetch("/api/account/me", token, process.env.NEXT_PUBLIC_API_URL);
  if (!response.ok) throw new Error("No pudimos cargar tu perfil.");
  const body = await response.json() as AccountBody;

  return {
    email: data.user.email ?? "",
    phone: body.phone ?? null,
    role: body.role ?? null,
    firstName: body.first_name ?? "",
    lastName: body.last_name ?? "",
    nationalId: body.national_id ?? null,
  };
}

export default function ProfileSettingsPage() {
  const queryClient = useQueryClient();
  const [changingPhone, setChangingPhone] = useState(false);
  const [phoneNotice, setPhoneNotice] = useState("");
  const [phoneWarning, setPhoneWarning] = useState("");
  const profileQuery = useQuery({
    queryKey: ["account-profile"],
    queryFn: fetchProfile,
    retry: false,
    staleTime: 60_000,
  });

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main lp-app customer-services-page" id="contenido">
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
            <>
              {phoneNotice && <p role="status" aria-live="polite" className="auth-notice">{phoneNotice}</p>}
              {phoneWarning && <p className="auth-help">{phoneWarning}</p>}
              <dl className="account-data">
                <div>
                  <dt>Nombre</dt>
                  <dd>{profileQuery.data.firstName || MISSING_VALUE}</dd>
                </div>
                <div>
                  <dt>Apellido</dt>
                  <dd>{profileQuery.data.lastName || MISSING_VALUE}</dd>
                </div>
                <div>
                  <dt>RUT</dt>
                  <dd>{profileQuery.data.nationalId || MISSING_VALUE}</dd>
                </div>
                <div>
                  <dt>Correo</dt>
                  <dd>{profileQuery.data.email || MISSING_VALUE}</dd>
                </div>
                <div>
                  <dt>Teléfono</dt>
                  <dd>
                    {profileQuery.data.phone || MISSING_VALUE}
                    {!changingPhone && (
                      <button
                        className="button button-secondary account-data-action"
                        onClick={() => {
                          setPhoneNotice("");
                          setPhoneWarning("");
                          setChangingPhone(true);
                        }}
                        type="button"
                      >
                        Cambiar teléfono
                      </button>
                    )}
                  </dd>
                </div>
              </dl>
              {changingPhone && (
                <PhoneChangeForm
                  currentPhone={profileQuery.data.phone}
                  onCancel={() => setChangingPhone(false)}
                  onChanged={(account, warning) => {
                    queryClient.setQueryData<ProfileData>(["account-profile"], (current) => current && { ...current, phone: account.phone });
                    setChangingPhone(false);
                    setPhoneNotice("Tu número de teléfono se actualizó.");
                    setPhoneWarning(warning ?? "");
                  }}
                />
              )}
            </>
          )}
          {profileQuery.isSuccess && PROVIDER_ROLES.has(profileQuery.data.role ?? "") && (
            <ProviderProfileForm isCompany={profileQuery.data.role === "company_owner"} />
          )}
        </div>
      </main>
      <MarketplaceFooter />
    </>
  );
}
