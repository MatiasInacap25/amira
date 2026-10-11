"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { MarketplaceSkeleton, SERVICE_DETAIL_LAYOUT } from "@/components/marketplace/marketplace-skeleton";
import { ServiceDetail } from "@/components/marketplace/service-detail";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { accountApiFetch } from "@/lib/auth/account-api";
import {
  parseServiceResponse,
  requestCustomerServiceDetail,
  requestProviderServiceDetail,
  ServiceRequestError,
  type ServiceDetail as ServiceDetailData,
} from "@/lib/marketplace-api";
import { sendWithTokenRetry } from "@/lib/customer-request-retry";
import { CustomerSessionError, readAccessToken, refreshAccessToken } from "@/lib/customer-session";
import { isProviderRole } from "@/lib/provider-requests";

const ACCOUNT_ROLE_KEY = ["services-account-role"];
const SIGN_IN_HREF = "/login?next=%2Fcuenta%2Fservicios";
const LIST_HREF = "/cuenta/servicios";

class ServiceNotFoundError extends Error {}

/**
 * Resolves whether the signed-in account is a provider, which selects the detail endpoint.
 * Role comes from /api/account/me; anything other than a provider role is treated as a customer.
 */
export function useServiceAccountRole() {
  return useQuery({
    queryKey: ACCOUNT_ROLE_KEY,
    queryFn: async () => {
      const response = await sendWithTokenRetry(
        (accessToken) => accountApiFetch("/api/account/me", accessToken, process.env.NEXT_PUBLIC_API_URL),
        readAccessToken,
        refreshAccessToken,
      );
      if (response.status === 401) throw new CustomerSessionError();
      if (!response.ok) throw new ServiceRequestError(response.status);
      const body = await response.json() as { role?: string | null };
      return { provider: isProviderRole(body.role) };
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function ServiceDetailView({ serviceId }: { serviceId: string }) {
  const roleQuery = useServiceAccountRole();
  const provider = roleQuery.data?.provider ?? false;

  const detailQuery = useQuery({
    queryKey: ["service-detail", provider ? "provider" : "customer", serviceId],
    queryFn: async () => {
      const response = await sendWithTokenRetry(
        (accessToken) => (provider
          ? requestProviderServiceDetail(accessToken, serviceId)
          : requestCustomerServiceDetail(accessToken, serviceId)),
        readAccessToken,
        refreshAccessToken,
      );
      if (response.status === 401) throw new CustomerSessionError();
      if (response.status === 404) throw new ServiceNotFoundError();
      return parseServiceResponse<ServiceDetailData>(response);
    },
    enabled: roleQuery.isSuccess,
    retry: false,
  });

  const error = roleQuery.isError ? roleQuery.error : detailQuery.error;
  const needsSignIn = error instanceof CustomerSessionError;
  const notFound = error instanceof ServiceNotFoundError;
  const failed = Boolean(error) && !needsSignIn && !notFound;
  const loading = roleQuery.isPending || (roleQuery.isSuccess && detailQuery.isPending);

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main customer-services-page" id="contenido">
        <div className="customer-services-wrap">
          <Link className="account-service-back" href={LIST_HREF}>
            <ArrowLeft aria-hidden="true" size={15} /> Volver a mis servicios
          </Link>

          {needsSignIn && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos verificar tu sesión</h2>
              <p>Inicia sesión de nuevo para ver este servicio.</p>
              <Link className="button button-secondary" href={SIGN_IN_HREF}>Iniciar sesión</Link>
            </div>
          )}
          {notFound && (
            <div className="marketplace-state marketplace-empty" role="status">
              <h2>Servicio no encontrado</h2>
              <p>Este servicio no existe o no está disponible en tu cuenta.</p>
              <Link className="button button-secondary" href={LIST_HREF}>Volver a mis servicios</Link>
            </div>
          )}
          {failed && (
            <div className="marketplace-state marketplace-error" role="alert">
              <h2>No pudimos cargar este servicio</h2>
              <p>Inténtalo nuevamente en unos minutos.</p>
              <button
                className="button button-secondary"
                onClick={() => void (roleQuery.isError ? roleQuery.refetch() : detailQuery.refetch())}
                type="button"
              >
                Reintentar
              </button>
            </div>
          )}

          {!error && (
            <MarketplaceSkeleton label="Cargando servicio…" layout={SERVICE_DETAIL_LAYOUT} loading={loading} name="service-detail">
              {detailQuery.data && <ServiceDetail service={detailQuery.data} />}
            </MarketplaceSkeleton>
          )}
        </div>
      </main>
      <MarketplaceFooter />
    </>
  );
}
