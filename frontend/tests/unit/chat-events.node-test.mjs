import assert from "node:assert/strict";
import { test } from "node:test";
import { chatEventsBackoffMs, createChatEventParser, parseChatEvent, parseChatStreamState } from "../../src/lib/chat-events.ts";

function collect() {
  const frames = [];
  const parser = createChatEventParser((frame) => frames.push(frame));
  return { frames, parser };
}

test("parser emits one frame per blank-line-terminated event with its event name and data", () => {
  const { frames, parser } = collect();

  parser.push('event: message.created\ndata: {"kind":"message.created","chatId":"chat-1","messageId":"m-1"}\n\n');

  assert.deepEqual(frames, [
    { event: "message.created", data: '{"kind":"message.created","chatId":"chat-1","messageId":"m-1"}' },
  ]);
});

test("parser joins chunks split mid-line and mid-field without losing or duplicating data", () => {
  const { frames, parser } = collect();
  const wire = "event: quotation.changed\ndata: {\"kind\":\"quotation.changed\",\"chatId\":\"c\",\"quotationId\":\"q\"}\n\n";

  for (const char of wire) parser.push(char);

  assert.equal(frames.length, 1);
  assert.equal(frames[0].event, "quotation.changed");
  assert.equal(JSON.parse(frames[0].data).quotationId, "q");
});

test("parser holds a CR at the end of a chunk until the LF arrives in the next one", () => {
  const { frames, parser } = collect();

  parser.push("event: message.created\r");
  assert.equal(frames.length, 0);
  parser.push("\ndata: {}\r\n\r\n");

  assert.deepEqual(frames, [{ event: "message.created", data: "{}" }]);
});

test("parser ignores comment lines such as keepalives and emits no frame for them", () => {
  const { frames, parser } = collect();

  parser.push(": keepalive\n\n: keepalive\n\n");

  assert.deepEqual(frames, []);
});

test("parser joins multi-line data with newlines and keeps a comment inside an event", () => {
  const { frames, parser } = collect();

  parser.push("event: message.created\n: note\ndata: first\ndata: second\n\n");

  assert.deepEqual(frames, [{ event: "message.created", data: "first\nsecond" }]);
});

test("parser defaults the event name to message and does not dispatch an event without data", () => {
  const { frames, parser } = collect();

  parser.push("data: hello\n\nevent: quotation.changed\n\n");

  assert.deepEqual(frames, [{ event: "message", data: "hello" }]);
});

test("parseChatEvent maps known event frames to typed ids and drops unknown or malformed ones", () => {
  assert.deepEqual(
    parseChatEvent({ event: "message.created", data: '{"kind":"message.created","chatId":"chat-1","messageId":"m-1"}' }),
    { kind: "message.created", chatId: "chat-1", messageId: "m-1" },
  );
  assert.deepEqual(
    parseChatEvent({ event: "quotation.changed", data: '{"kind":"quotation.changed","chatId":"chat-1","quotationId":"q-1"}' }),
    { kind: "quotation.changed", chatId: "chat-1", quotationId: "q-1" },
  );
  assert.equal(parseChatEvent({ event: "payment.updated", data: '{"kind":"payment.updated","chatId":"chat-1"}' }), null);
  assert.equal(parseChatEvent({ event: "message.created", data: "{not json" }), null);
  assert.equal(parseChatEvent({ event: "message.created", data: '{"kind":"quotation.changed","chatId":"chat-1"}' }), null);
  assert.equal(parseChatEvent({ event: "message.created", data: '{"kind":"message.created","messageId":"m-1"}' }), null);
});

test("backoff doubles from 1 s and caps at 30 s", () => {
  const sequence = [0, 1, 2, 3, 4, 5, 6, 7, 50].map((attempt) => chatEventsBackoffMs(attempt));

  assert.deepEqual(sequence, [1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000, 30_000, 30_000]);
});

test("backoff applies the injected jitter to the capped delay", () => {
  assert.equal(chatEventsBackoffMs(2, (ms) => ms * 0.5), 2_000);
  assert.equal(chatEventsBackoffMs(9, (ms) => ms * 0.5), 15_000);
});

test("parser and parseChatStreamState report ready and degraded frames and ignore other events", () => {
  const { frames, parser } = collect();

  parser.push("event: ready\ndata: {}\n\nevent: degraded\ndata: {}\n\nevent: message.created\ndata: {}\n\n");

  assert.deepEqual(frames.map(parseChatStreamState), ["ready", "degraded", null]);
});

test("maps a chat.read frame to the reader's chat id without a message or quotation id", () => {
  const { frames, parser } = collect();

  parser.push('event: chat.read\ndata: {"kind":"chat.read","chatId":"chat-1"}\n\n');

  assert.deepEqual(parseChatEvent(frames[0]), { kind: "chat.read", chatId: "chat-1" });
});

test("rejects a chat.read frame without a chat id", () => {
  assert.equal(parseChatEvent({ event: "chat.read", data: '{"kind":"chat.read"}' }), null);
});
