"use client";

import { useQueryClient, type InfiniteData, type QueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { invalidateChatQueriesOnce, subscribeChatEvents } from "@/components/marketplace/use-chat-events";
import { chatListQueryOptions } from "@/lib/chat-list-query";
import { buildChatToast, shouldNotify, type ChatNotifiableEvent } from "@/lib/chat-notifications";
import { chatHref, chatListKey, type ChatListPage, type ChatSummary } from "@/lib/chats";

function findChat(data: InfiniteData<ChatListPage> | undefined, chatId: string): ChatSummary | undefined {
  return data?.pages.flatMap((page) => page.items).find((item) => item.chatId === chatId);
}

// The chat as of this event, or undefined when it is not on the fresh first page or the read fails.
// A mounted list refetches through the shared invalidation; an unmounted one is fetched here, so no older preview is shown.
async function freshChatAfterEvent(
  queryClient: QueryClient,
  userId: string,
  chatId: string,
  eventAt: number,
): Promise<ChatSummary | undefined> {
  const key = chatListKey(userId);
  try {
    if (queryClient.getQueryCache().find({ queryKey: key, type: "active" })) {
      await invalidateChatQueriesOnce(queryClient, key);
      const state = queryClient.getQueryState<InfiniteData<ChatListPage>>(key);
      if (state?.status !== "success" || state.dataUpdatedAt < eventAt) return undefined;
      return findChat(state.data, chatId);
    }
    // pages: 1 keeps the cache shape the list reads.
    const data = await queryClient.fetchInfiniteQuery({ ...chatListQueryOptions(userId), pages: 1, staleTime: 0 });
    return findChat(data, chatId);
  } catch {
    return undefined;
  }
}

// Toasts the other participant's messages and quotation changes on any page. Mounted once in the header,
// so it renders nothing and is inactive for signed-out visitors.
export function ChatNotifications({ userId }: { userId: string | null }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const pathnameRef = useRef(pathname);

  useEffect(() => {
    pathnameRef.current = pathname;
  }, [pathname]);

  useEffect(() => {
    if (!userId) return;
    return subscribeChatEvents((event) => {
      if (event.kind === "chat.read") return;
      if (!shouldNotify(event, pathnameRef.current, document.visibilityState === "visible")) return;
      const notifiable: ChatNotifiableEvent = event;
      const eventAt = Date.now();
      void freshChatAfterEvent(queryClient, userId, notifiable.chatId, eventAt).then((chat) => {
        const copy = buildChatToast(notifiable, chat);
        toast(copy.title, {
          id: copy.id,
          description: copy.description,
          action: { label: "Ver", onClick: () => router.push(chatHref(notifiable.chatId)) },
        });
      });
    });
  }, [queryClient, router, userId]);

  return null;
}
