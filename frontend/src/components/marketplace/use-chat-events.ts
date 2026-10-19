"use client";

import { useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";
import { resolveApiBaseUrl } from "@/lib/auth/account-api";
import {
  chatEventsBackoffMs,
  createChatEventParser,
  parseChatEvent,
  parseChatStreamState,
  type ChatEvent,
} from "@/lib/chat-events";
import { CHAT_ROOT_KEY, chatListKey, chatThreadKey, chatUnreadTotalKey } from "@/lib/chats";
import { currentAccessToken, isSignInRequired } from "@/lib/provider-request-access";

type ChatEventListener = (event: ChatEvent) => void;

// One stream per browser tab, shared by every mounted view. The first subscriber opens it and the last one closes it.
const listeners = new Set<ChatEventListener>();
const statusListeners = new Set<() => void>();
let connection: { controller: AbortController } | null = null;
let connected = false;

function setConnected(value: boolean) {
  if (connected === value) return;
  connected = value;
  statusListeners.forEach((notify) => notify());
}

// A loop that was aborted must not overwrite the state of the connection that replaced it.
function setConnectionStatus(value: boolean, signal: AbortSignal) {
  if (!signal.aborted) setConnected(value);
}

function subscribeStatus(notify: () => void) {
  statusListeners.add(notify);
  return () => {
    statusListeners.delete(notify);
  };
}

// Full jitter halves the delay at most, so the 30 s cap is never exceeded.
function reconnectDelayMs(attempt: number) {
  return chatEventsBackoffMs(attempt, (ms) => ms * (0.5 + Math.random() / 2));
}

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

// Opens one stream with the current token, in the Authorization header. Resolves false when the server refuses it.
async function readStream(signal: AbortSignal): Promise<boolean> {
  const token = await currentAccessToken();
  const url = `${resolveApiBaseUrl(process.env.NEXT_PUBLIC_API_URL)}/api/chats/events`;
  const response = await fetch(url, {
    headers: { Accept: "text/event-stream", Authorization: `Bearer ${token}` },
    cache: "no-store",
    signal,
  });
  if (!response.ok || !response.body) return false;

  const parser = createChatEventParser((frame) => {
    // An accepted stream is not proof that events flow: only the server's "ready" frame marks the connection live.
    const state = parseChatStreamState(frame);
    if (state) {
      setConnectionStatus(state === "ready", signal);
      return;
    }
    const event = parseChatEvent(frame);
    if (event) listeners.forEach((listener) => listener(event));
  });
  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return true;
    parser.push(decoder.decode(value, { stream: true }));
  }
}

// Reconnects after the stream ends or fails, with a fresh token each time. Stops when signed out or aborted.
async function runConnection(signal: AbortSignal) {
  let attempt = 0;
  while (!signal.aborted) {
    let accepted = false;
    try {
      accepted = await readStream(signal);
    } catch (cause) {
      if (signal.aborted) return;
      if (isSignInRequired(cause)) {
        setConnectionStatus(false, signal);
        return;
      }
    }
    setConnectionStatus(false, signal);
    if (signal.aborted) return;
    // A stream the server accepted and later closed (for example at token expiry) starts over at the first delay.
    if (accepted) attempt = 0;
    await sleep(reconnectDelayMs(attempt), signal);
    attempt += 1;
  }
}

// Other subscribers (the in-app notifier) share the same stream and the same tick.
export function subscribeChatEvents(listener: ChatEventListener) {
  listeners.add(listener);
  if (!connection) {
    const controller = new AbortController();
    connection = { controller };
    void runConnection(controller.signal).finally(() => {
      if (connection?.controller === controller) connection = null;
    });
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size > 0 || !connection) return;
    connection.controller.abort();
    connection = null;
    setConnected(false);
  };
}

// Every subscriber hears the same event in the same tick. Their invalidations are merged so each query refetches once.
type InvalidationBatch = { keys: Map<string, QueryKey>; done: Promise<void> };
const pendingInvalidations = new Map<QueryClient, InvalidationBatch>();

// Resolves once the merged invalidations have refetched, so a subscriber can read the refreshed cache.
export function invalidateChatQueriesOnce(queryClient: QueryClient, queryKey: QueryKey): Promise<void> {
  let batch = pendingInvalidations.get(queryClient);
  if (!batch) {
    const keys = new Map<string, QueryKey>();
    const done = Promise.resolve().then(async () => {
      pendingInvalidations.delete(queryClient);
      await Promise.all([...keys.values()].map((key) => queryClient.invalidateQueries({ queryKey: key })));
    });
    batch = { keys, done };
    pendingInvalidations.set(queryClient, batch);
  }
  batch.keys.set(JSON.stringify(queryKey), queryKey);
  return batch.done;
}

// Subscribes the view to chat events for the signed-in user and returns whether the stream is connected.
// Each event refetches the chat list and the thread of the chat it names.
export function useChatEvents(userId: string | null | undefined): boolean {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!userId) return;
    // Events published while the stream was down are not replayed, so each transition to ready resyncs every chat query.
    const unsubscribeStatus = subscribeStatus(() => {
      if (connected) invalidateChatQueriesOnce(queryClient,CHAT_ROOT_KEY);
    });
    const unsubscribeEvents = subscribeChatEvents((event) => {
      // chat.read only changes unread state, so the open thread keeps its data.
      invalidateChatQueriesOnce(queryClient,chatListKey(userId));
      invalidateChatQueriesOnce(queryClient,chatUnreadTotalKey(userId));
      if (event.kind !== "chat.read") invalidateChatQueriesOnce(queryClient,chatThreadKey(userId, event.chatId));
    });
    return () => {
      unsubscribeStatus();
      unsubscribeEvents();
    };
  }, [queryClient, userId]);

  return useSyncExternalStore(subscribeStatus, () => connected, () => false);
}
