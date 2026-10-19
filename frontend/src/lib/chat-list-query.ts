import { CHAT_LIST_PAGE_SIZE, chatListKey, nextChatListOffset } from "@/lib/chats";
import { getChats } from "@/lib/marketplace-api";
import { currentAccessToken } from "@/lib/provider-request-access";

// Key, page fetcher and paging of the chat list. The list view and the in-app notifier share it, so they share one cache entry.
export function chatListQueryOptions(userId: string) {
  return {
    queryKey: chatListKey(userId),
    queryFn: async ({ pageParam }: { pageParam: number }) =>
      getChats(await currentAccessToken(), { limit: CHAT_LIST_PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: nextChatListOffset,
  };
}
