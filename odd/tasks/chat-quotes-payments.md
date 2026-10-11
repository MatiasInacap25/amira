# Chat, quotations and payments

## Objective

Make the chat window usable: participants send messages (without sharing contact details), the provider sends a priced quotation from a modal, and the customer pays or rejects it. Payment goes through a provider port with a simulated adapter for now.

## Current state (2026-10-11)

- Builds on `odd/tasks/chat-list.md` (chat list and read-only chat view, `GET /api/chats`, `GET /api/chats/{id}/messages`). Start only after that feature is committed.
- Models exist without endpoints: `Cotizacion` (`chat_id` NOT NULL, `amount` ≥ 0, `currency` = CLP, `status` String(40) with no CHECK, `expires_at` > `created_at`, `accepted_at`, `service_at`, `description`, `origin`, `destination`, `service_type_id`), `Pago` (`quotation_id`, `provider`, `provider_payment_id`, `idempotency_key`, `amount`, `currency` = CLP, `status`, `confirmed_at`), `Servicio` (`accepted_quotation_id` unique NOT NULL).
- `PROJECT_OVERVIEW.md` lists the external payment provider as not selected.

## Decisions

- Payment provider (user, 2026-10-11): simulated adapter for now, behind a `PaymentProvider` port; a real provider (Mercado Pago, Webpay, Flow) is added later as another adapter without touching the domain.
- Contact rule (user, 2026-10-11): messages must not carry phone numbers, emails, links or social handles; enforced in the backend, mirrored in the frontend as a pre-check. The filter is heuristic and can be evaded (e.g. digits spelled out).
- Quotation states: `pending`, `paid`, `rejected`, `expired`, `superseded`. One pending quotation per chat; a new one supersedes the previous pending one. Expiry is evaluated on read and on pay.
- Payment confirmation must verify the provider signature (simulated adapter signs with a server secret). Creating the `Servicio` and marking the quotation `paid` happen in one transaction, idempotent on the provider payment id.
- Out of scope: payouts (`Desembolso`), refunds, commissions, realtime, attachments.
- The simulated adapter must refuse to run when `APP_ENV` is `production`.

## Tasks

### Backend

- [ ] MB1 `POST /api/chats/{id}/messages` (participants only, 404 otherwise; content 1–2000 chars, trimmed) with the contact filter (422 Spanish message naming the blocked kind).
- [ ] MB2 `POST /api/chats/{id}/quotations` (provider participant only): amount CLP integer > 0, service date, description, validity (default 48 h); supersedes previous pending; migration adds CHECK on `Cotizacion.Estado`. Quotations appear in the chat timeline returned by `GET /api/chats/{id}/messages`.
- [ ] MB3 `POST /api/quotations/{id}/reject` (customer participant only; pending only).
- [ ] MB4 Payments: `POST /api/quotations/{id}/payments` (customer only, pending and not expired) creates a `Pago` with an idempotency key and returns a checkout URL from the `PaymentProvider` port; `POST /api/payments/confirm` verifies the signature, marks `Pago` confirmed, quotation `paid`, and creates the `Servicio` atomically and idempotently. Simulated adapter with its own checkout endpoint for development.

### Frontend

Skills: `ui-ux-pro-max`, `impeccable`, `vercel-react-best-practices`, `boneyard`.

- [ ] MF1 Message composer in `/mensajes/[chatId]` with the contact pre-check and ~10 s polling.
- [ ] MF2 Provider-only "Enviar cotización" button and modal (monto CLP, fecha del servicio, descripción, vigencia).
- [ ] MF3 Quotation card in the timeline for both roles with status; customer actions "Pagar" and "Rechazar".
- [ ] MF4 `/pagos/resultado` return page (success, failure, pending) and the simulated checkout page in development.

Verification: backend `uv run pytest -q`; frontend `npm run lint`, `npx tsc --noEmit`, `node --test tests/unit/*.mjs`, `npm run build`.

## Progress

- 2026-10-11: Plan approved with the simulated payment provider. Waiting for `chat-list` to finish before starting.

## Verification evidence

Pending.
