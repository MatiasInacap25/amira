import assert from "node:assert/strict";
import { test } from "node:test";
import { buildChatToast, shouldNotify } from "../../src/lib/chat-notifications.ts";

const messageFromOther = { kind: "message.created", chatId: "chat-1", messageId: "m-1", fromMe: false };
const quotationFromOther = { kind: "quotation.changed", chatId: "chat-1", quotationId: "q-1", fromMe: false };

const ana = {
  chatId: "chat-1",
  counterpart: { name: "Ana Pérez", kind: "customer", providerProfileId: null },
  lastMessage: { content: "¿A qué hora llegan?", sentAt: "2026-10-19T12:00:00Z", fromMe: false },
};

test("shouldNotify skips the caller's own events", () => {
  assert.equal(shouldNotify({ ...messageFromOther, fromMe: true }, "/servicios", true), false);
  assert.equal(shouldNotify({ ...quotationFromOther, fromMe: true }, "/servicios", true), false);
});

test("shouldNotify notifies for another chat's message while the user is elsewhere", () => {
  assert.equal(shouldNotify({ ...messageFromOther, chatId: "chat-2" }, "/mensajes/chat-1", true), true);
  assert.equal(shouldNotify(messageFromOther, "/servicios", true), true);
});

test("shouldNotify stays quiet for the open chat while its tab is visible", () => {
  assert.equal(shouldNotify(messageFromOther, "/mensajes/chat-1", true), false);
  assert.equal(shouldNotify(quotationFromOther, "/mensajes/chat-1", true), false);
});

test("shouldNotify notifies for the open chat when its tab is hidden", () => {
  assert.equal(shouldNotify(messageFromOther, "/mensajes/chat-1", false), true);
});

test("shouldNotify never notifies for chat.read, which only updates unread state", () => {
  assert.equal(shouldNotify({ kind: "chat.read", chatId: "chat-1", fromMe: true }, "/servicios", true), false);
});

test("buildChatToast names the counterpart and uses the last message preview", () => {
  assert.deepEqual(buildChatToast(messageFromOther, ana), {
    id: "chat-chat-1",
    title: "Nuevo mensaje de Ana Pérez",
    description: "¿A qué hora llegan?",
  });
});

test("buildChatToast shows the photo preview for an image-only last message", () => {
  const photo = { ...ana, lastMessage: { content: "Foto", sentAt: "2026-10-19T12:00:00Z", fromMe: false } };

  assert.equal(buildChatToast(messageFromOther, photo).description, "Foto");
});

test("buildChatToast words a quotation change with the counterpart name and no preview", () => {
  assert.deepEqual(buildChatToast(quotationFromOther, ana), {
    id: "chat-chat-1",
    title: "Actualización de cotización de Ana Pérez",
  });
});

test("buildChatToast falls back to generic copy when the chat is not in the loaded pages", () => {
  assert.deepEqual(buildChatToast({ ...messageFromOther, chatId: "chat-9" }, undefined), {
    id: "chat-chat-9",
    title: "Tienes un mensaje nuevo",
  });
  assert.deepEqual(buildChatToast({ ...quotationFromOther, chatId: "chat-9" }, undefined), {
    id: "chat-chat-9",
    title: "Tienes una actualización de cotización",
  });
});
