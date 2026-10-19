// Pure rules for the chat real-time stream: an incremental SSE parser, event mapping and reconnect backoff.
// Keep this module free of imports so node unit tests can load it.

export type ChatStreamFrame = { event: string; data: string };

export type ChatEvent =
  | { kind: "message.created"; chatId: string; messageId: string }
  | { kind: "quotation.changed"; chatId: string; quotationId: string };

export const CHAT_EVENTS_INITIAL_BACKOFF_MS = 1_000;
export const CHAT_EVENTS_MAX_BACKOFF_MS = 30_000;

// Accepts CRLF, LF and CR line endings and keeps a partial line until its terminator arrives.
export function createChatEventParser(onFrame: (frame: ChatStreamFrame) => void) {
  let pending = "";
  let event = "";
  let dataLines: string[] = [];

  function handleLine(line: string) {
    if (line === "") {
      if (dataLines.length > 0) onFrame({ event: event || "message", data: dataLines.join("\n") });
      event = "";
      dataLines = [];
      return;
    }
    if (line.startsWith(":")) return;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    if (field === "data") dataLines.push(value);
  }

  return {
    push(chunk: string) {
      pending += chunk;
      let lineEnd = pending.search(/[\r\n]/);
      while (lineEnd !== -1) {
        // A CR at the very end may be the first half of a CRLF split across chunks; wait for the next chunk.
        if (pending[lineEnd] === "\r" && lineEnd === pending.length - 1) break;
        const width = pending[lineEnd] === "\r" && pending[lineEnd + 1] === "\n" ? 2 : 1;
        handleLine(pending.slice(0, lineEnd));
        pending = pending.slice(lineEnd + width);
        lineEnd = pending.search(/[\r\n]/);
      }
    },
  };
}

// Maps a frame to a typed event. Unknown event names, malformed JSON and mismatched payloads yield null.
export function parseChatEvent(frame: ChatStreamFrame): ChatEvent | null {
  let payload: unknown;
  try {
    payload = JSON.parse(frame.data);
  } catch {
    return null;
  }
  if (typeof payload !== "object" || payload === null) return null;
  const { kind, chatId } = payload as Record<string, unknown>;
  if (kind !== frame.event || typeof chatId !== "string") return null;
  if (kind === "message.created") {
    const { messageId } = payload as Record<string, unknown>;
    return typeof messageId === "string" ? { kind, chatId, messageId } : null;
  }
  if (kind === "quotation.changed") {
    const { quotationId } = payload as Record<string, unknown>;
    return typeof quotationId === "string" ? { kind, chatId, quotationId } : null;
  }
  return null;
}

// Capped exponential backoff: 1 s, 2 s, 4 s ... 30 s. The jitter maps the capped delay to the delay used.
export function chatEventsBackoffMs(attempt: number, jitter: (ms: number) => number = (ms) => ms): number {
  const capped = Math.min(CHAT_EVENTS_MAX_BACKOFF_MS, CHAT_EVENTS_INITIAL_BACKOFF_MS * 2 ** Math.max(0, attempt));
  return Math.round(jitter(capped));
}
