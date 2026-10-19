// Pure rules for the in-app chat toasts. Keep runtime imports free so node unit tests can load this module.
import type { ChatEvent } from "@/lib/chat-events";
import type { ChatSummary } from "@/lib/chats";

// Only events that announce something to the user; chat.read only updates unread state.
export type ChatNotifiableEvent = Extract<ChatEvent, { kind: "message.created" | "quotation.changed" }>;

export type ChatToast = { id: string; title: string; description?: string };

const OPEN_CHAT_PATH = /^\/mensajes\/([^/]+)\/?$/;

// Same id for a chat means a newer toast replaces the older one.
export function chatToastId(chatId: string): string {
  return `chat-${chatId}`;
}

// Notifies for the other participant's events, except while the user is reading that chat with the tab visible.
export function shouldNotify(event: ChatEvent, pathname: string, visible: boolean): boolean {
  if (event.kind === "chat.read" || event.fromMe) return false;
  const openChat = OPEN_CHAT_PATH.exec(pathname)?.[1];
  const readingThisChat = visible && openChat === encodeURIComponent(event.chatId);
  return !readingThisChat;
}

// `chat` is the chat's entry in the loaded list pages; without it the copy stays generic.
export function buildChatToast(event: ChatNotifiableEvent, chat: ChatSummary | undefined): ChatToast {
  const id = chatToastId(event.chatId);
  if (event.kind === "quotation.changed") {
    if (!chat) return { id, title: "Tienes una actualización de cotización" };
    return { id, title: `Actualización de cotización de ${chat.counterpart.name}` };
  }
  if (!chat) return { id, title: "Tienes un mensaje nuevo" };
  const description = chat.lastMessage?.content;
  return { id, title: `Nuevo mensaje de ${chat.counterpart.name}`, ...(description ? { description } : {}) };
}
