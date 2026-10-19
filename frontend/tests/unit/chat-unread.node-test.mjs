import assert from "node:assert/strict";
import { test } from "node:test";
import { shouldMarkChatRead, formatUnreadBadge, unreadAccessibleLabel } from "../../src/lib/chat-unread.ts";
import { CHAT_ROOT_KEY, chatUnreadTotalKey } from "../../src/lib/chats.ts";

test("hides the unread badge when nothing is unread", () => {
  assert.equal(formatUnreadBadge(0), undefined);
  assert.equal(formatUnreadBadge(-1), undefined);
});

test("shows exact counts up to 99 and caps larger counts at 99+", () => {
  assert.equal(formatUnreadBadge(1), "1");
  assert.equal(formatUnreadBadge(99), "99");
  assert.equal(formatUnreadBadge(100), "99+");
  assert.equal(formatUnreadBadge(250), "99+");
});

test("labels the unread count in Spanish for screen readers", () => {
  assert.equal(unreadAccessibleLabel(0), undefined);
  assert.equal(unreadAccessibleLabel(1), "1 mensaje sin leer");
  assert.equal(unreadAccessibleLabel(3), "3 mensajes sin leer");
  assert.equal(unreadAccessibleLabel(100), "100 mensajes sin leer");
});

test("marks a thread read when it is visible and its newest entry is new", () => {
  assert.equal(shouldMarkChatRead({ visibility: "visible", newestEntryId: "m-2", lastMarkedEntryId: undefined }), true);
  assert.equal(shouldMarkChatRead({ visibility: "visible", newestEntryId: "m-3", lastMarkedEntryId: "m-2" }), true);
});

test("does not mark a thread read while the tab is hidden", () => {
  assert.equal(shouldMarkChatRead({ visibility: "hidden", newestEntryId: "m-3", lastMarkedEntryId: "m-2" }), false);
});

test("does not repeat a mark for the same newest entry", () => {
  assert.equal(shouldMarkChatRead({ visibility: "visible", newestEntryId: "m-2", lastMarkedEntryId: "m-2" }), false);
});

test("does not mark an empty thread", () => {
  assert.equal(shouldMarkChatRead({ visibility: "visible", newestEntryId: undefined, lastMarkedEntryId: undefined }), false);
});

test("keys the unread total under the chat root so existing invalidations cover it", () => {
  assert.deepEqual(chatUnreadTotalKey("user-1"), [...CHAT_ROOT_KEY, "unread", "user-1"]);
});
