"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { CustomerServiceActions } from "@/components/marketplace/customer-service-actions";
import { DeliveryPhoto } from "@/components/marketplace/delivery-photo";
import { ServiceActions } from "@/components/marketplace/service-actions";
import { ServiceAssignmentForm } from "@/components/marketplace/service-assignment-form";
import { MarketplaceSkeleton, SERVICE_DETAIL_LAYOUT } from "@/components/marketplace/marketplace-skeleton";
import { ServiceDetail } from "@/components/marketplace/service-detail";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { accountApiFetch } from "@/lib/auth/account-api";
import {
  parseAssignmentSaveResponse,
  parseServiceResponse,
  type DeliveryPhotoLink,
  requestCustomerDeliveryPhoto,
  requestCustomerServiceClaim,
  requestCustomerServiceConsent,
  requestCustomerServiceDetail,
  requestProviderAssignmentOptions,
  requestProviderAssignmentUpdate,
  requestProviderDeliveryPhoto,
  requestProviderServiceComplete,
  requestProviderServiceDetail,
  requestProviderServiceStart,
  ServiceRequestError,
  type ServiceAssignmentOptions,
  type ServiceAssignmentUpdate,
  type ServiceDetail as ServiceDetailData,
} from "@/lib/marketplace-api";
import { sendWithTokenRetry, type StatusResponse } from "@/lib/customer-request-retry";
import { CustomerSessionError, readAccessToken, refreshAccessToken } from "@/lib/customer-session";
import { isProviderRole } from "@/lib/provider-requests";
import {
  ACCOUNT_ROLE_KEY,
  CUSTOMER_SERVICES_KEY,
  PROVIDER_SERVICES_KEY,
  SERVICE_DETAIL_KEY,
} from "@/lib/service-query-keys";
import { serviceActionErrorMessage } from "@/lib/service-status";

const SIGN_IN_HREF = "/login?next=%2Fcuenta%2Fservicios";
const LIST_HREF = "/cuenta/servicios";

class ServiceNotFoundError extends Error {}

// Sends with the session token, retrying once with a refreshed token on 401. A second 401 is returned to the caller.
function sendAuthorizedRequest<T extends StatusResponse>(send: (accessToken: string) => Promise<T>) {
  return sendWithTokenRetry(send, readAccessToken, refreshAccessToken);
}

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

// Provider mutations refresh the detail and every list, since a status or assignment change shows in the customer list too.
function useProviderServiceMutations(serviceId: string) {
  const queryClient = useQueryClient();

  function refreshServiceViews() {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: SERVICE_DETAIL_KEY }),
      queryClient.invalidateQueries({ queryKey: PROVIDER_SERVICES_KEY }),
      queryClient.invalidateQueries({ queryKey: CUSTOMER_SERVICES_KEY }),
    ]);
  }

  const saveAssignments = useMutation({
    mutationFn: async (update: ServiceAssignmentUpdate) => {
      const response = await sendAuthorizedRequest((accessToken) => requestProviderAssignmentUpdate(accessToken, serviceId, update));
      return parseAssignmentSaveResponse(response);
    },
    onSuccess: (result) => {
      if (result.status === "saved") return refreshServiceViews();
    },
  });

  const startService = useMutation({
    mutationFn: async () => {
      const response = await sendAuthorizedRequest((accessToken) => requestProviderServiceStart(accessToken, serviceId));
      return parseServiceResponse<ServiceDetailData>(response);
    },
    onSuccess: refreshServiceViews,
  });

  const completeService = useMutation({
    mutationFn: async (photo: File) => {
      const response = await sendAuthorizedRequest((accessToken) => requestProviderServiceComplete(accessToken, serviceId, photo));
      return parseServiceResponse<ServiceDetailData>(response);
    },
    onSuccess: refreshServiceViews,
  });

  return { saveAssignments, startService, completeService };
}

// Customer mutations refresh on settle, not only on success: a 409 means the shown state is stale and must be refetched.
function useCustomerServiceMutations(serviceId: string) {
  const queryClient = useQueryClient();

  function refreshServiceViews() {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: SERVICE_DETAIL_KEY }),
      queryClient.invalidateQueries({ queryKey: CUSTOMER_SERVICES_KEY }),
    ]);
  }

  const consent = useMutation({
    mutationFn: async () => {
      const response = await sendAuthorizedRequest((accessToken) => requestCustomerServiceConsent(accessToken, serviceId));
      return parseServiceResponse<ServiceDetailData>(response);
    },
    onSettled: refreshServiceViews,
  });

  const claim = useMutation({
    mutationFn: async (reason: string) => {
      const response = await sendAuthorizedRequest((accessToken) => requestCustomerServiceClaim(accessToken, serviceId, { reason }));
      return parseServiceResponse<ServiceDetailData>(response);
    },
    onSettled: refreshServiceViews,
  });

  return { consent, claim };
}

function assignmentSignature(assignments: ServiceDetailData["assignments"]) {
  return assignments.map((assignment) => `${assignment.driverId}:${assignment.vehicleId}`).join("|");
}

export function ServiceDetailView({ serviceId }: { serviceId: string }) {
  const roleQuery = useServiceAccountRole();
  const provider = roleQuery.data?.provider ?? false;
  const mutations = useProviderServiceMutations(serviceId);
  const customerMutations = useCustomerServiceMutations(serviceId);

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

  const detail = detailQuery.data;
  // Only the profile owner can manage assignments, and only before the service starts.
  const showAssignmentForm = Boolean(detail?.canManage && detail.status === "confirmed");
  // A same-day conflict answer is a successful request too, so only a saved result shows the notice.
  const assignmentsSaved = mutations.saveAssignments.isSuccess && mutations.saveAssignments.data?.status === "saved";

  const optionsQuery = useQuery({
    queryKey: ["service-assignment-options", serviceId],
    queryFn: async () => {
      const response = await sendAuthorizedRequest((accessToken) => requestProviderAssignmentOptions(accessToken, serviceId));
      return parseServiceResponse<ServiceAssignmentOptions>(response);
    },
    enabled: showAssignmentForm,
    retry: false,
  });

  const error = roleQuery.isError ? roleQuery.error : detailQuery.error;
  const needsSignIn = error instanceof CustomerSessionError;
  const notFound = error instanceof ServiceNotFoundError;
  const failed = Boolean(error) && !needsSignIn && !notFound;
  const loading = roleQuery.isPending || (roleQuery.isSuccess && detailQuery.isPending);

  const isProviderViewer = detail?.viewerRole === "provider";
  const isCustomerViewer = detail?.viewerRole === "customer";
  // Claims and consent only exist once the service is completed; a disputed service still shows its open claim.
  const showCustomerResolution = Boolean(isCustomerViewer && detail && (detail.status === "completed" || detail.status === "disputed"));

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
              {detail && (
                <ServiceDetail
                  actions={isProviderViewer ? (
                    <ServiceActions
                      canManage={detail.canManage}
                      completePending={mutations.completeService.isPending}
                      hasAssignments={detail.assignments.length > 0}
                      onComplete={(photo) => mutations.completeService.mutateAsync(photo)}
                      onStart={() => mutations.startService.mutateAsync()}
                      startPending={mutations.startService.isPending}
                      status={detail.status}
                      viewerAssigned={detail.viewerAssigned}
                    />
                  ) : undefined}
                  assignmentEditor={showAssignmentForm ? (
                    <>
                      {assignmentsSaved && (
                        <p aria-live="polite" className="account-service-result" role="status">Asignaciones guardadas.</p>
                      )}
                      <ServiceAssignmentForm
                        // Remounts when the saved assignments change, so the form is prefilled from the server state.
                        key={assignmentSignature(detail.assignments)}
                        assignments={detail.assignments}
                        onSave={(update) => mutations.saveAssignments.mutateAsync(update)}
                        options={optionsQuery.data}
                        optionsErrorMessage={optionsQuery.isError ? serviceActionErrorMessage(optionsQuery.error, "load-options") : undefined}
                        optionsPending={optionsQuery.isPending}
                      />
                    </>
                  ) : undefined}
                  customerResolution={showCustomerResolution ? (
                    <CustomerServiceActions
                      claimPending={customerMutations.claim.isPending}
                      consentPending={customerMutations.consent.isPending}
                      onClaim={(reason) => customerMutations.claim.mutateAsync(reason)}
                      onConsent={() => customerMutations.consent.mutateAsync()}
                      service={detail}
                    />
                  ) : undefined}
                  deliveryPhoto={detail.deliveryPhotoAvailable ? (
                    <DeliveryPhoto
                      onLoad={() => sendAuthorizedRequest((accessToken) => (isProviderViewer
                        ? requestProviderDeliveryPhoto(accessToken, serviceId)
                        : requestCustomerDeliveryPhoto(accessToken, serviceId)))
                        .then((response) => parseServiceResponse<DeliveryPhotoLink>(response))}
                    />
                  ) : undefined}
                  service={detail}
                />
              )}
            </MarketplaceSkeleton>
          )}
        </div>
      </main>
      <MarketplaceFooter />
    </>
  );
}
