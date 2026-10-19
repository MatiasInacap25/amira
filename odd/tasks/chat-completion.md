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
| T2 | S2.2, S2.3 | delegated (herdr worker, Haiku) | done | `3d0efa3` |
| T3 | S2.1, S2.2, S2.4, S2.5 | delegated (herdr worker, Haiku) | done | `8f51d1a` |
| T4 | S2.6 | delegated (herdr worker, Haiku) | done | `911708f` |
| V1 | S2 | independent verifier (high risk: auth, concurrency) | pending | |

Route evidence: `HERDR_ENV=1`; the project CLAUDE.md makes the parent an orchestrator that does not edit code. Workers run one at a time because Playwright uses port 3179.

## Log

- L1 (2026-10-18): "dale, despues sigues con el timepo real y con adjuntos, mensajes no leidos y notificaciones" (answer to: fix the thread contract mismatch first, with a test comparing the real backend response to what the frontend expects).
- L2 (2026-10-18): Mismatch confirmed by reading code: `ChatMessagesPage(ChatHeader)` is flat; `frontend/src/lib/chats.ts:73-75` expects `chat` and `hasMore`; `getChatMessages` returns the JSON with no adapter; the composer renders only when `chat` exists.
- L3 (2026-10-18): T1 done (`3f78f72`). Frontend adapter adaptChatMessagesPage in chats.ts; shared fixture frontend/tests/fixtures/chat-messages-page.json validated by backend/tests/test_chat_contract.py and the node unit tests. RED: 11 page-chat failures with backend-shaped mocks; unit import failure. auth.spec.ts:498 mock updated to the flat shape. Parent checks: Playwright auth + page-chat 43 passed (full suite before the auth fix: 284 passed, 1 failed = that test); unit 70 passed; backend 559 passed; lint 0.
- L4 (2026-10-18): Native review of T1 (base `dbc26a8`, committed-only): consent granted; lens reliability; approved and acknowledged (lineage `review-9910ca6229b19bc8`). Advisory SUGGESTION R3-adapter-header-fields-partially-asserted at frontend/tests/unit/chats.node-test.mjs:99-111 (later work). Next: user approval of the S2 real-time plan (SSE from FastAPI chosen).
- L5 (2026-10-18): "si, dale" (approval of the S2 SSE plan). Branch `feat/chat-realtime` created on top of `fix/chat-thread-contract` (not merged yet).
- L6 (2026-10-18): T2 done (`3d0efa3`): realtime.publish_chat_event in send message, quotation create (superseded + new), reject, payment confirmation; superseded ids selected before the update. Backend 579 passed. pg_notify SQL not exercised against Postgres (offline tests).
- L7 (2026-10-18): T3 done (`8f51d1a`): ChatBroker (per-user cap 5, slow subscribers dropped), LISTEN listener in the lifespan with 1-30 s backoff, `GET /api/chats/events`. Parent review found the auth DB session lived for the whole stream (yield dependency exits after the response in FastAPI 0.141.1); fixed with `Depends(get_db_session, scope="function")` on this route plus `authorize_current_user` extracted unchanged; RED/GREEN test proves the session closes before the first frame. Backend 604 passed. Untested: listener reconnect loop, mid-stream disconnect cleanup.
- L8 (2026-10-18): T4 done (`911708f`): chat-events.ts parser + backoff, one ref-counted stream per tab, invalidation per event, polling 30 s only while disconnected. Full Playwright 287 passed; unit 79 passed; lint 0; worker build 0.
- L9 (2026-10-18): V1 independent verifier (scratch worktree, HEAD b7351ba): S2.1, S2.2, S2.5, S2.6 pass; S2.3, S2.4 pass for code paths, Postgres LISTEN/NOTIFY round trip unverified (no local Postgres or Docker). No blockers. Advisories: run a real committed/rolled-back NOTIFY round trip before shipping; the 5-stream cap is per process; keepalive default not asserted by a test; customer dispute status change does not publish (outside S2.3); CHAT_POLL_INTERVAL_MS referenced before its declaration (cosmetic). Backend 604, unit 79, Playwright chat 32 passed; repository unchanged.
- L10 (2026-10-18): Native review of T2-T4 (base `575c5f6`, committed-only, lenses risk/resilience/reliability, consent granted, lineage `review-fcfcc4e27815a1fa`). Blocking CRITICAL R4-polling-disabled-while-listener-is-dead: an accepted stream disabled polling even when no events flow. One bounded correction committed as `be48d57` (ready/degraded from listener state; client polls every 10 s until ready; S2.6 polling interval is now 10 s while not ready, not 30 s). Backend 608, unit 80, Playwright chat 34 passed; lint 0. Targeted validator REJECTED (state escalated): a transaction pooler accepts LISTEN but never delivers NOTIFY, so the listener still reports ready. No regression in the correction. Validator follow-ups: a full queue can drop a degraded frame (realtime.py:113-126,153); consider a periodic self-NOTIFY round trip before reporting ready. Needs user decision.
