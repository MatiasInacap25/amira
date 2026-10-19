# Amira backend

FastAPI starter application. It provides a health check and validated settings; it does not yet implement marketplace behavior or connect to external services.

## Requirements

- Python 3.12+
- `uv` (the project uses `pyproject.toml` and `uv.lock`)

## Setup

```powershell
uv sync
Copy-Item .env.example .env
uv run uvicorn amira_api.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API documentation is at `/docs`. The health endpoint is `GET /health`.

Account provisioning requires the trusted `INDEPENDENT_DRIVER_TYPE_ID` mapping for independent drivers. If a company owner opts into a linked driver record, configure `COMPANY_DRIVER_TYPE_ID` with the UUID of the approved `Tipo_Conductor` row. The API verifies that configured row exists and fails closed before creating account records if it does not; do not accept a driver type from browser input or infer one from a display name. Company owners who do not opt in remain company-only accounts. Personal RUT, birth date, and phone are validated and stored on the private `Usuario` record; they are not Supabase user metadata or fields in public account responses. Supabase Auth remains the only password store, and the API email is taken from the verified Auth identity.

Set `CORS_ORIGINS` to a comma-separated list of exact browser origins, including scheme and port, for example `http://localhost:3000`. Do not use wildcard origins when sending credentials. The API connects lazily when a database-backed request runs; Alembic reads `DATABASE_URL` and reports a clear error if migrations are run before one is configured.

## Development-only SMS MFA bypass

`DEV_SKIP_SMS_MFA` (default `false`) lets an `aal1` session that was authenticated with a password skip the SMS MFA step and the email-fallback proof, so a developer with one test phone can create several accounts and sign in with email and password. The bypass only applies when the token passes the same signature, issuer, audience, expiry, role, email, and `is_anonymous` checks as every other request; anonymous, non-password, or otherwise unverifiable sessions are still rejected. Accepted requests carry the assurance `dev_password_bypass`. Phone numbers are not unique, so several accounts may share one test number.

The bypass is fail-closed: it is active only when `DEV_SKIP_SMS_MFA=true` and `APP_ENV` (trimmed, case-insensitive) is one of `development`, `local`, or `test`. If `DEV_SKIP_SMS_MFA=true` and `APP_ENV` is unset or has any other value (`production`, `prod`, `staging`, `preview`, a typo, or empty), the API refuses to start with an error naming the allowed values. The error never echoes other settings. The API logs a warning at startup whenever the bypass is active. Never enable it in a deployed environment.

The frontend also needs its own switch: set `NEXT_PUBLIC_DEV_SKIP_SMS_MFA=true` in `frontend/.env.local` alongside `DEV_SKIP_SMS_MFA=true` here. The backend flag alone does not change what the browser asks for.

## Public browse API

- `GET /api/services?q=&regionCode=&communeCode=&limit=20&offset=0` returns provider/service catalog entries. `regionCode` (2 digits) and `communeCode` (5 digits) are official CUT codes from `GET /api/locations`.
- `GET /api/shared-routes?originCommuneCode=&destinationCommuneCode=&departureFrom=&departureTo=&limit=20&offset=0` returns published routes that accept requests, with ordered stop numbers and estimated times. Route items expose `originCommuneCode`/`destinationCommuneCode`, which are null for legacy rows created before the commune catalog.

Both endpoints return `{items, total, limit, offset}`, cap page size at 50 and offset at 5000, and validate filter lengths. Responses intentionally omit account identity, company tax IDs, raw storage keys, full stop addresses, vehicles/drivers, customer requests, chats, payments, and payout references. Route results expose only published origin/destination cities; intermediate stops include sequence and time but no address because the current schema has no separate public-locality field. Service entries are based on `Servicios_Disponibles`; the current schema has no separate visibility status for that association. Logo URLs remain null until a safe public asset URL mechanism is implemented. Departure filters must be timezone-aware ISO-8601 datetimes.

## Payments (simulated provider)

Payments go through the `PaymentProvider` port (`src/amira_api/payment_provider.py`). The domain in `payment_service.py` depends only on the port; `simulated_payment_provider.py` is the only adapter and `payment_routes.py` is the composition root that chooses it.

The simulated adapter is enabled only when `APP_ENV` is set explicitly to `development`, `local` or `test` (fail closed, like `DEV_SKIP_SMS_MFA`; an unset `APP_ENV` disables it). It needs `PAYMENT_SIMULATOR_SECRET` (signs checkout tokens and confirmations; the browser never sees it) and `FRONTEND_BASE_URL` (builds the `/pagos/simulado` link). Without them, payment endpoints answer 503, and the simulated checkout endpoint answers 404 outside development.

A checkout link is bound to its payment and to the paying customer, expires after 15 minutes, and is single-use: the link is consumed in the same transaction as the confirmation, so a refused confirmation releases it. Only the payment's customer can complete it.

`POST /api/payments/confirm` is server-to-server only: it requires the `X-Amira-Payment-Webhook-Secret` header, compared in constant time with `PAYMENT_WEBHOOK_SECRET` (401 when wrong or missing, 503 when the secret is not configured). It refuses confirmations from the simulated provider with 403, so a browser can never obtain an approval through it. Confirmations are applied under row locks and are idempotent on the provider payment; a conflicting result for an already-decided payment is refused with 409.

## Contracted services

A `Servicio` moves through `confirmed`, `in_progress`, `completed` and `disputed` (`ck_service_status_allowed`). Providers assign one or more (driver, vehicle) pairs per service in `Servicio_Asignacion`.

- `GET /api/provider/services?status=&limit=20&offset=0` and `GET /api/provider/services/{serviceId}`: the owner of a provider `Perfil` sees every service of that profile; a company-employed driver (`Conductor.ID_perfil` set) who owns no profile sees only the services they are assigned to. Any other account gets 403.
- `GET /api/customer/services/{serviceId}`: the customer who owns the service.

A service the viewer cannot see answers 404. Responses name the counterpart (provider display name for customers, customer first name for providers) and never include phone, email or RUT. `canManage` is true only for the profile owner.

### Delivery photos (private Supabase Storage bucket)

`POST /api/provider/services/{serviceId}/complete` takes a multipart `photo` field from the assigned driver. The photo is stored in a private bucket and read back only through a signed URL (`GET .../delivery-photo` for the provider and the customer). The bucket is not created by code or migrations, so create it once per Supabase project:

1. In the Supabase dashboard, open Storage and create a bucket named `service-evidence` (or the value of `SERVICE_EVIDENCE_BUCKET`). Leave **Public** switched off.
2. Set `SUPABASE_URL` (the project URL) and `SUPABASE_SERVICE_ROLE_KEY` in the backend environment. The service-role key is server-side only; never put it in a `NEXT_PUBLIC_*` variable.

Optional settings and defaults: `SERVICE_EVIDENCE_MAX_BYTES` (8 MiB), `SERVICE_EVIDENCE_URL_TTL_SECONDS` (300), `SERVICE_CLAIM_WINDOW_HOURS` (24). Without the Supabase settings, the delivery-photo endpoints answer 503.

### Claims, consent and payout release

A customer can act on a completed service once: `POST /api/customer/services/{serviceId}/claims` with `{reason}` (trimmed, 1 to 1000 characters) opens a claim and moves the service to `disputed`; `POST /api/customer/services/{serviceId}/consent` (no body) records that the customer is satisfied. Both lock the service row. A claim is refused after the claim window (`SERVICE_CLAIM_WINDOW_HOURS` from completion) and after consent; consent is refused while a claim is open. Claim resolution and refunds are out of scope.

Payouts are released by `python -m amira_api.release_payouts`. No scheduled job is deployed: `render.yaml` defines only the web service. The only payout adapter is the simulated one (`simulated_payout_provider.py`), which never moves money and runs only when `APP_ENV` is set explicitly to `development`, `local` or `test`. Scheduling the job in production is therefore deferred until a real adapter exists behind the `PayoutProvider` port.

Until then, run the release by hand from `backend/` against a development database:

```bash
APP_ENV=development DATABASE_URL=<development database URL> uv run python -m amira_api.release_payouts
```

A completed service is released when the customer consented or its claim window has closed, it has no open claim, and it has no payout yet. The release needs an approved payment and an enabled `Cuenta_Desembolso` on the provider profile; services without one are counted as `missing_account` or `missing_payment` and stay due. Each service is released in its own transaction, the job is idempotent, and a provider failure is logged without stopping the other services. The command exits 1 only when the job cannot run (for example the adapter is refused for this `APP_ENV`, or the database is not configured).

The platform keeps a commission on each payout. `PAYOUT_COMMISSION_PERCENT` (default `10`, an integer from `0` to `99`) sets it as a percent of the gross approved payment. The commission is `gross * percent / 100`, rounded half up to whole CLP, and the provider receives `gross - commission`. `Desembolso.Monto_Neto` stores that net amount; the gross stays in `Pago`, and no commission column exists.

When a real payout adapter is added, re-add the Render cron job to `render.yaml` under `services:`, after the web service. This is the block removed from the blueprint:

```yaml
  - type: cron
    name: amira-release-payouts-dev
    runtime: docker
    rootDir: backend
    dockerfilePath: Dockerfile
    dockerContext: .
    schedule: "*/15 * * * *"
    dockerCommand: python -m amira_api.release_payouts
    envVars:
      - key: APP_NAME
        value: Amira API
      - key: APP_ENV
        value: production
      - key: CORS_ORIGINS
        sync: false
      - key: DATABASE_URL
        sync: false
      - key: SUPABASE_JWT_ISSUER
        sync: false
      - key: SUPABASE_JWT_AUDIENCE
        value: authenticated
      - key: INDEPENDENT_DRIVER_TYPE_ID
        sync: false
      - key: COMPANY_DRIVER_TYPE_ID
        sync: false
```

The block still sets `APP_ENV=production`, which the simulated adapter refuses. Replace the cron with the real adapter's configuration before deploying it. Add `PAYOUT_COMMISSION_PERCENT` to its `envVars` only if the commission differs from the default.

## Chat real-time events

`GET /api/chats/events` is a per-user Server-Sent Events stream (`text/event-stream`). It needs the same Supabase JWT in the `Authorization` header as every other endpoint; the token is never read from the URL. Each event carries ids only: `message.created` with `{chatId, messageId}` and `quotation.changed` with `{chatId, quotationId}`. The frontend re-reads the affected data after an event. The stream sends `: keepalive` every 20 seconds, closes when the token's `exp` passes (the client reconnects with a fresh token), and each user may hold at most 5 open streams (the sixth gets 429).

Writers announce changes with `pg_notify` inside their own transaction, so a rolled-back write sends nothing. A listener task started in the FastAPI lifespan runs `LISTEN` on its own connection and forwards each notification to the open streams of its recipients. It reconnects with capped exponential backoff and logs only the exception type.

LISTEN needs a session connection: the Supabase transaction pooler does not deliver notifications. Set `REALTIME_DATABASE_URL` to a direct or session-mode connection string. When it is unset, the listener uses `DATABASE_URL`. When neither is set, the listener does not start, the API still boots, and the stream stays silent. Like `DATABASE_URL`, the URL is forced to TLS (`sslmode=require`).

The listener proves delivery with a heartbeat. Every ~15 s it sends `pg_notify` on the `amira_chat_health` channel with a fresh random nonce, through the app engine (`DATABASE_URL`). It reports ready only when its own `LISTEN` connection receives a nonce it sent, and degraded when no matching heartbeat arrives within ~35 s or the connection drops. Without `DATABASE_URL` no heartbeat runs, so the listener stays degraded. Heartbeats are never forwarded to the event streams.

The stream sends `event: ready` when the listener is live, and `event: ready` or `event: degraded` to open streams when that changes. A stream whose queue cannot take that state change is closed, so the client reconnects and receives the current state. The client polls every 10 s until it sees `ready`.

A transaction pooler accepts `LISTEN` but never delivers notifications, so its heartbeat never returns and the listener shows as degraded. Clients then poll every 10 s instead of freezing. For live updates, `REALTIME_DATABASE_URL` should still be a session or direct connection.

### Chat attachments (private Supabase Storage bucket)

Chat messages can carry one image (JPEG, PNG or WebP). The bytes are stored in a private bucket and read back only through a signed URL, like delivery photos. Create the bucket once per Supabase project: in the dashboard, open Storage and create a bucket named `chat-attachments` (or the value of `CHAT_ATTACHMENTS_BUCKET`), with **Public** switched off. It uses the same `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as delivery photos; without them the attachment endpoints answer 503.

Optional settings and defaults: `CHAT_ATTACHMENTS_BUCKET` (`chat-attachments`), `CHAT_ATTACHMENT_MAX_BYTES` (5 MiB), `CHAT_ATTACHMENT_URL_TTL_SECONDS` (300).

- `POST /api/chats/{chatId}/messages/attachments`: multipart with a required `photo` and an optional `content`. Participants only; other callers get 404. The type is detected from the bytes, not the declared content type. An oversize photo gets 413, another type 415, and `content` goes through the same contact-details filter as text messages. The object is stored under `chats/{chatId}/{messageId}.{ext}`; if the database write fails, the object is deleted. The response is the created timeline entry, and `message.created` is published in the same transaction.
- `GET /api/chats/{chatId}/messages/{messageId}/attachment`: returns `{url, expiresAt}` for a signed URL. Participants only; a message without an attachment gets 404.

Timeline message entries carry `attachment: {contentType, sizeBytes} | null`. The chat list shows `Foto` as the preview when the last message has no text and an attachment.

## Checks

```powershell
uv run pytest
uv run python -c "from amira_api.main import app; print(app.title)"
uv lock --check
```

## Migrations

Alembic is initialized under `alembic/`. The declarative mappings live in `src/amira_api/models.py`; configure `DATABASE_URL` before applying migrations. Migrations are not run as part of tests and no live database is required for structural checks or offline PostgreSQL SQL generation.

## Database mapping

The ORM was mapped from the current Lucid diagram and its approved constraint notes, with English Python names and the diagram's Spanish table/column names retained in PostgreSQL. UUID primary keys use `gen_random_uuid()`; money uses fixed-precision `NUMERIC`, date-times are timezone-aware, and identity is linked by a unique Supabase Auth user UUID. Amira does not store a local password hash. `Vehiculo.Imagen_Storage_Key` is one required private-storage key; `Año` and `Peso_maximo` are optional.

`Usuario` is the complete account set. `Conductor` is a unique-user subset assigned to an employer `Perfil`; it is not itself the driver's public listing. A user may own at most one public profile, and that profile may exist without a driver record. `Rut_Empresa` is nullable because independent profiles do not require it; the profile's configured company role and any driver affiliation must be validated by the service layer because the diagram does not provide canonical role codes. `Cuenta_Desembolso` stores only a provider account reference, onboarding state, and timestamps. A payout records the destination account used for audit; no bank account, card, identity image, or credential is stored locally.

The schema enforces primary/foreign keys, one profile per user, one driver row per user, chat-member uniqueness, sender membership, one rating per service, normalized email/plate uniqueness, trip/vehicle assignment, same-trip stop references, provider-scoped external IDs/idempotency keys, and field-level checks. The current diagram contains 25 entities; `Cuenta_Desembolso` is added from its explicit Lucid note because the ERD shape is absent under the document's editing limit.

Cross-record and temporal rules remain business-transaction responsibilities unless a reviewed database trigger is installed: verify payment-provider signatures and state transitions; only reserve after successful payment; verify the quotation/chat/form/customer chain and preserve accepted commercial terms; lock capacity/exclusivity while confirming payment; validate trip ownership/roles and assignments; enforce pickup-before-delivery and publication prerequisites; keep refund-claim/payment-service references consistent; and release funds only after completion, notice, customer-conformity or the 24-hour rule, and claim checks. Foreign keys alone do not prove these invariants. RLS, grants, endpoint authorization, and public/private response shaping must be configured separately before exposing tables through Supabase Data API.

The logical ERD does not settle provider status vocabularies, canonical profile-role tokens, subcontracting policy, refund limits, currency/provider compatibility, or live concurrency and reconciliation behavior. Those are not inferred by the ORM; the application must define them before money-moving workflows are enabled.

The engine normalizes PostgreSQL URLs to Psycopg 3, requires TLS, and bounds the pool, connection timeout, and statement timeout. The public-browse migration enables RLS and revokes `PUBLIC`, `anon`, and `authenticated` privileges for all 26 application tables and `alembic_version`. It seeds clearly labeled `[DEMO]` rows with a synthetic non-login account mapping and `.invalid` email; it creates no Supabase Auth user, identity-verification, payment, or payout record.
