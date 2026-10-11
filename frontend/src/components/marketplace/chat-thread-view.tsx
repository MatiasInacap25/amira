"use client";

import Link from "next/link";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useRef } from "react";
import { ChatErrorState } from "@/components/marketplace/chat-error-state";
import { CHAT_THREAD_LAYOUT, MarketplaceSkeleton } from "@/components/marketplace/marketplace-skeleton";
import { useNavUserId } from "@/components/marketplace/site-navigation";
import {
  CHAT_MESSAGE_PAGE_SIZE,
  ChatRequestError,
  chatHref,
  chatRouteLabel,
  chatThreadKey,
  counterpartKindLabel,
  nextMessagesBefore,
  orderMessagesOldestFirst,
} from "@/lib/chats";
import { getChatMessages } from "@/lib/marketplace-api";
import { currentAccessToken } from "@/lib/provider-request-access";

const timeFormatter = new Intl.DateTimeFormat("es-CL", { hour: "2-digit", minute: "2-digit", timeZone: "America/Santiago" });

// Same view for customers and providers. Messages are read-only until sending ships.
export function ChatThreadView({ chatId }: { chatId: string }) {
  const { userId, pending: sessionPending } = useNavUserId();
  const threadQuery = useInfiniteQuery({
    queryKey: chatThreadKey(userId ?? "", chatId),
    queryFn: async ({ pageParam }) => getChatMessages(await currentAccessToken(), chatId, { limit: CHAT_MESSAGE_PAGE_SIZE, before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (_lastPage, pages) => nextMessagesBefore(pages),
    enabled: Boolean(userId),
    retry: false,
  });

  const pages = threadQuery.data?.pages ?? [];
  const chat = pages[0]?.chat;
  const messages = orderMessagesOldestFirst(pages);
  const lastMessageId = messages[messages.length - 1]?.messageId;
  const endRef = useRef<HTMLDivElement>(null);

  // Opens the conversation at its latest message. Loading older pages keeps the last message, so it does not jump.
  useEffect(() => {
    if (lastMessageId) endRef.current?.scrollIntoView({ block: "end" });
  }, [lastMessageId]);

  const notFound = threadQuery.error instanceof ChatRequestError && threadQuery.error.status === 404;
  const loading = sessionPending || (Boolean(userId) && threadQuery.isPending);

  return (
    <article aria-labelledby="chat-thread-title" className="chat-wrap">
      <Link className="chat-back" href="/mensajes"><ArrowLeft aria-hidden="true" size={16} /> Volver a mensajes</Link>

      {notFound && (
        <div className="marketplace-state marketplace-empty" role="status">
          <h1 id="chat-thread-title">No encontramos esta conversación</h1>
          <p>Es posible que ya no exista o que no tengas acceso a ella.</p>
          <Link className="button button-secondary" href="/mensajes">Ver mis mensajes</Link>
        </div>
      )}
      {!notFound && threadQuery.isError && (
        <ChatErrorState error={threadQuery.error} nextPath={chatHref(chatId)} onRetry={() => void threadQuery.refetch()} />
      )}

      {!notFound && !threadQuery.isError && (
        <MarketplaceSkeleton label="Cargando la conversación…" layout={CHAT_THREAD_LAYOUT} loading={loading} name="chat-thread">
          {chat && (
            <header className="chat-thread-header">
              <h1 id="chat-thread-title">{chat.counterpart.name}</h1>
              <p className="chat-card-meta">{counterpartKindLabel(chat.counterpart.kind)} · {chat.serviceName}</p>
              <p className="chat-card-meta">{chatRouteLabel(chat)}</p>
            </header>
          )}

          {threadQuery.hasNextPage && (
            <div className="chat-more">
              <button
                className="button button-secondary"
                disabled={threadQuery.isFetchingNextPage}
                onClick={() => void threadQuery.fetchNextPage()}
                type="button"
              >
                {threadQuery.isFetchingNextPage ? "Cargando…" : "Ver mensajes anteriores"}
              </button>
            </div>
          )}

          {threadQuery.isSuccess && messages.length === 0 ? (
            <div className="marketplace-state marketplace-empty" role="status">
              <h2>Aún no hay mensajes en esta conversación</h2>
            </div>
          ) : (
            <ol aria-label="Mensajes" className="chat-thread">
              {messages.map((message) => (
                <li className={message.fromMe ? "chat-message chat-message-own" : "chat-message"} key={message.messageId}>
                  {!message.fromMe && <p className="chat-message-sender">{message.senderName}</p>}
                  <p className="chat-message-content">{message.content}</p>
                  <time dateTime={message.sentAt}>{timeFormatter.format(new Date(message.sentAt))}</time>
                </li>
              ))}
            </ol>
          )}
          <div ref={endRef} />

          <p className="chat-composer-note">El envío de mensajes estará disponible próximamente.</p>
        </MarketplaceSkeleton>
      )}
    </article>
  );
}
