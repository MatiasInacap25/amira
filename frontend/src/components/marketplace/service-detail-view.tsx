"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import { PublishSharedTripDialog } from "@/components/account/publish-shared-trip-dialog";
import { CustomerServiceActions } from "@/components/marketplace/customer-service-actions";
import { DeliveryPhoto } from "@/components/marketplace/delivery-photo";
import { DriverLocationSharing } from "@/components/marketplace/driver-location-sharing";
import { ServiceActions } from "@/components/marketplace/service-actions";
import { ServiceAssignmentForm } from "@/components/marketplace/service-assignment-form";
import { MarketplaceSkeleton, SERVICE_DETAIL_LAYOUT } from "@/components/marketplace/marketplace-skeleton";
import { ServiceDetail } from "@/components/marketplace/service-detail";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";
import { accountApiFetch } from "@/lib/auth/account-api";
import {
  parseAssignmentSaveResponse,
  parseServiceLocationResponse,
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
  requestProviderServiceLocationUpdate,
  requestProviderServiceStart,
  requestServiceLocation,
  ServiceRequestError,
  type ServiceAssignmentOptions,
  type ServiceAssignmentUpdate,
  type ServiceDetail as ServiceDetailData,
  type ServiceLocation,
} from "@/lib/marketplace-api";
import {
  LOCATION_INTERVAL_MS,
  LocationError,
  type LocationPayload,
  geolocationErrorMessage,
  requestDriverLocation,
} from "@/lib/geolocation";
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

// The map pulls in Leaflet and touches the DOM, so it is loaded only in the browser.
const LiveLocationMap = dynamic(() => import("@/components/marketplace/live-location-map"), {
  ssr: false,
  loading: () => <p className="account-service-empty">Cargando mapa…</p>,
});

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

  // The position is asked first: if the browser refuses it, nothing is sent and the service stays confirmed.
  const startService = useMutation({
    mutationFn: async () => {
      const location = await requestDriverLocation();
      const response = await sendAuthorizedRequest((accessToken) => requestProviderServiceStart(accessToken, serviceId, location));
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

// Time only: the last update is always from today while the service is in progress, so the date adds nothing.
function formatLocationTime(value: string) {
  return new Date(value).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });
}

function assignmentSignature(assignments: ServiceDetailData["assignments"]) {
  return assignments.map((assignment) => `${assignment.driverId}:${assignment.vehicleId}`).join("|");
}

export function ServiceDetailView({ serviceId }: { serviceId: string }) {
  const roleQuery = useServiceAccountRole();
  const provider = roleQuery.data?.provider ?? false;
  const mutations = useProviderServiceMutations(serviceId);
  const customerMutations = useCustomerServiceMutations(serviceId);
  const [publishOpen, setPublishOpen] = useState(false);
  const [locationMessage, setLocationMessage] = useState<string | null>(null);

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

  // The assigned driver shares their own position; anyone else who can see an in-progress service follows it on the map.
  const showDriverSharing = Boolean(isProviderViewer && detail?.viewerAssigned && detail.status === "in_progress");
  const showLiveMap = Boolean(detail && detail.status === "in_progress" && !showDriverSharing);
  const locationQuery = useQuery({
    queryKey: ["service-location", isCustomerViewer ? "customer" : "provider", serviceId],
    queryFn: async () => {
      const viewer = isCustomerViewer ? "customer" : "provider";
      const response = await sendAuthorizedRequest((accessToken) => requestServiceLocation(accessToken, viewer, serviceId));
      if (response.status === 401) throw new CustomerSessionError();
      return parseServiceLocationResponse(response);
    },
    enabled: showLiveMap,
    // The customer page refreshes about every 15 seconds, the same cadence the driver sends at.
    refetchInterval: LOCATION_INTERVAL_MS,
    retry: false,
  });

  function sendDriverLocation(location: LocationPayload) {
    return sendAuthorizedRequest((accessToken) => requestProviderServiceLocationUpdate(accessToken, serviceId, location))
      .then((response) => parseServiceResponse<ServiceLocation>(response));
  }

  // A refused position is shown here, not as the generic start error, because the service did not start at all.
  async function startWithLocation() {
    setLocationMessage(null);
    try {
      await mutations.startService.mutateAsync();
    } catch (cause) {
      if (!(cause instanceof LocationError)) throw cause;
      setLocationMessage(geolocationErrorMessage(cause.code));
    }
  }

  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main lp-app customer-services-page" id="contenido">
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
                    <>
                      <ServiceActions
                        canManage={detail.canManage}
                        completePending={mutations.completeService.isPending}
                        hasAssignments={detail.assignments.length > 0}
                        onComplete={(photo) => mutations.completeService.mutateAsync(photo)}
                        onStart={startWithLocation}
                        startPending={mutations.startService.isPending}
                        status={detail.status}
                        viewerAssigned={detail.viewerAssigned}
                      />
                      {locationMessage && <p className="account-service-form-error" role="alert">{locationMessage}</p>}
                    </>
                  ) : undefined}
                  locationSharing={showDriverSharing ? (
                    <DriverLocationSharing sendLocation={sendDriverLocation} />
                  ) : showLiveMap ? (
                    locationQuery.isError ? (
                      <p className="account-service-form-error" role="alert">No pudimos cargar la ubicación del conductor. Inténtalo nuevamente en unos minutos.</p>
                    ) : locationQuery.data ? (
                      <>
                        <LiveLocationMap latitude={locationQuery.data.latitude} longitude={locationQuery.data.longitude} />
                        <p className="live-location-updated">
                          Última actualización: <time dateTime={locationQuery.data.updatedAt}>{formatLocationTime(locationQuery.data.updatedAt)}</time>
                        </p>
                      </>
                    ) : locationQuery.isSuccess ? (
                      <p className="account-service-empty">El conductor todavía no comparte su ubicación</p>
                    ) : (
                      <p className="account-service-empty">Cargando ubicación…</p>
                    )
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
                  sharedTrip={isProviderViewer && detail.canManage ? (
                    detail.isExclusive ? (
                      <p className="account-service-empty">El cliente no aceptó compartir el viaje.</p>
                    ) : detail.sharedTripId ? (
                      <>
                        <p className="account-service-empty">Publicado como viaje compartido.</p>
                        <Link className="button button-secondary" href="/cuenta/viajes-compartidos">Ver mis viajes compartidos</Link>
                      </>
                    ) : (
                      <>
                        <button className="button button-secondary" onClick={() => setPublishOpen(true)} type="button">Publicar como viaje compartido</button>
                        <PublishSharedTripDialog onClose={() => setPublishOpen(false)} open={publishOpen} serviceId={serviceId} />
                      </>
                    )
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
