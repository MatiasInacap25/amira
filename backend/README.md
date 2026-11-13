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

The frontend also needs its own switch: set `NEXT_PUBLIC_DEV_SKIP_SMS_MFA=true` and `NEXT_PUBLIC_APP_ENV=development` (or `local` or `test`) in the frontend environment alongside `DEV_SKIP_SMS_MFA=true` and `APP_ENV` here. The frontend variables are inlined at build time, so a Vercel redeploy is needed after changing them. The frontend does not depend on `NODE_ENV` for this switch. The backend flag alone does not change what the browser asks for, and the backend guard above is what actually rejects sessions without SMS.

## Public browse API

- `GET /api/services?q=&regionCode=&communeCode=&limit=20&offset=0` returns provider/service catalog entries. `regionCode` (2 digits) and `communeCode` (5 digits) are official CUT codes from `GET /api/locations`.
- `GET /api/shared-routes?originCommuneCode=&destinationCommuneCode=&departureFrom=&departureTo=&limit=20&offset=0` returns published routes that accept requests, with ordered stop numbers and estimated times. Route items expose `originCommuneCode`/`destinationCommuneCode`, which are null for legacy rows created before the commune catalog.

Both endpoints return `{items, total, limit, offset}`, cap page size at 50 and offset at 5000, and validate filter lengths. Responses intentionally omit account identity, company tax IDs, raw storage keys, full stop addresses, vehicles/drivers, customer requests, chats, payments, and payout references. Route results expose only published origin/destination cities; intermediate stops include sequence and time but no address because the current schema has no separate public-locality field. Service entries are based on `Servicios_Disponibles`; the current schema has no separate visibility status for that association. Logo URLs remain null until a safe public asset URL mechanism is implemented. Departure filters must be timezone-aware ISO-8601 datetimes.

### Hidden service types

`GET /api/service-types` lists the service types offered in the catalog. Types listed in `HIDDEN_SERVICE_TYPE_SLUGS` (`amira_api/service_type_visibility.py`) are hidden: `carga-compartida` (the old "Carga compartida" type, replaced by shared trips as an option of contracted services) is left out of the type list, returns no results from `GET /api/services?serviceType=carga-compartida`, and is not shown in a provider's service names or categories. A provider whose only type is hidden is not listed. The rows stay in `Tipos_Servicio` and every existing reference stays valid; hiding is a code-only change with no migration. On provider profile save, a hidden type cannot be newly selected (422 `Unknown service type.`), while a link the profile already has is kept even when the save omits it.

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

### Live service location (in-progress services)

While a service is `in_progress`, the assigned driver's browser sends its GPS position and the customer of that service can follow it. Only the current position is stored, in `Servicio_Ubicacion` (one row per service, primary key `ID_Servicio`, cascade on service delete). There is no trail.

- `POST /api/provider/services/{serviceId}/start` now requires a JSON body: `{"latitude": -33.4489, "longitude": -70.6693, "accuracy": 12.5}`. `accuracy` is optional (meters). Without valid coordinates it answers 422 and the service stays `confirmed`. On success the status change and the first position are written in the same transaction.
- `PUT /api/provider/services/{serviceId}/location` takes the same body and upserts the row. Only a driver assigned through `Servicio_Asignacion` can update, and only while the service is `in_progress`. Answers: 404 for a service the viewer cannot see, 403 for a viewer who can see it but is not an assigned driver (the profile owner included), 409 when the service is not in progress, 422 for invalid coordinates. Success returns the stored position.
- `GET /api/provider/services/{serviceId}/location` (owner and assigned drivers) and `GET /api/customer/services/{serviceId}/location` (the customer who owns the service) return `{latitude, longitude, accuracy, updatedAt}`. They answer 404 when the service is not in progress or has no position yet, and anyone who cannot see the service gets the same 404 as the service detail. A non-customer account gets 403 on the customer route.
- Validation: latitude -90..90, longitude -180..180, accuracy 0..100000 meters. Values are stored with the database checks too.
- Deletion: `POST .../complete` deletes the row in the same transaction. After completion, updates answer 409 and reads answer 404.
- Privacy: the position is personal data. The table has RLS enabled and no `anon`/`authenticated` privileges, and it is only reachable through these endpoints. Viewers see only the position, never the trail.

The frontend must send the position on start and then about every 15 seconds while the page is open. A web page cannot track in the background.

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

`GET /api/chats/events` is a per-user Server-Sent Events stream (`text/event-stream`). It needs the same Supabase JWT in the `Authorization` header as every other endpoint; the token is never read from the URL. Each event carries ids only: `message.created` with `{chatId, messageId}` and `quotation.changed` with `{chatId, quotationId}`. Every event also carries `fromMe`: `true` when the caller's own action caused it (for example, the caller sent the message), `false` when the other participant did. The server-side actor and recipient ids are never sent. The frontend re-reads the affected data after an event. The stream sends `: keepalive` every 20 seconds, closes when the token's `exp` passes (the client reconnects with a fresh token), and each user may hold at most 5 open streams (the sixth gets 429).

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

### Request images (private Supabase Storage bucket)

The customer can attach up to 5 images (JPEG, PNG or WebP) to a service request, for example from the quote modal. The bytes are stored in a private bucket and read back only through short-lived signed URLs. Create the bucket once per Supabase project: in the dashboard, open Storage and create a bucket named `request-images`, with **Public** switched off, then set `REQUEST_IMAGES_BUCKET=request-images` in the backend environment. The bucket name has no default: when `REQUEST_IMAGES_BUCKET` is unset or blank, the endpoints answer 503 and write nothing. It uses the same `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as the other buckets.

Optional settings and defaults: `REQUEST_IMAGE_URL_TTL_SECONDS` (300). The size cap is the chat one, `CHAT_ATTACHMENT_MAX_BYTES` (5 MiB).

- `POST /api/requests/{requestId}/images`: multipart with a required `photo`. Only the customer who owns the request may upload; other callers get 404. The type is detected from the bytes. An oversize photo gets 413, another type 415, and a sixth image 409. The count is checked under the request's row lock. The object is stored under `requests/{requestId}/{imageId}.{ext}` with a server-generated id, never the client's filename. If the database write fails, the object is deleted. The response is `{imageId}`.
- `GET /api/requests/{requestId}/images`: returns `{items: [{imageId, url, expiresAt}]}`. The owning customer, and exactly the providers who can open `GET /api/provider/requests/{requestId}`, may read it. Anyone else gets the same response that route gives them.

### Provider vehicles (private Supabase Storage bucket)

A provider (company owner or independent driver) registers the vehicles it can later assign to a shared trip. Each vehicle has one photo in a private bucket, read back only through short-lived signed URLs. The bucket is named `vehicle-images` and already exists in the Supabase project; set `VEHICLE_IMAGES_BUCKET=vehicle-images` in the backend environment. The bucket name has no default: when `VEHICLE_IMAGES_BUCKET` is unset or blank, the endpoints answer 503 to the owner and write nothing. It uses the same `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as the other buckets.

Optional settings and defaults: `VEHICLE_IMAGE_URL_TTL_SECONDS` (300). The photo size cap is `CHAT_ATTACHMENT_MAX_BYTES` (5 MiB).

Only the owner of a provider profile may use these routes; company-employed drivers and customers get 403. Another provider's vehicle is never visible: list omits it and delete answers 404 with the same body as a missing vehicle.

- `POST /api/provider/vehicles`: multipart with required `plate`, `brand`, `model` and `photo`, and optional `year` (1886 to 2200) and `maximum_weight` (above 0, kg). Plate uniqueness ignores case and surrounding spaces; a duplicate answers 409. The photo type is detected from the bytes (415 otherwise) and the size is capped (413). The object is stored under `vehicles/{profileId}/{vehicleId}.{ext}` with a server-generated id. No open transaction is held during the upload; if the database write fails, the object is deleted. Response: `{vehicleId}`, status 201.
- `GET /api/provider/vehicles`: returns `{items: [{vehicleId, plate, brand, model, year, maximumWeight, url, expiresAt}]}`, where `url` is a signed link for the photo.
- `DELETE /api/provider/vehicles/{vehicleId}`: deletes the vehicle and its photo (204). It answers 409 while any contracted service, service assignment or shared trip references the vehicle.

Schema: the photo is required (`Vehiculo.Imagen_Storage_Key` is not null). No migration is needed for these routes.

### Unread counts

Each participant has a read time, `Chat_participantes.Ultima_Lectura` (migration `20261019_0002`, default `now()`, so existing chats start read). A message is unread for a participant when another participant sent it after that time; the caller's own messages and quotations never count.

- `GET /api/chats` items carry `unreadCount`, computed in one grouped query for the whole page.
- `GET /api/chats/unread` returns `{total}`, the sum over the caller's chats.
- `POST /api/chats/{chatId}/read` sets the read time to the database `now()` and never moves it backwards. It answers 204; non-participants get 404. It publishes `chat.read` to the reader's own streams only, so their other tabs update.

## Shared trips

A shared trip is an option of a contracted service, not a service type. The customer's sharing choice (`es_exclusivo`, false when the customer accepts sharing) decides whether the provider may publish the service's route as a trip. The trip is a `Viaje` with one `Viaje_Vehiculo` (vehicle and driver), an origin stop and a destination stop. Every service on the trip carries the trip vehicle and its own pickup and delivery stops, as the composite foreign keys require. Capacity is not calculated: the provider decides per request.

Ownership uses the verified JWT and the provider-profile helper of the other provider routes. A service, vehicle or driver that is not the caller's answers 404. A customer account answers 403.

- `POST /api/provider/services/{serviceId}/shared-trip`: body `{vehicleId, driverId}`. The provider publishes a paid service. The trip copies origin, destination, communes and the requested date, and is published and accepting requests. The vehicle must belong to the caller's profile. The driver must be a company's employed driver (`Conductor` of that employer profile, role `company_driver`) or the caller's own driver record. Response: `{tripId}`, status 201. Refused with 409 when the service is exclusive (the customer did not accept sharing), already has a trip, has no requested date, or has no origin or destination. Each refusal leaves the rows unchanged.
- `POST /api/provider/shared-trips/{tripId}/close`: stops new requests (`acceptsRequests` false). Services already linked and requests already accepted stay linked. Response: `{tripId, acceptsRequests}`, status 200.
- `GET /api/provider/shared-trips?limit=20&offset=0`: the caller's trips only, ordered by departure. Items: `{tripId, status: "open" | "closed", origin, destination, departureAt, joinedServices}`, where `joinedServices` counts every service linked to the trip, the first service included. Returns `{items, total, limit, offset}`.
- `GET /api/provider/drivers`: the caller's drivers. Items: `{driverId, name, verified}`. A driver with `verified: false` cannot be put on a trip: publishing with them answers 409 (see [Driver verification](#driver-verification)).
- `POST /api/service-requests` takes an optional `requestedTripId`. When present, the request is for that trip: `originCommuneCode`/`origin` are the customer's pickup and `destinationCommuneCode`/`destination` the delivery. The customer must accept sharing: `acceptsSharing` must be `true`, otherwise the request answers 422 (`loc: ["body", "acceptsSharing"]`) and writes nothing, including when the field is omitted (its default is `false`). The trip must belong to the requested `profileId` (404 otherwise) and be published and accepting requests (409 otherwise). Without `requestedTripId` the request behaves as before. Provider inbox items expose `requestedTripId`.
- Payment is the second guard. A paid request is linked to its trip only when it carries a `requestedTripId` and is not exclusive (`es_exclusivo` false). An exclusive request is paid as a normal request and is not linked, and the stop insertion (`link_join_request_stops`) refuses an exclusive service on its own, so no stops are added for it. Linking still happens under the trip row lock, in the same transaction as the payment.
- `GET /api/shared-routes` items carry `tripId` and `departureAt`, so the frontend can start a join request.
- `GET /api/provider/services/{serviceId}` (provider detail) carries `sharedTripId`: the trip the service is linked to, or `null` when it has none. Customers always get `null`; the field is read-only and changes no other behavior.

Payment of a join request (`payment_service.confirm_payment`) runs in the same transaction as the approval. It locks the trip row, inserts the pickup and delivery stops before the destination, renumbers the route `1..n` in two phases to keep `(trip, order)` unique, and links the new service with the trip, the trip vehicle and its stops. Closing the trip does not block a request already accepted. If the trip no longer exists or has no vehicle, the payment is recorded as rejected and nothing is linked, like the other closed-quotation cases.

## Driver verification

Every driver (any user with a `Conductor` row: independent drivers, company drivers and company owners who also drive) verifies two Registro Civil certificates: the certificado de antecedentes (`criminal_record`) and the hoja de vida del conductor (`driver_record`). The driver sends each certificate's folio and verification code; the backend checks them through the `CertificateVerifier` port (`driver_certificates.py`).

- Adapters: Verifik (`verifik_certificate_verifier.py`, `GET https://api.verifik.co/v2/cl/registro-civil/certificado?folio=&verificationCode=`) when `VERIFIK_API_TOKEN` is set; the simulator only when `VERIFIK_SIMULATOR=true` and `APP_ENV` is set explicitly to `development`, `local` or `test`. Anything else answers 503. The token is server-side only. Optional: `VERIFIK_BASE_URL` (default `https://api.verifik.co`).
- Simulator codes: `ok-<RUN>` / `anot-<RUN>` give a certificado de antecedentes without or with an annotation; `hv-<RUN>` / `hvanot-<RUN>` the same for the hoja de vida; anything else is not found. It returns no PDF.
- Rule: a certificate is verified automatically only when its RUN matches the account's RUT, every register shows the declared type (registers named "...Condenas..." for antecedentes, "...Conductores..." for the hoja de vida) and every register says "No registra anotaciones". Annotations, an unrecognised response or a type that does not match go to manual review (`in_review`); another person's certificate is `rejected`. A folio can be used once per provider across all users.
- The official PDF Verifik returns is stored in the private bucket named by `DRIVER_CERTIFICATES_BUCKET` (no default: unset means 503 when Verifik is configured), under `driver-certificates/{userId}/{certificateId}.pdf`, with the same `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as the other buckets. Create the bucket as private, like the others.
- Storage: `Verificacion_Identidad` (migration `20261113_0001` adds `Tipo_Documento`, `Anotaciones`, `Clave_PDF`, `Fecha_Revision` and NOT VALID checks on status and type).

Routes (any driver; other accounts get 403):

- `GET /api/driver/verifications`: `{verified, certificates: [{type, status, reason, submittedAt, verifiedAt}]}`, one item per type; `status` is `missing`, `verified`, `in_review` or `rejected`.
- `POST /api/driver/verifications`: body `{type, folio, verification_code}` (folio 10 to 15 letters or digits). 201 with the same view. 409 when that type is already verified or in review, or the folio was used; 422 when Verifik does not find the certificate or rejects the input; 503 when Verifik or storage fails (nothing is stored). No database transaction stays open during the Verifik call.

What an unverified driver cannot do:

- An independent driver's profile lists `driver_verification` in `missing`, so `POST /api/provider/profile/publish` answers 422 and a profile save unpublishes a profile that becomes incomplete. Company profiles do not depend on it.
- `PUT /api/provider/services/{id}/assignments` answers 422 (`driver_not_verified`); `PUT /api/provider/services/{id}/driver` answers 409; `POST /api/provider/services/{id}/start` answers 409 while any assigned driver is unverified; publishing a shared trip with an unverified driver answers 409. Assignment options and `GET /api/provider/drivers` carry `verified` for each driver.

Manual review (an Amira administrator, with the backend's `DATABASE_URL`; not exposed over HTTP):

```bash
uv run python -m amira_api.review_driver_verifications list
uv run python -m amira_api.review_driver_verifications approve <certificateId>
uv run python -m amira_api.review_driver_verifications reject <certificateId> --reason "Motivo que verá el conductor"
```

Only certificates in review can be decided; the row is locked while it changes. Exit codes: 0 done, 1 no database, 2 refused.

## Checks

```powershell
uv run pytest
uv run python -c "from amira_api.main import app; print(app.title)"
uv lock --check
```

`tests/test_public_db.py` (public search) and `tests/test_payment_db.py` (simulated payment persistence) are PostgreSQL tests that are skipped unless `AMIRA_TEST_DATABASE_URL` is set. They drop and recreate their own tables: `test_public_db.py` drops the public search tables (`Regiones`, `Comunas`, `Rol_Usuario`, `Usuario`, `Rol_Perfil`, `Perfil`, `Tipos_Servicio`, `Servicios_Disponibles`), and `test_payment_db.py` drops the payment path tables plus the tables their foreign keys reference. The shared guard and engine live in `tests/postgres_support.py`, so:

- Point `AMIRA_TEST_DATABASE_URL` only at a disposable database on TCP `localhost`, `127.0.0.1` or `::1`. Unix sockets, host lists, and service files are not supported.
- The test is skipped, without connecting, unless the URL has that explicit host and none of these are set: the URL query keys `host`, `hostaddr`, `service`, `servicefile`, or the environment variables `PGHOST`, `PGHOSTADDR`, `PGSERVICE`, `PGSERVICEFILE`. libpq honours those settings over the URL, so they could send the test to a different server.
- Why: the test drops and recreates the tables above. A mistyped or redirected URL must never reach a shared or real database, so the rule is an allowlist: anything not explicitly local is skipped.
- `DATABASE_URL` is never used for this test, because it may point at a real project.
- Do not reuse the variable for a hosted or shared database.

```powershell
$env:AMIRA_TEST_DATABASE_URL = "postgresql://amira:amira@localhost:5432/amira_test"
uv run pytest tests/test_public_db.py
```

To run it against the local Supabase stack (the DB listens on `127.0.0.1:54322`):

```bash
npx supabase start
AMIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres uv run pytest tests/test_public_db.py
```

The local database has no SSL, so this test builds its engine without the forced `sslmode=require` used in production. The allowlist above is what makes that safe.

## Migrations

Alembic is initialized under `alembic/`. The declarative mappings live in `src/amira_api/models.py`; configure `DATABASE_URL` before applying migrations. Migrations are not run as part of tests and no live database is required for structural checks or offline PostgreSQL SQL generation.

## Database mapping

The ORM was mapped from the current Lucid diagram and its approved constraint notes, with English Python names and the diagram's Spanish table/column names retained in PostgreSQL. UUID primary keys use `gen_random_uuid()`; money uses fixed-precision `NUMERIC`, date-times are timezone-aware, and identity is linked by a unique Supabase Auth user UUID. Amira does not store a local password hash. `Vehiculo.Imagen_Storage_Key` is one required private-storage key; `Año` and `Peso_maximo` are optional.

`Usuario` is the complete account set. `Conductor` is a unique-user subset assigned to an employer `Perfil`; it is not itself the driver's public listing. A user may own at most one public profile, and that profile may exist without a driver record. `Rut_Empresa` is nullable because independent profiles do not require it; the profile's configured company role and any driver affiliation must be validated by the service layer because the diagram does not provide canonical role codes. `Cuenta_Desembolso` stores only a provider account reference, onboarding state, and timestamps. A payout records the destination account used for audit; no bank account, card, identity image, or credential is stored locally.

The schema enforces primary/foreign keys, one profile per user, one driver row per user, chat-member uniqueness, sender membership, one rating per service, normalized email/plate uniqueness, trip/vehicle assignment, same-trip stop references, provider-scoped external IDs/idempotency keys, and field-level checks. The current diagram contains 25 entities; `Cuenta_Desembolso` is added from its explicit Lucid note because the ERD shape is absent under the document's editing limit.

Cross-record and temporal rules remain business-transaction responsibilities unless a reviewed database trigger is installed: verify payment-provider signatures and state transitions; only reserve after successful payment; verify the quotation/chat/form/customer chain and preserve accepted commercial terms; lock capacity/exclusivity while confirming payment; validate trip ownership/roles and assignments; enforce pickup-before-delivery and publication prerequisites; keep refund-claim/payment-service references consistent; and release funds only after completion, notice, customer-conformity or the 24-hour rule, and claim checks. Foreign keys alone do not prove these invariants. RLS, grants, endpoint authorization, and public/private response shaping must be configured separately before exposing tables through Supabase Data API.

The logical ERD does not settle provider status vocabularies, canonical profile-role tokens, subcontracting policy, refund limits, currency/provider compatibility, or live concurrency and reconciliation behavior. Those are not inferred by the ORM; the application must define them before money-moving workflows are enabled.

The engine normalizes PostgreSQL URLs to Psycopg 3, requires TLS, and bounds the pool, connection timeout, and statement timeout. The public-browse migration enables RLS and revokes `PUBLIC`, `anon`, and `authenticated` privileges for all 26 application tables and `alembic_version`. It seeds clearly labeled `[DEMO]` rows with a synthetic non-login account mapping and `.invalid` email; it creates no Supabase Auth user, identity-verification, payment, or payout record.

## Unit test coverage

From this directory, run:

```bash
uv run pytest --cov=amira_api --cov-branch --cov-report=term-missing
```

Tests use local fakes; database integration tests require an explicitly configured local test database.

## Opt-in black-box suite

The black-box suite starts a real Uvicorn subprocess and a local JWKS server. It
seeds and truncates account-linked rows in an **already migrated disposable**
PostgreSQL database, exclusively `127.0.0.1:55432/postgres` with TLS. Never point
it at a developer or hosted database. The localhost redirect guard in
`tests/postgres_support.py` applies as well; URL query overrides are refused.

```bash
AMIRA_BLACKBOX_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres uv run pytest tests/blackbox -v
```

Without `AMIRA_BLACKBOX_DATABASE_URL`, all black-box tests skip before creating
sockets or connecting to PostgreSQL. `uv run pytest` remains the default runner.
The harness uses generated signing keys and local-only simulator secrets, does
not load the repository `.env`, and never imports application code for assertions.
A local in-memory Storage fake accepts uploads and signed-URL requests; it does
not prove Supabase bucket policies, real signed-URL expiry or production delivery.
Specifications and the live `/openapi.json` are the oracle.
