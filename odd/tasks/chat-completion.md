# Chat completion

Objective: make the customer–provider chat work against the real backend, then add real-time updates, attachments, unread counts and notifications. Branch: `fix/chat-thread-contract` (T1), later branches per slice.
Delivery: ask-on-risk. Runners: backend `uv run pytest` (from `backend/`), frontend Playwright and `node --test tests/unit/*.mjs` (from `frontend/`).

## Specs

- S1: The chat thread works against the real backend response of `GET /api/chats/{id}/messages`, which returns the chat header fields flat at the top level plus `viewerRole`, `timeline` and `nextBefore` (no `chat` object, no `hasMore`; `chat_schemas.py:74-77`). With that response the thread shows its header, the composer and "Ver mensajes anteriores" when `nextBefore` is not null. A contract test pins one shared fixture: the backend validates it against `ChatMessagesPage`, and the frontend parses the same fixture. Playwright chat mocks use the backend shape.
- S2: Real-time updates via SSE from FastAPI (user choice: "SSE desde FastAPI (Recomendado)"). Approved design:
  - S2.1 One stream per user: `GET /api/chats/events`, `text/event-stream`. Requires a valid Supabase JWT in the `Authorization` header (same verification as other endpoints; the token is never accepted in the URL).
  - S2.2 Events carry no message content: `message.created` `{chatId, messageId}` and `quotation.changed` `{chatId, quotationId}`. A user only receives events for chats they participate in.
  - S2.3 Every write that changes a chat (new message, quotation created/superseded/rejected, payment confirmation that changes a quotation) calls `pg_notify` inside the same transaction, so nothing is announced for a rolled-back write. The payload names both participants' user ids as recipients.
  - S2.4 A listener holds its own connection (`REALTIME_DATABASE_URL`, falling back to `DATABASE_URL`; LISTEN needs a session connection, not the transaction pooler) and fans events out to open streams in this process.
  - S2.5 The stream sends a keepalive comment every 20 s and closes when the caller's token expires; the client reconnects with a fresh token.
  - S2.6 The frontend opens the stream with `fetch` + `Authorization` (not `EventSource`), invalidates the chat list and the affected thread on each event, reconnects with backoff, and falls back to polling every 30 s while disconnected.
- S3: Attachments in chat. Pending design decision.
- S4: Unread counts. Pending design decision.
- S5: Notifications. Pending design decision.

## Tasks

| ID | Specs | Route | Status | Commit |
|---|---|---|---|---|
| T1 | S1 | delegated (herdr worker, Haiku) | done | `3f78f72` |
| T2 | S2.2, S2.3 | delegated (herdr worker, Haiku) | pending | |
| T3 | S2.1, S2.2, S2.4, S2.5 | delegated (herdr worker, Haiku) | pending | |
| T4 | S2.6 | delegated (herdr worker, Haiku) | pending | |
| V1 | S2 | independent verifier (high risk: auth, concurrency) | pending | |

Route evidence: `HERDR_ENV=1`; the project CLAUDE.md makes the parent an orchestrator that does not edit code. Workers run one at a time because Playwright uses port 3179.

## Log

- L1 (2026-10-18): "dale, despues sigues con el timepo real y con adjuntos, mensajes no leidos y notificaciones" (answer to: fix the thread contract mismatch first, with a test comparing the real backend response to what the frontend expects).
- L2 (2026-10-18): Mismatch confirmed by reading code: `ChatMessagesPage(ChatHeader)` is flat; `frontend/src/lib/chats.ts:73-75` expects `chat` and `hasMore`; `getChatMessages` returns the JSON with no adapter; the composer renders only when `chat` exists.
- L3 (2026-10-18): T1 done (`3f78f72`). Frontend adapter adaptChatMessagesPage in chats.ts; shared fixture frontend/tests/fixtures/chat-messages-page.json validated by backend/tests/test_chat_contract.py and the node unit tests. RED: 11 page-chat failures with backend-shaped mocks; unit import failure. auth.spec.ts:498 mock updated to the flat shape. Parent checks: Playwright auth + page-chat 43 passed (full suite before the auth fix: 284 passed, 1 failed = that test); unit 70 passed; backend 559 passed; lint 0.
- L4 (2026-10-18): Native review of T1 (base `dbc26a8`, committed-only): consent granted; lens reliability; approved and acknowledged (lineage `review-9910ca6229b19bc8`). Advisory SUGGESTION R3-adapter-header-fields-partially-asserted at frontend/tests/unit/chats.node-test.mjs:99-111 (later work). Next: user approval of the S2 real-time plan (SSE from FastAPI chosen).
- L5 (2026-10-18): "si, dale" (approval of the S2 SSE plan). Branch `feat/chat-realtime` created on top of `fix/chat-thread-contract` (not merged yet).
