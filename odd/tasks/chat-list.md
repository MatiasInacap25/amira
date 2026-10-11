# Chat list

## Objective

One chat window, identical for customers and providers (independent drivers and company owners): a list of the user's chats showing the last message, and a chat view that shows every message of the selected chat.

## Current state (2026-10-11 audit)

- Models exist: `Chat` (`ID`, `Fecha_creacion`, `ID_Formulario`), `Chat_participantes` (`ID_Chat`, `ID_user`, unique pair), `Mensajes` (`ID_Chat`, `ID_Usuario`, `Contenido`, `Fecha_Creacion`; sender must be a chat participant) in `backend/src/amira_api/models.py:340-383`.
- A chat is created with two participants (customer and provider account) when a provider accepts a request (`public_routes.py` accept route).
- No chat or message endpoints exist; `frontend/src/app/mensajes/[chatId]/page.tsx` is a placeholder.

## Decisions

- Scope (user, 2026-10-11): only the chat list with the last message, and a chat view showing all messages. Sending messages, unread counts, realtime, and the contact-sharing filter are out of scope for this feature.
- The contact rule (no phone numbers, emails or other contact details in chat) applies when sending is built; recorded in `odd/tasks/provider-request-inbox.md` and project memory.
- Counterpart name: a provider sees the customer's first and last name (chats exist only after acceptance); a customer sees the provider's public name (company name or independent driver's name).
- Never expose phone, email, RUT or auth IDs of the counterpart.
- Workers do not commit; the orchestrator commits. No Playwright, no live database.

## API contract

Public JSON is camelCase. Both endpoints require the same authenticated user as `GET /api/provider/requests` (`get_current_user`).

1. `GET /api/chats?limit&offset` (limit ≤ 50): chats where the caller is a participant, ordered by last activity (last message time, else chat creation) descending. Response `{"items": [...], "total", "limit", "offset"}`; each item: `chatId`, `requestId`, `createdAt`, `serviceName`, `originCommuneName`, `destinationCommuneName` (nullable), `counterpart: {"name", "kind": "customer" | "company" | "independent_driver", "providerProfileId": uuid | null}`, `lastMessage: {"content" (first 140 chars), "sentAt", "fromMe": bool} | null`. Total and items must come from the same filtered relation.
2. `GET /api/chats/{chat_id}/messages?limit&before` (limit ≤ 100, `before` = ISO timestamp cursor): the chat header (same item shape as above, without `lastMessage`) plus `messages: [{"messageId", "content", "sentAt", "fromMe", "senderName"}]` oldest → newest within the page, and `hasMore`. 404 when the chat does not exist or the caller is not a participant (do not leak existence).

## Tasks

### Backend (worker `backend`)

Skills: `api-and-interface-design`, `fastapi-templates`, `sqlalchemy-alembic-expert-best-practices-code-review`.

- [x] CB1 `GET /api/chats` (contract 1) in a new `chat_routes.py` + `chat_schemas.py`, wired in `main.py`. Tests: only own chats, ordering, last message, counterpart naming per role, no contact data, total/items parity.
- [x] CB2 `GET /api/chats/{chat_id}/messages` (contract 2). Tests: participant only (404 otherwise), ordering, cursor pagination, `fromMe`.

Verification: `uv run pytest -q`, `uv lock --check`.

### Frontend (worker `frontend`)

Skills: `ui-ux-pro-max`, `impeccable`, `vercel-react-best-practices`, `boneyard`. UI copy in Spanish. Same view for every role.

- [x] CF1 `/mensajes`: chat list with counterpart name and kind, service, route communes, last message preview and relative time (or "Sin mensajes aún"), empty state, boneyard skeleton, "Cargar más". Clicking a chat opens `/mensajes/[chatId]`. Nav link "Mensajes" for signed-in users (any role), cache scoped per user and cleared on sign-out like the provider nav.
- [x] CF2 `/mensajes/[chatId]`: replace the placeholder with the chat header and all messages (own messages aligned right), "Ver mensajes anteriores" with the `before` cursor, loading/empty/error/not-found states. No composer: a short note says sending messages is coming soon.

Verification: `npm run lint`, `npx tsc --noEmit`, `node --test tests/unit/*.mjs`, `npm run build`.

## Progress

- 2026-10-11: Audit done, scope set by the user (list + read-only chat view). Branch `feat/chat-list`.

## Verification evidence

Pending.
