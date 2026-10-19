# Chat completion

Objective: make the customer–provider chat work against the real backend, then add real-time updates, attachments, unread counts and notifications. Branch: `fix/chat-thread-contract` (T1), later branches per slice.
Delivery: ask-on-risk. Runners: backend `uv run pytest` (from `backend/`), frontend Playwright and `node --test tests/unit/*.mjs` (from `frontend/`).

## Specs

- S1: The chat thread works against the real backend response of `GET /api/chats/{id}/messages`, which returns the chat header fields flat at the top level plus `viewerRole`, `timeline` and `nextBefore` (no `chat` object, no `hasMore`; `chat_schemas.py:74-77`). With that response the thread shows its header, the composer and "Ver mensajes anteriores" when `nextBefore` is not null. A contract test pins one shared fixture: the backend validates it against `ChatMessagesPage`, and the frontend parses the same fixture. Playwright chat mocks use the backend shape.
- S2: Real-time updates. Pending design decision.
- S3: Attachments in chat. Pending design decision.
- S4: Unread counts. Pending design decision.
- S5: Notifications. Pending design decision.

## Tasks

| ID | Specs | Route | Status | Commit |
|---|---|---|---|---|
| T1 | S1 | delegated (herdr worker, Haiku) | done | see L3 |

Route evidence: `HERDR_ENV=1`; the project CLAUDE.md makes the parent an orchestrator that does not edit code. Workers run one at a time because Playwright uses port 3179.

## Log

- L1 (2026-10-18): "dale, despues sigues con el timepo real y con adjuntos, mensajes no leidos y notificaciones" (answer to: fix the thread contract mismatch first, with a test comparing the real backend response to what the frontend expects).
- L2 (2026-10-18): Mismatch confirmed by reading code: `ChatMessagesPage(ChatHeader)` is flat; `frontend/src/lib/chats.ts:73-75` expects `chat` and `hasMore`; `getChatMessages` returns the JSON with no adapter; the composer renders only when `chat` exists.
- L3 (2026-10-18): T1 done (`3f78f72`). Frontend adapter adaptChatMessagesPage in chats.ts; shared fixture frontend/tests/fixtures/chat-messages-page.json validated by backend/tests/test_chat_contract.py and the node unit tests. RED: 11 page-chat failures with backend-shaped mocks; unit import failure. auth.spec.ts:498 mock updated to the flat shape. Parent checks: Playwright auth + page-chat 43 passed (full suite before the auth fix: 284 passed, 1 failed = that test); unit 70 passed; backend 559 passed; lint 0.
