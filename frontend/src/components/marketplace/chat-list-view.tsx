"use client";

import Link from "next/link";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ChatErrorState } from "@/components/marketplace/chat-error-state";
import { CHAT_LIST_LAYOUT, MarketplaceSkeleton } from "@/components/marketplace/marketplace-skeleton";
import { useNavUserId } from "@/components/marketplace/site-navigation";
import {
  CHAT_LIST_PAGE_SIZE,
  chatHref,
  chatListKey,
  chatRouteLabel,
  counterpartKindLabel,
  formatChatRelativeTime,
  lastMessageLabel,
  nextChatListOffset,
  type ChatSummary,
} from "@/lib/chats";
import { getChats } from "@/lib/marketplace-api";
import { currentAccessToken } from "@/lib/provider-request-access";

// Same view for customers and providers: the counterpart is labelled by its kind.
export function ChatListView() {
  const { userId, pending: sessionPending } = useNavUserId();
  const chatsQuery = useInfiniteQuery({
    queryKey: chatListKey(userId ?? ""),
    queryFn: async ({ pageParam }) => getChats(await currentAccessToken(), { limit: CHAT_LIST_PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: nextChatListOffset,
    enabled: Boolean(userId),
    retry: false,
  });

  const chats = chatsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const loading = sessionPending || (Boolean(userId) && chatsQuery.isPending);
  const now = new Date();

  return (
    <section aria-labelledby="chat-list-title" className="chat-wrap">
      <div className="chat-heading">
        <h1 id="chat-list-title">Mensajes</h1>
      </div>

      {!userId && !sessionPending && (
        <div className="marketplace-state">
          <p role="alert">Inicia sesión para ver tus mensajes.</p>
          <Link className="button button-primary" href={`/login?next=${encodeURIComponent("/mensajes")}`}>Iniciar sesión</Link>
        </div>
      )}
      {chatsQuery.isError && (
        <ChatErrorState error={chatsQuery.error} nextPath="/mensajes" onRetry={() => void chatsQuery.refetch()} />
      )}

      {!chatsQuery.isError && (
        <MarketplaceSkeleton label="Cargando tus mensajes…" layout={CHAT_LIST_LAYOUT} loading={loading} name="chat-list">
          {chatsQuery.isSuccess && chats.length === 0 ? (
            <div className="marketplace-state marketplace-empty" role="status">
              <h2>Aún no tienes conversaciones</h2>
              <p>Cuando una solicitud sea aceptada, la conversación aparecerá aquí.</p>
            </div>
          ) : (
            <ul className="chat-list">
              {chats.map((chat) => (
                <li key={chat.chatId}>
                  <ChatCard chat={chat} now={now} />
                </li>
              ))}
            </ul>
          )}
        </MarketplaceSkeleton>
      )}

      {chatsQuery.hasNextPage && (
        <div className="chat-more">
          <button
            className="button button-secondary"
            disabled={chatsQuery.isFetchingNextPage}
            onClick={() => void chatsQuery.fetchNextPage()}
            type="button"
          >
            {chatsQuery.isFetchingNextPage ? "Cargando…" : "Cargar más"}
          </button>
        </div>
      )}
    </section>
  );
}

function ChatCard({ chat, now }: { chat: ChatSummary; now: Date }) {
  const titleId = `chat-${chat.chatId}-title`;
  const lastMessage = chat.lastMessage;
  return (
    <article aria-labelledby={titleId} className="chat-card">
      <Link className="chat-card-link" href={chatHref(chat.chatId)}>
        <div className="chat-card-top">
          <h2 id={titleId}>{chat.counterpart.name}</h2>
          {lastMessage && <time className="chat-card-time" dateTime={lastMessage.sentAt}>{formatChatRelativeTime(lastMessage.sentAt, now)}</time>}
        </div>
        <p className="chat-card-meta">
          {counterpartKindLabel(chat.counterpart.kind)} · {chat.serviceName}
        </p>
        <p className="chat-card-meta">{chatRouteLabel(chat)}</p>
        <p className={lastMessage ? "chat-card-preview" : "chat-card-preview chat-card-preview-empty"}>{lastMessageLabel(lastMessage)}</p>
      </Link>
    </article>
  );
}
