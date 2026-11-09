import assert from "node:assert/strict";
import { test } from "node:test";
import { ChatRequestError, chatAccessMessage, formatChatRelativeTime } from "../../src/lib/chats.ts";
import { chatRefetchInterval, quotationStatusLabel } from "../../src/lib/chat-quotations.ts";
import { safeNextPath } from "../../src/lib/post-login-path.ts";
import { createChatEventParser, parseChatEvent } from "../../src/lib/chat-events.ts";
import { buildChatToast, shouldNotify } from "../../src/lib/chat-notifications.ts";
import { LocationError, requestDriverLocation } from "../../src/lib/geolocation.ts";

test("chat errors preserve optional detail and map every access reason", () => {
  const error = new ChatRequestError(422, { type: "contact", msg: "Contact blocked" });
  assert.equal(error.status, 422);
  assert.equal(error.detailType, "contact");
  assert.equal(error.detailMessage, "Contact blocked");
  assert.equal(error.name, "ChatRequestError");
  assert.equal(new ChatRequestError(500).detailType, null);
  for (const reason of ["sign-in", "aal2", "session"]) assert.match(chatAccessMessage(reason), /sesión|teléfono/);
});

test("chat relative date labels cover the multi-day boundary", () => {
  const now = new Date("2026-11-07T12:00:00Z");
  assert.equal(formatChatRelativeTime("2026-11-05T12:00:00Z", now), "hace 2 días");
  assert.equal(formatChatRelativeTime("2026-11-01T12:00:00Z", now), "hace 6 días");
});

test("quotation polling and unknown statuses have explicit fallbacks", () => {
  assert.equal(chatRefetchInterval(true), false);
  assert.equal(chatRefetchInterval(false), 10000);
  assert.equal(quotationStatusLabel("future-status"), "Estado desconocido");
});

test("safe-next rejects control-character origin normalization and parser failures", () => {
  assert.equal(safeNextPath("/\n/evil.test"), "/servicios");
  const RealURL = globalThis.URL;
  try {
    globalThis.URL = class { constructor() { throw new TypeError("parse unavailable"); } };
    assert.equal(safeNextPath("/panel"), "/servicios");
  } finally {
    globalThis.URL = RealURL;
  }
});

test("SSE parser handles colonless fields, empty values, bare CR and partial input", () => {
  const frames = [];
  const parser = createChatEventParser((frame) => frames.push(frame));
  parser.push("event\rdata\r\rignored: value\r\r");
  parser.push("x");
  assert.deepEqual(frames, [{ event: "message", data: "" }]);
  assert.equal(parseChatEvent({ event: "message.created", data: "[]" }), null);
  assert.equal(parseChatEvent({ event: "message.created", data: JSON.stringify({ kind: "message.created", chatId: "c", messageId: 1 }) }), null);
  assert.equal(parseChatEvent({ event: "quotation.changed", data: JSON.stringify({ kind: "quotation.changed", chatId: "c", quotationId: null }) }), null);
});

test("chat toast omits missing previews and still notifies outside the visible thread", () => {
  const event = { kind: "message.created", chatId: "chat", messageId: "message", fromMe: false };
  const chat = { counterpart: { name: "Ana" }, lastMessage: null };
  assert.deepEqual(buildChatToast(event, chat), { id: "chat-chat", title: "Nuevo mensaje de Ana" });
  assert.equal(shouldNotify(event, "/panel", true), true);
  assert.equal(shouldNotify(event, "/mensajes/chat", false), true);
});

for (const code of [2, 3, 99]) {
  test(`geolocation failure ${code} maps to a bounded LocationError`, async () => {
    await assert.rejects(requestDriverLocation({ getCurrentPosition(_success, failure, options) {
      assert.deepEqual(options, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
      failure({ code });
    } }), (error) => error instanceof LocationError && error.code === (code === 3 ? 3 : 2));
  });
}
