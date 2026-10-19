import { authenticatedApiFetch, resolveApiBaseUrl } from "@/lib/auth/account-api";
import {
  adaptChatMessagesPage,
  ChatRequestError,
  type BackendChatMessagesPage,
  type ChatAttachmentUrl,
  type ChatListPage,
  type ChatMessage,
  type ChatQuotation,
} from "@/lib/chats";
import { buildProviderRequestsQuery, type ProviderRequestStatus } from "@/lib/provider-requests";

export type LocationCommune = {
  code: string;
  name: string;
};

export type LocationRegion = {
  code: string;
  name: string;
  communes: LocationCommune[];
};

export type LocationCatalog = {
  regions: LocationRegion[];
};

export type ServiceType = {
  id: string;
  slug: string;
  name: string;
};

export type ServiceTypeCatalog = {
  items: ServiceType[];
};

export type ServiceProfile = {
  profileId: string;
  providerName: string;
  category: string;
  description?: string | null;
  location?: string | null;
  communeCode?: string | null;
  communeName?: string | null;
  regionName?: string | null;
  logoUrl?: string | null;
  services: Array<{ serviceTypeId: string; name: string }>;
};

export type SharedRouteStop = {
  stopNumber: number;
  estimatedAt?: string | null;
};

export type SharedRoute = {
  tripId: string;
  profileId: string;
  providerName: string;
  origin: string;
  destination: string;
  originCommuneCode?: string | null;
  destinationCommuneCode?: string | null;
  departureAt?: string | null;
  stops?: SharedRouteStop[] | null;
};

export type ProviderProfile = {
  profileId: string;
  providerName: string;
  kind: "company" | "independent_driver";
  description: string | null;
  location: string | null;
  communeCode: string | null;
  communeName: string | null;
  regionName: string | null;
  ownerName: string;
  drivers: Array<{ firstName: string; lastName: string; isOwner: boolean }>;
  services: Array<{ serviceTypeId: string; name: string }>;
  vehicles: Array<{ brand: string; model: string; year: number | null; maximumWeight: string | null }>;
  ratings?: {
    averageRating: number | null;
    ratingCount: number;
    recent: Array<{ rating: number; comment: string | null; createdAt: string }>;
  } | null;
};

export type CustomerServiceRating = {
  rating: number;
  comment: string | null;
  createdAt: string;
};

export type CustomerService = {
  serviceId: string;
  providerProfileId: string;
  providerName: string;
  serviceTypeName: string;
  completedAt: string | null;
  rating: CustomerServiceRating | null;
};

export type CustomerServicePage = PagedResponse<CustomerService>;

// "Mis servicios": contracted services for customers and providers. Contact details are never part of these shapes.
export type ServiceStatus = "confirmed" | "in_progress" | "completed" | "disputed";

export type ServiceListItem = {
  serviceId: string;
  status: ServiceStatus;
  serviceTypeName: string;
  serviceAt: string | null;
  amount: number | null;
  // ISO 4217 code from the backend (three uppercase letters).
  currency: string;
  originCommune: string | null;
  destinationCommune: string | null;
  isExclusive: boolean;
  counterpartName: string;
  assignmentCount: number;
};

export type ServiceAssignment = {
  driverId: string;
  driverFirstName: string;
  vehicleId: string;
  vehicleLabel: string;
  plate: string;
};

export type ServiceDetail = ServiceListItem & {
  chatId: string | null;
  description: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  payoutDeadlineAt: string | null;
  viewerRole: "customer" | "provider";
  canManage: boolean;
  // True when the viewer is one of the assigned drivers; always false for customers.
  viewerAssigned: boolean;
  assignments: ServiceAssignment[];
  deliveryPhotoAvailable: boolean;
  customerConsentAt: string | null;
  claimOpen: boolean;
  // Customer-only flags; providers always receive false.
  canClaim: boolean;
  canConsent: boolean;
};

export type ServiceListPage = PagedResponse<ServiceListItem>;

export type ServiceAssignmentOptions = {
  drivers: Array<{ driverId: string; firstName: string; lastName: string; isOwner: boolean }>;
  vehicles: Array<{ vehicleId: string; vehicleLabel: string; plate: string }>;
};

export type ServiceAssignmentInput = {
  driverId: string;
  vehicleId: string;
};

export type ServiceAssignmentUpdate = {
  assignments: ServiceAssignmentInput[];
  confirmSameDayConflicts: boolean;
};

export type ServiceSameDayConflict = {
  driverId: string;
  serviceId: string;
  serviceAt: string;
};

// A 409 with conflicts is an expected outcome the user can confirm, so it is returned, not thrown.
export type ServiceAssignmentSaveResult =
  | { status: "saved"; service: ServiceDetail }
  | { status: "same_day_conflicts"; conflicts: ServiceSameDayConflict[] };

export type DeliveryPhotoLink = {
  url: string;
  expiresAt: string;
};

export type CustomerServiceClaimInput = {
  reason: string;
};

export type ProviderServiceQuery = {
  status?: ServiceStatus;
  limit: number;
  offset: number;
};

export type ServiceRequestInput = {
  profileId: string;
  serviceTypeId: string;
  originCommuneCode: string;
  destinationCommuneCode: string;
  origin: string | null;
  destination: string | null;
  requestedAt: string | null;
  estimatedWeight: string | null;
  estimatedVolume: string | null;
  description: string | null;
  cargoMeasurements: string | null;
};

export type ProviderRequest = {
  requestId: string;
  status: "pending" | "accepted" | "rejected" | string;
  origin: string | null;
  destination: string | null;
  originCommuneCode: string | null;
  originCommuneName: string | null;
  originRegionName: string | null;
  destinationCommuneCode: string | null;
  destinationCommuneName: string | null;
  destinationRegionName: string | null;
  isExclusive: boolean;
  customerFirstName: string;
  // Non-null only once the request is accepted.
  customerLastName: string | null;
  requestedAt: string | null;
  createdAt: string;
  estimatedWeight: string | null;
  estimatedVolume: string | null;
  description: string | null;
  cargoMeasurements: string | null;
  serviceName: string;
  chatId: string | null;
};

export type ProviderRequestCounts = {
  pending: number;
  accepted: number;
  rejected: number;
};

// Counts always cover every status, independent of the status filter.
export type ProviderRequestPage = PagedResponse<ProviderRequest> & {
  counts: ProviderRequestCounts;
};

export type ProviderRequestDecision = {
  requestId: string;
  status: "accepted" | "rejected";
  chatId: string | null;
};

export type PagedResponse<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type ServiceFilters = {
  q: string;
  serviceType: string;
  regionCode: string;
  communeCode: string;
  offset: number;
};

export type SharedRouteFilters = {
  originCommuneCode: string;
  destinationCommuneCode: string;
  departureFrom: string;
  departureTo: string;
  offset: number;
};

const PAGE_SIZE = 20;
function addNonEmpty(params: URLSearchParams, key: string, value: string) {
  const normalized = value.trim();
  if (normalized) params.set(key, normalized);
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const apiBaseUrl = resolveApiBaseUrl(process.env.NEXT_PUBLIC_API_URL);
  const response = await fetch(`${apiBaseUrl}${path}`, { headers: { Accept: "application/json" }, cache: "no-store", signal });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export function getLocations(signal?: AbortSignal) {
  return getJson<LocationCatalog>("/api/locations", signal);
}

export function getServiceTypes(signal?: AbortSignal) {
  return getJson<ServiceTypeCatalog>("/api/service-types", signal);
}

export function getProviderProfile(profileId: string, signal?: AbortSignal) {
  return getJson<ProviderProfile>(`/api/providers/${encodeURIComponent(profileId)}`, signal);
}

export async function createServiceRequest(input: ServiceRequestInput, accessToken: string) {
  return authenticatedApiFetch(
    "/api/service-requests",
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) },
  );
}

export function requestCustomerServices(accessToken: string, offset: number, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  return authenticatedApiFetch(
    `/api/customer/services?${params.toString()}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, cache: "no-store", signal },
  );
}

export async function createCustomerServiceRating(serviceId: string, input: { rating: number; comment: string | null }, accessToken: string) {
  return authenticatedApiFetch(
    `/api/customer/services/${encodeURIComponent(serviceId)}/rating`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(input) },
  );
}

export class ServiceRequestError extends Error {
  // `detail` is the backend's message for handled errors, when it is a plain string.
  constructor(readonly status: number, readonly detail: string | null = null) {
    super(`Service request failed (${status})`);
    this.name = "ServiceRequestError";
  }
}

// Responses are returned raw so callers can map 401 (token retry) and 404 (not visible) before parsing.
export function requestProviderServices(accessToken: string, options: ProviderServiceQuery, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(options.limit), offset: String(options.offset) });
  if (options.status) params.set("status", options.status);
  return authenticatedApiFetch(
    `/api/provider/services?${params.toString()}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, cache: "no-store", signal },
  );
}

export function requestProviderServiceDetail(accessToken: string, serviceId: string, signal?: AbortSignal) {
  return authenticatedApiFetch(
    `/api/provider/services/${encodeURIComponent(serviceId)}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, cache: "no-store", signal },
  );
}

export function requestCustomerServiceDetail(accessToken: string, serviceId: string, signal?: AbortSignal) {
  return authenticatedApiFetch(
    `/api/customer/services/${encodeURIComponent(serviceId)}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, cache: "no-store", signal },
  );
}

// FastAPI puts a handled error's message in `detail`. A body that is not JSON, or has no string detail, yields null.
async function serviceErrorDetailFrom(response: Response): Promise<string | null> {
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  return typeof body?.detail === "string" ? body.detail : null;
}

export async function parseServiceResponse<T>(response: Response): Promise<T> {
  if (!response.ok) throw new ServiceRequestError(response.status, await serviceErrorDetailFrom(response));
  return response.json() as Promise<T>;
}

export function requestProviderAssignmentOptions(accessToken: string, serviceId: string, signal?: AbortSignal) {
  return authenticatedApiFetch(
    `/api/provider/services/${encodeURIComponent(serviceId)}/assignment-options`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, cache: "no-store", signal },
  );
}

export function requestProviderAssignmentUpdate(accessToken: string, serviceId: string, update: ServiceAssignmentUpdate) {
  return authenticatedApiFetch(
    `/api/provider/services/${encodeURIComponent(serviceId)}/assignments`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(update),
    },
  );
}

// Only the same-day 409 is typed; any other failure goes through parseServiceResponse and throws.
export async function parseAssignmentSaveResponse(response: Response): Promise<ServiceAssignmentSaveResult> {
  if (response.status === 409) {
    const body = (await response.json().catch(() => null)) as { conflicts?: unknown } | null;
    if (Array.isArray(body?.conflicts)) {
      return { status: "same_day_conflicts", conflicts: body.conflicts as ServiceSameDayConflict[] };
    }
  }
  return { status: "saved", service: await parseServiceResponse<ServiceDetail>(response) };
}

export function requestProviderServiceStart(accessToken: string, serviceId: string) {
  return authenticatedApiFetch(
    `/api/provider/services/${encodeURIComponent(serviceId)}/start`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { method: "POST", headers: { Accept: "application/json" } },
  );
}

// No Content-Type header: the browser sets the multipart boundary.
export function requestProviderServiceComplete(accessToken: string, serviceId: string, photo: File) {
  const body = new FormData();
  body.append("photo", photo);
  return authenticatedApiFetch(
    `/api/provider/services/${encodeURIComponent(serviceId)}/complete`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { method: "POST", headers: { Accept: "application/json" }, body },
  );
}

export function requestProviderDeliveryPhoto(accessToken: string, serviceId: string, signal?: AbortSignal) {
  return authenticatedApiFetch(
    `/api/provider/services/${encodeURIComponent(serviceId)}/delivery-photo`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, cache: "no-store", signal },
  );
}

export function requestCustomerDeliveryPhoto(accessToken: string, serviceId: string, signal?: AbortSignal) {
  return authenticatedApiFetch(
    `/api/customer/services/${encodeURIComponent(serviceId)}/delivery-photo`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, cache: "no-store", signal },
  );
}

// No body: the backend records consent for the viewer's own service and releases the payout at the next run.
export function requestCustomerServiceConsent(accessToken: string, serviceId: string) {
  return authenticatedApiFetch(
    `/api/customer/services/${encodeURIComponent(serviceId)}/consent`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { method: "POST", headers: { Accept: "application/json" } },
  );
}

export function requestCustomerServiceClaim(accessToken: string, serviceId: string, input: CustomerServiceClaimInput) {
  return authenticatedApiFetch(
    `/api/customer/services/${encodeURIComponent(serviceId)}/claims`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export async function getProviderRequests(
  accessToken: string,
  options: { status?: ProviderRequestStatus; limit: number; offset: number },
) {
  const response = await authenticatedApiFetch(
    `/api/provider/requests?${buildProviderRequestsQuery(options)}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) throw new Error(`Provider requests failed (${response.status})`);
  return response.json() as Promise<ProviderRequestPage>;
}

export async function getChats(accessToken: string, options: { limit: number; offset: number }, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(options.limit), offset: String(options.offset) });
  const response = await authenticatedApiFetch(
    `/api/chats?${params.toString()}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) throw new ChatRequestError(response.status);
  return response.json() as Promise<ChatListPage>;
}

export async function getChatMessages(
  accessToken: string,
  chatId: string,
  options: { limit: number; before?: string },
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ limit: String(options.limit) });
  if (options.before) params.set("before", options.before);
  const response = await authenticatedApiFetch(
    `/api/chats/${encodeURIComponent(chatId)}/messages?${params.toString()}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) throw new ChatRequestError(response.status);
  return adaptChatMessagesPage((await response.json()) as BackendChatMessagesPage);
}

// FastAPI validation errors arrive as { detail: [{ type, msg }] }; other errors carry no usable detail.
async function chatErrorFrom(response: Response): Promise<ChatRequestError> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  const first = Array.isArray(body?.detail) ? (body.detail[0] as { type?: unknown; msg?: unknown } | undefined) : undefined;
  return new ChatRequestError(response.status, {
    type: typeof first?.type === "string" ? first.type : null,
    msg: typeof first?.msg === "string" ? first.msg : null,
  });
}

async function postChatJson<T>(accessToken: string, path: string, body?: unknown): Promise<T> {
  const response = await authenticatedApiFetch(path, accessToken, process.env.NEXT_PUBLIC_API_URL, {
    method: "POST",
    headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await chatErrorFrom(response);
  return response.json() as Promise<T>;
}

export function sendChatMessage(accessToken: string, chatId: string, content: string) {
  return postChatJson<ChatMessage>(accessToken, `/api/chats/${encodeURIComponent(chatId)}/messages`, { content });
}

// Multipart upload: the browser sets the boundary, so no Content-Type header is passed.
export async function uploadChatAttachment(accessToken: string, chatId: string, photo: File, content?: string) {
  const form = new FormData();
  form.append("photo", photo);
  if (content) form.append("content", content);
  const response = await authenticatedApiFetch(
    `/api/chats/${encodeURIComponent(chatId)}/messages/attachments`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { method: "POST", headers: { Accept: "application/json" }, body: form },
  );
  if (!response.ok) throw await chatErrorFrom(response);
  return response.json() as Promise<ChatMessage>;
}

export async function getChatAttachmentUrl(accessToken: string, chatId: string, messageId: string) {
  const response = await authenticatedApiFetch(
    `/api/chats/${encodeURIComponent(chatId)}/messages/${encodeURIComponent(messageId)}/attachment`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) throw new ChatRequestError(response.status);
  return response.json() as Promise<ChatAttachmentUrl>;
}

export type QuotationInput = {
  amount: number;
  serviceAt: string;
  description: string;
  validityHours: number;
};

export function createQuotation(accessToken: string, chatId: string, input: QuotationInput) {
  return postChatJson<ChatQuotation>(accessToken, `/api/chats/${encodeURIComponent(chatId)}/quotations`, input);
}

export function rejectQuotation(accessToken: string, quotationId: string) {
  return postChatJson<ChatQuotation>(accessToken, `/api/quotations/${encodeURIComponent(quotationId)}/reject`);
}

export function createQuotationPayment(accessToken: string, quotationId: string) {
  return postChatJson<{ paymentId: string; checkoutUrl: string }>(
    accessToken,
    `/api/quotations/${encodeURIComponent(quotationId)}/payments`,
  );
}

export type PaymentStatusPage = {
  paymentId: string;
  status: string;
  quotationId: string;
  quotationStatus: string;
  chatId: string;
};

export async function getPaymentStatus(accessToken: string, paymentId: string) {
  const response = await authenticatedApiFetch(
    `/api/payments/${encodeURIComponent(paymentId)}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) throw new ChatRequestError(response.status);
  return response.json() as Promise<PaymentStatusPage>;
}

// Development-only simulated checkout. The backend signs and applies the confirmation itself.
export async function completeSimulatedPayment(accessToken: string, paymentId: string, token: string, approve: boolean) {
  await postChatJson<unknown>(accessToken, `/api/payments/simulated/${encodeURIComponent(paymentId)}/complete`, { token, approve });
}

export async function getProviderRequest(accessToken: string, requestId: string) {
  return authenticatedApiFetch(
    `/api/provider/requests/${encodeURIComponent(requestId)}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { headers: { Accept: "application/json" } },
  );
}

export async function decideProviderRequest(requestId: string, decision: "accept" | "reject", accessToken: string) {
  return authenticatedApiFetch(
    `/api/provider/requests/${encodeURIComponent(requestId)}/${decision}`,
    accessToken,
    process.env.NEXT_PUBLIC_API_URL,
    { method: "POST", headers: { Accept: "application/json" } },
  );
}

export function getServices(filters: ServiceFilters, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(filters.offset) });
  addNonEmpty(params, "q", filters.q);
  addNonEmpty(params, "serviceType", filters.serviceType);
  addNonEmpty(params, "regionCode", filters.regionCode);
  addNonEmpty(params, "communeCode", filters.communeCode);
  return getJson<PagedResponse<ServiceProfile>>(`/api/services?${params.toString()}`, signal);
}

export function getSharedRoutes(filters: SharedRouteFilters, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(filters.offset) });
  addNonEmpty(params, "originCommuneCode", filters.originCommuneCode);
  addNonEmpty(params, "destinationCommuneCode", filters.destinationCommuneCode);
  addNonEmpty(params, "departureFrom", dateBoundary(filters.departureFrom, "00:00:00"));
  addNonEmpty(params, "departureTo", dateBoundary(filters.departureTo, "23:59:59.999"));
  return getJson<PagedResponse<SharedRoute>>(`/api/shared-routes?${params.toString()}`, signal);
}

function dateBoundary(date: string, time: string) {
  if (!date) return "";
  const reference = new Date(`${date}T12:00:00Z`);
  const offsetPart = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Santiago",
    timeZoneName: "longOffset",
  }).formatToParts(reference).find((part) => part.type === "timeZoneName")?.value;
  const offset = offsetPart === "GMT" ? "+00:00" : offsetPart?.replace(/^GMT/, "") ?? "";
  return `${date}T${time}${offset}`;
}
