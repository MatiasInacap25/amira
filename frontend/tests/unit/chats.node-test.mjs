import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  adaptChatMessagesPage,
  CHAT_ROOT_KEY,
  chatHref,
  chatListKey,
  chatRouteLabel,
  chatThreadKey,
  counterpartKindLabel,
  formatChatRelativeTime,
  lastMessageLabel,
  nextChatListOffset,
  nextMessagesBefore,
  orderTimelineOldestFirst,
} from "../../src/lib/chats.ts";

const NOW = new Date("2026-10-11T15:00:00.000Z");

function minutesAgo(minutes) {
  return new Date(NOW.getTime() - minutes * 60_000).toISOString();
}

function messageEntry(messageId, sentAt) {
  return { kind: "message", messageId, content: messageId, sentAt, fromMe: false, senderName: "Ana" };
}

test("returns the next chat offset while more chats remain", () => {
  assert.equal(nextChatListOffset({ offset: 0, total: 45, items: new Array(20) }), 20);
  assert.equal(nextChatListOffset({ offset: 40, total: 45, items: new Array(5) }), undefined);
});

test("stops on an empty chat page even when total says more exist", () => {
  assert.equal(nextChatListOffset({ offset: 0, total: 45, items: [] }), undefined);
});

test("formats relative times in Spanish for recent and older messages", () => {
  assert.equal(formatChatRelativeTime(minutesAgo(0.5), NOW), "ahora");
  assert.equal(formatChatRelativeTime(minutesAgo(5), NOW), "hace 5 min");
  assert.equal(formatChatRelativeTime(minutesAgo(180), NOW), "hace 3 h");
  assert.equal(formatChatRelativeTime(minutesAgo(60 * 24 + 30), NOW), "ayer");
  assert.equal(formatChatRelativeTime(minutesAgo(60 * 24 * 3), NOW), "hace 3 días");
});

test("uses a calendar date label for messages older than a week", () => {
  const label = formatChatRelativeTime(minutesAgo(60 * 24 * 30), NOW);
  assert.notEqual(label, "");
  assert.doesNotMatch(label, /^hace /);
});

test("labels the counterpart kind for both sides of the chat", () => {
  assert.equal(counterpartKindLabel("customer"), "Cliente");
  assert.equal(counterpartKindLabel("company"), "Empresa");
  assert.equal(counterpartKindLabel("independent_driver"), "Conductor independiente");
});

test("previews the last message with a sender prefix only for own messages", () => {
  assert.equal(lastMessageLabel(null), "Sin mensajes aún");
  assert.equal(lastMessageLabel({ content: "Hola", sentAt: minutesAgo(1), fromMe: true }), "Tú: Hola");
  assert.equal(lastMessageLabel({ content: "Hola", sentAt: minutesAgo(1), fromMe: false }), "Hola");
});

test("describes the route with fallbacks for missing communes", () => {
  assert.equal(
    chatRouteLabel({ originCommuneName: "Santiago", destinationCommuneName: "Valparaíso" }),
    "Santiago → Valparaíso",
  );
  assert.equal(
    chatRouteLabel({ originCommuneName: "Santiago", destinationCommuneName: null }),
    "Santiago → Destino no indicado",
  );
});

test("encodes the chat id in its href", () => {
  assert.equal(chatHref("abc/1"), "/mensajes/abc%2F1");
});

test("scopes chat query keys by user and keeps them under the chat root", () => {
  assert.notDeepEqual(chatListKey("user-a"), chatListKey("user-b"));
  assert.notDeepEqual(chatThreadKey("user-a", "chat-1"), chatThreadKey("user-a", "chat-2"));
  assert.deepEqual(chatListKey("user-a").slice(0, CHAT_ROOT_KEY.length), [...CHAT_ROOT_KEY]);
  assert.deepEqual(chatThreadKey("user-a", "chat-1").slice(0, CHAT_ROOT_KEY.length), [...CHAT_ROOT_KEY]);
});

test("uses the server nextBefore cursor of the last fetched page", () => {
  const latest = { chat: {}, hasMore: true, nextBefore: "older-cursor", viewerRole: "customer", timeline: [messageEntry("m3", "2026-10-11T12:00:00.000Z"), messageEntry("m4", "2026-10-11T13:00:00.000Z")] };
  const older = { chat: {}, hasMore: true, nextBefore: "oldest-cursor", viewerRole: "customer", timeline: [messageEntry("m1", "2026-10-10T09:00:00.000Z")] };
  assert.equal(nextMessagesBefore([latest, older]), "oldest-cursor");
});

test("has no before cursor once the server reports no more messages", () => {
  const oldest = { chat: {}, hasMore: false, nextBefore: null, viewerRole: "customer", timeline: [messageEntry("m1", "2026-10-10T09:00:00.000Z")] };
  assert.equal(nextMessagesBefore([oldest]), undefined);
});

const backendThreadPage = JSON.parse(readFileSync(new URL("../fixtures/chat-messages-page.json", import.meta.url), "utf8"));

test("adapts the backend thread page into the header object the views use", () => {
  const page = adaptChatMessagesPage(backendThreadPage);

  assert.equal(page.chat.chatId, backendThreadPage.chatId);
  assert.equal(page.chat.serviceName, "Mudanzas");
  assert.equal(page.chat.originCommuneName, "Santiago");
  assert.equal(page.chat.destinationCommuneName, "Valparaíso");
  assert.deepEqual(page.chat.counterpart, backendThreadPage.counterpart);
  assert.equal(page.viewerRole, "customer");
  assert.equal(page.timeline.length, 4);
  assert.equal(page.timeline[1].kind, "quotation");
  assert.equal(page.nextBefore, backendThreadPage.nextBefore);
});

test("passes the image attachment through unchanged and keeps null for text-only messages", () => {
  const page = adaptChatMessagesPage(backendThreadPage);
  const imageEntry = backendThreadPage.timeline[2];

  assert.deepEqual(page.timeline[2], imageEntry);
  assert.deepEqual(page.timeline[2].attachment, { contentType: "image/jpeg", sizeBytes: 183250 });
  assert.equal(page.timeline[0].attachment, null);
  assert.equal(page.timeline[3].attachment, null);
});

test("reports more messages when the backend sends a next cursor", () => {
  assert.equal(adaptChatMessagesPage(backendThreadPage).hasMore, true);
});

test("reports no more messages when the backend nextBefore is null", () => {
  const page = adaptChatMessagesPage({ ...backendThreadPage, nextBefore: null });

  assert.equal(page.hasMore, false);
  assert.equal(page.nextBefore, null);
});

test("orders fetched timeline entries oldest first while keeping each page's order", () => {
  const latest = { chat: {}, hasMore: true, nextBefore: "c", viewerRole: "customer", timeline: [messageEntry("m3", "2026-10-11T12:00:00.000Z"), messageEntry("m4", "2026-10-11T13:00:00.000Z")] };
  const older = { chat: {}, hasMore: false, nextBefore: null, viewerRole: "customer", timeline: [messageEntry("m1", "2026-10-10T09:00:00.000Z"), messageEntry("m2", "2026-10-10T10:00:00.000Z")] };
  assert.deepEqual(
    orderTimelineOldestFirst([latest, older]).map((entry) => entry.messageId),
    ["m1", "m2", "m3", "m4"],
  );
});
