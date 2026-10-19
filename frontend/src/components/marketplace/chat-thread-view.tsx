"use client";

import Link from "next/link";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ChatAttachmentImage } from "@/components/marketplace/chat-attachment-image";
import { ChatComposer } from "@/components/marketplace/chat-composer";
import { ChatErrorState } from "@/components/marketplace/chat-error-state";
import { ChatQuotationCard } from "@/components/marketplace/chat-quotation-card";
import { QuotationDialog } from "@/components/marketplace/quotation-dialog";
import { CHAT_THREAD_LAYOUT, MarketplaceSkeleton } from "@/components/marketplace/marketplace-skeleton";
import { useChatEvents } from "@/components/marketplace/use-chat-events";
import { useNavUserId } from "@/components/marketplace/site-navigation";
import {
  CHAT_MESSAGE_PAGE_SIZE,
  ChatRequestError,
  chatHref,
  chatListKey,
  chatRouteLabel,
  chatThreadKey,
  counterpartKindLabel,
  nextMessagesBefore,
  orderTimelineOldestFirst,
} from "@/lib/chats";
import { chatRefetchInterval } from "@/lib/chat-quotations";
import { getChatMessages } from "@/lib/marketplace-api";
import { currentAccessToken, ProviderRequestAccessError } from "@/lib/provider-request-access";

const timeFormatter = new Intl.DateTimeFormat("es-CL", { hour: "2-digit", minute: "2-digit", timeZone: "America/Santiago" });

// Same view for customers and providers. The chat stream pushes new messages; polling only runs while it is disconnected.
export function ChatThreadView({ chatId }: { chatId: string }) {
  const { userId, pending: sessionPending } = useNavUserId();
  const streamConnected = useChatEvents(userId);
  const queryClient = useQueryClient();
  const threadQuery = useInfiniteQuery({
    queryKey: chatThreadKey(userId ?? "", chatId),
    queryFn: async ({ pageParam }) => getChatMessages(await currentAccessToken(), chatId, { limit: CHAT_MESSAGE_PAGE_SIZE, before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (_lastPage, pages) => nextMessagesBefore(pages),
    enabled: Boolean(userId),
    retry: false,
    refetchInterval: chatRefetchInterval(streamConnected),
  });

  const pages = threadQuery.data?.pages ?? [];
  const chat = pages[0]?.chat;
  const timeline = orderTimelineOldestFirst(pages);
  const lastEntry = timeline[timeline.length - 1];
  const lastEntryId = lastEntry?.kind === "message" ? lastEntry.messageId : lastEntry?.quotation.quotationId;
  const viewerRole = pages[0]?.viewerRole;
  const endRef = useRef<HTMLDivElement>(null);
  const [quotationOpen, setQuotationOpen] = useState(false);
  // A new message or quotation changes both the thread and the list preview.
  const refreshThread = () => {
    void queryClient.invalidateQueries({ queryKey: chatThreadKey(userId ?? "", chatId) });
    void queryClient.invalidateQueries({ queryKey: chatListKey(userId ?? "") });
  };

  // Opens the conversation at its latest message. Loading older pages keeps the last message, so it does not jump.
  useEffect(() => {
    if (lastEntryId) endRef.current?.scrollIntoView({ block: "end" });
  }, [lastEntryId]);

  const notFound = threadQuery.error instanceof ChatRequestError && threadQuery.error.status === 404;
  const loading = sessionPending || (Boolean(userId) && threadQuery.isPending);
  const signedOut = !userId && !sessionPending;

  return (
    <article aria-labelledby="chat-thread-title" className="chat-wrap">
      <Link className="chat-back" href="/mensajes"><ArrowLeft aria-hidden="true" size={16} /> Volver a mensajes</Link>

      {signedOut && (
        <ChatErrorState error={new ProviderRequestAccessError("sign-in")} nextPath={chatHref(chatId)} onRetry={() => void threadQuery.refetch()} />
      )}

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

      {!signedOut && !notFound && !threadQuery.isError && (
        <MarketplaceSkeleton label="Cargando la conversación…" layout={CHAT_THREAD_LAYOUT} loading={loading} name="chat-thread">
          {chat && (
            <header className="chat-thread-header">
              <h1 id="chat-thread-title">{chat.counterpart.name}</h1>
              <p className="chat-card-meta">{counterpartKindLabel(chat.counterpart.kind)} · {chat.serviceName}</p>
              <p className="chat-card-meta">{chatRouteLabel(chat)}</p>
              {viewerRole === "provider" && (
                <button className="button button-primary chat-quotation-trigger" onClick={() => setQuotationOpen(true)} type="button">
                  Enviar cotización
                </button>
              )}
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

          {threadQuery.isSuccess && timeline.length === 0 ? (
            <div className="marketplace-state marketplace-empty" role="status">
              <h2>Aún no hay mensajes en esta conversación</h2>
            </div>
          ) : (
            <ol aria-label="Mensajes" className="chat-thread">
              {timeline.map((entry) => entry.kind === "message" ? (
                <li className={entry.fromMe ? "chat-message chat-message-own" : "chat-message"} key={entry.messageId}>
                  {!entry.fromMe && <p className="chat-message-sender">{entry.senderName}</p>}
                  {entry.attachment && <ChatAttachmentImage chatId={chatId} messageId={entry.messageId} senderName={entry.senderName} />}
                  {entry.content && <p className="chat-message-content">{entry.content}</p>}
                  <time dateTime={entry.sentAt}>{timeFormatter.format(new Date(entry.sentAt))}</time>
                </li>
              ) : (
                <li className="chat-timeline-quotation" key={entry.quotation.quotationId}>
                  <ChatQuotationCard onChanged={refreshThread} quotation={entry.quotation} viewerRole={viewerRole ?? "customer"} />
                </li>
              ))}
            </ol>
          )}
          <div ref={endRef} />

          {quotationOpen && (
            <QuotationDialog
              chatId={chatId}
              onClose={() => setQuotationOpen(false)}
              onCreated={refreshThread}
            />
          )}

          {chat && (
            <ChatComposer chatId={chatId} onSent={refreshThread} />
          )}
        </MarketplaceSkeleton>
      )}
    </article>
  );
}
