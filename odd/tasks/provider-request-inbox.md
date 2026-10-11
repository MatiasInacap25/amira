# Provider request inbox

## Objective

Give independent drivers and company owners a usable window to review the quote requests they received: filter by status, see catalog communes and the customer's name under a privacy rule, open a detail view, and reach the chat after accepting.

## Current state (2026-10-11 audit)

- `GET /api/provider/requests` (`backend/src/amira_api/public_routes.py:302`) returns 20 newest requests with free-text origin/destination, cargo details, service name and chat id; no status filter, no counts, no commune names, no customer data. Ownership via `_owned_provider` (`:269`): only `company_owner` and `independent_driver`.
- `POST /api/provider/requests/{id}/accept|reject` (`:340-397`): pending → accepted/rejected; accept creates a `Chat` with two participants. Idempotent, 409 on conflicting decisions.
- `frontend/src/components/marketplace/provider-request-inbox.tsx` renders a single unpaginated list; "Mis solicitudes" nav link is shown to everyone (`site-navigation.tsx:20,46`).
- `Cotizacion` and `Mensaje` exist only as schema; the chat page is a placeholder.

## Decisions

- Customer data policy (user, 2026-10-11): before acceptance the provider sees only the customer's first name; after acceptance, first and last name. Phone and email are never exposed to providers.
- Future chat rule (user, 2026-10-11): when messaging is built, users must not be able to exchange phone numbers, emails or other contact details through the chat. Out of scope here; recorded for the messaging feature.
- Out of scope: priced quotes (`Cotizacion`), messaging, company-driver access, cargo images, multiple profiles per owner.
- Branch is stacked on `feat/dev-skip-sms-mfa` (PR #4) because the inbox uses `src/lib/auth/dev-mfa.ts`.
- Workers do not commit; the orchestrator commits each verified unit. No Playwright.

## API contract

Public JSON is camelCase.

1. `GET /api/provider/requests?status=pending|accepted|rejected&limit&offset` (status optional = all). Response adds `counts: {"pending", "accepted", "rejected"}` (always for all statuses, independent of the filter). Each item adds `originCommuneCode`, `originCommuneName`, `originRegionName`, `destinationCommuneCode`, `destinationCommuneName`, `destinationRegionName` (nullable), `isExclusive`, `customerFirstName` (string), `customerLastName` (string | null; non-null only when status is `accepted`). `origin` and `destination` become nullable. Invalid `status` → 422 in Spanish.
2. `GET /api/provider/requests/{request_id}` → one item with the same shape; 404 when it does not belong to the caller's profile (do not leak existence).
3. Accept/reject unchanged.

## Tasks

### Backend (worker `backend`)

Skills: `api-and-interface-design`, `fastapi-templates`, `sqlalchemy-alembic-expert-best-practices-code-review`.

- [x] QB1 List filter, counts, communes, customer name policy, nullable origin/destination (contract 1). Tests for each rule, including that phone and email never appear and last name only appears when accepted.
- [x] QB2 Detail endpoint (contract 2) with ownership tests.

Verification: `uv run pytest -q`, `uv lock --check`.

### Frontend (worker `frontend`)

Skills: `ui-ux-pro-max`, `impeccable`, `vercel-react-best-practices`, `boneyard`. UI copy in Spanish.

- [x] QF1 Inbox redesign: tabs Pendientes / Aceptadas / Rechazadas with counts, "Cargar más" pagination, commune/region display (fallback to free text), customer name, boneyard skeleton, empty/error states.
- [x] QF2 Detail page `/solicitudes/[requestId]` with all fields and accept/reject actions.
- [x] QF3 Nav: show "Mis solicitudes" only to provider roles (`company_owner`, `independent_driver`) using the account endpoint, with a pending-count badge; after accepting, navigate to `/mensajes/{chatId}`.

Verification: `npm run lint`, `npx tsc --noEmit`, `node --test tests/unit/*.mjs`, `npm run build`.

## Progress

- 2026-10-11: Audit done, plan approved with the customer-name policy. Branch `feat/provider-request-inbox`.

## Verification evidence

Pending.
