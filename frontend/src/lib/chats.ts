// Pure rules and API types for the chat list and chat view. Keep this module free of imports so node unit tests can load it.

export const CHAT_LIST_PAGE_SIZE = 20;
export const CHAT_MESSAGE_PAGE_SIZE = 50;
export const NO_LAST_MESSAGE_LABEL = "Sin mensajes aún";

export type CounterpartKind = "customer" | "company" | "independent_driver";

export type ChatCounterpart = {
  name: string;
  kind: CounterpartKind;
  providerProfileId: string | null;
};

export type ChatLastMessage = {
  content: string;
  sentAt: string;
  fromMe: boolean;
};

export type ChatHeader = {
  chatId: string;
  requestId: string;
  createdAt: string;
  serviceName: string;
  originCommuneName: string;
  destinationCommuneName: string | null;
  counterpart: ChatCounterpart;
};

export type ChatSummary = ChatHeader & {
  lastMessage: ChatLastMessage | null;
};

export type ChatListPage = {
  items: ChatSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type ChatMessage = {
  messageId: string;
  content: string;
  sentAt: string;
  fromMe: boolean;
  senderName: string;
};

export type ChatViewerRole = "customer" | "provider";

export type QuotationStatus = "pending" | "paid" | "rejected" | "expired" | "superseded";

export type ChatQuotation = {
  quotationId: string;
  status: QuotationStatus;
  amount: number;
  currency: "CLP";
  serviceAt: string;
  description: string;
  expiresAt: string;
  createdAt: string;
  paidAt: string | null;
};

export type ChatTimelineEntry =
  | ({ kind: "message" } & ChatMessage)
  | { kind: "quotation"; quotation: ChatQuotation };

// Payload of GET /api/chats/{id}/messages: the header fields sit flat at the top level.
export type BackendChatMessagesPage = ChatHeader & {
  viewerRole: ChatViewerRole;
  timeline: ChatTimelineEntry[];
  nextBefore: string | null;
};

// View shape: the header is nested under `chat`; `timeline` runs oldest to newest within the page.
// `nextBefore` is an opaque cursor for the next older page, null when no more messages exist.
export type ChatMessagesPage = {
  chat: ChatHeader;
  timeline: ChatTimelineEntry[];
  hasMore: boolean;
  nextBefore: string | null;
  viewerRole: ChatViewerRole;
};

export function adaptChatMessagesPage(page: BackendChatMessagesPage): ChatMessagesPage {
  const { chatId, requestId, createdAt, serviceName, originCommuneName, destinationCommuneName, counterpart } = page;
  return {
    chat: { chatId, requestId, createdAt, serviceName, originCommuneName, destinationCommuneName, counterpart },
    timeline: page.timeline,
    hasMore: page.nextBefore !== null,
    nextBefore: page.nextBefore,
    viewerRole: page.viewerRole,
  };
}

export const CHAT_ROOT_KEY = ["chats"] as const;

export function chatListKey(userId: string) {
  return [...CHAT_ROOT_KEY, "list", userId] as const;
}

export function chatThreadKey(userId: string, chatId: string) {
  return [...CHAT_ROOT_KEY, "thread", userId, chatId] as const;
}

// Stops on an empty page so a total/items mismatch cannot cause endless requests.
export function nextChatListOffset(page: { offset: number; items: readonly unknown[]; total: number }): number | undefined {
  if (page.items.length === 0) return undefined;
  const nextOffset = page.offset + page.items.length;
  return nextOffset < page.total ? nextOffset : undefined;
}

// Pages are fetched newest first. The server cursor breaks timestamp ties, so no message is skipped.
export function nextMessagesBefore(pages: readonly ChatMessagesPage[]): string | undefined {
  const oldest = pages[pages.length - 1];
  if (!oldest?.hasMore || !oldest.nextBefore) return undefined;
  return oldest.nextBefore;
}

// Pages are fetched newest first, so reversing them puts the oldest timeline entries first.
export function orderTimelineOldestFirst(pages: readonly ChatMessagesPage[]): ChatTimelineEntry[] {
  return [...pages].reverse().flatMap((page) => page.timeline);
}

export function chatHref(chatId: string): string {
  return `/mensajes/${encodeURIComponent(chatId)}`;
}

export function counterpartKindLabel(kind: CounterpartKind): string {
  if (kind === "customer") return "Cliente";
  if (kind === "company") return "Empresa";
  return "Conductor independiente";
}

export function lastMessageLabel(lastMessage: ChatLastMessage | null): string {
  if (!lastMessage) return NO_LAST_MESSAGE_LABEL;
  return lastMessage.fromMe ? `Tú: ${lastMessage.content}` : lastMessage.content;
}

export function chatRouteLabel(chat: { originCommuneName: string; destinationCommuneName: string | null }): string {
  const destination = chat.destinationCommuneName?.trim() || "Destino no indicado";
  return `${chat.originCommuneName} → ${destination}`;
}

const SANTIAGO_DATE = new Intl.DateTimeFormat("es-CL", { day: "numeric", month: "short", timeZone: "America/Santiago" });
const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

// Relative labels for the chat list. Messages older than a week show a short calendar date.
export function formatChatRelativeTime(sentAt: string, now: Date): string {
  const elapsed = now.getTime() - new Date(sentAt).getTime();
  if (elapsed < MINUTE_MS) return "ahora";
  if (elapsed < HOUR_MS) return `hace ${Math.floor(elapsed / MINUTE_MS)} min`;
  if (elapsed < DAY_MS) return `hace ${Math.floor(elapsed / HOUR_MS)} h`;
  if (elapsed < 2 * DAY_MS) return "ayer";
  if (elapsed < 7 * DAY_MS) return `hace ${Math.floor(elapsed / DAY_MS)} días`;
  return SANTIAGO_DATE.format(new Date(sentAt));
}

// Carries the HTTP status so the view can tell "not found" from a failed request.
export class ChatRequestError extends Error {
  readonly status: number;
  readonly detailType: string | null;
  readonly detailMessage: string | null;

  constructor(status: number, detail: { type: string | null; msg: string | null } = { type: null, msg: null }) {
    super(`Chat request failed (${status})`);
    this.name = "ChatRequestError";
    this.status = status;
    this.detailType = detail.type;
    this.detailMessage = detail.msg;
  }
}

export function chatAccessMessage(reason: "sign-in" | "aal2" | "session"): string {
  if (reason === "sign-in") return "Inicia sesión con tu correo confirmado para ver tus mensajes.";
  if (reason === "aal2") return "Verifica tu teléfono por SMS para ver tus mensajes.";
  return "Tu sesión expiró. Inicia sesión nuevamente para continuar.";
}
