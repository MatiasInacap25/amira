# Services lifecycle: "Mis servicios" for customers and providers

## Objective

Give customers and providers (independent drivers and companies) one "Mis servicios" window for contracted services. Providers assign one or more driver + vehicle pairs and start the service. A driver finishes it by uploading a delivery photo. The customer then has a claim window. A claim holds the payout; if there is no claim, the payout is released automatically.

## Problem and why

Today a `Servicio` is created with status `confirmed` when the payment is confirmed (`payment_service.py`), and nothing happens after that. Customers can list and rate services at `/cuenta/servicios` (`GET /api/customer/services`). Providers cannot see their contracted services, assign people or vehicles, or close the service, so the payout rule in `backend/README.md` (completion, notice, customer conformity or the 24-hour rule, and claim checks) cannot run.

## Current state (2026-10-11)

- `Servicio` has single `contracted_driver_id` and `vehicle_id` columns. `ck_service_trip_vehicle_pair` allows `vehicle_id` only together with `trip_id` (shared routes), so these columns cannot hold a regular service's assignment.
- `Servicio` already has `delivery_evidence_key`, `completed_at`, `completion_notified_at`, `customer_consent_at` and `payout_deadline_at`. `Reclamo` and `Desembolso` exist, with no endpoints. `Desembolso` requires a `Cuenta_Desembolso`.
- A company's drivers are `Conductor` rows whose `employer_profile_id` is the company `Perfil`. Vehicles belong to a `Perfil` (`Vehiculo.profile_id`).
- There is no scheduler in the repo and no payout provider has been chosen.
- Ownership (verified in S1): a provider `Perfil` has exactly one owner (`Perfil.owner_user_id`, unique). Company owners and independent drivers both own one. An independent driver also has a `Conductor` row with `employer_profile_id` NULL (`account_routes.py`); a company driver has a `Conductor` row whose `employer_profile_id` is the company profile (`invitation_routes.py`) and owns no profile.
- Only `payment_service.py` creates `Servicio` rows, always with status `confirmed`, so the status CHECK is safe on live data. `starts_at` (`Fecha_Inicio`) is never set today; it is reused as the actual start time.

## Decisions (user, 2026-10-11)

- Providers assign one or more (driver, vehicle) pairs per service.
- Start: the assigned driver or the profile owner can start the service. The actor is recorded.
- Finish: an assigned driver finishes the service by uploading a required delivery photo (private storage; the customer sees it through a short-lived signed URL).
- Claim window: 24 h after completion, configurable. A claim holds the payout. Customer consent releases it early. If there is no claim, it is released automatically when the deadline passes.
- Claim resolution (who decides, refunds) is out of scope.
- Double booking is allowed: a driver may have several services on the same day. Assigning a driver who already has a non-finished service that day (calendar day in `America/Santiago`) needs explicit confirmation: the backend returns 409 with the conflicts unless the request sends `confirmSameDayConflicts: true`, and the frontend shows a warning dialog before resending.
- Service states: `confirmed`, `in_progress`, `completed`, `disputed`. A released payout is a `Desembolso` row, not a service state.
- Payouts go through a simulated adapter behind a port, like payments, and refuse to run when `APP_ENV` is `production`.

## Delivery strategy

`auto-chain`, `stacked-to-main`: one PR per slice, each with its tests. Forecast about 1,800 authored changed lines.

| Slice | Content | Branch |
| --- | --- | --- |
| S1 | Assignment table, status CHECK, query endpoints | `feat/services-lifecycle` |
| S2 | Assignments + start + same-day warning (backend) | next |
| S3 | Completion with delivery photo | next |
| S4 | Claims, consent, payout release job, simulated payout | next |
| S5 | Frontend "Mis servicios" | next |

## API contract (S1)

Public JSON is camelCase. All endpoints use `get_current_user`. A service that the viewer cannot see returns 404, never 403.

1. `GET /api/provider/services?status&limit&offset` → `{items, total, limit, offset}`, the same page caps as the other lists. Visibility:
   - the owner of a provider `Perfil` sees every service whose `profile_id` is that profile;
   - a company-employed driver who does not own the profile sees only the services they are assigned to through `Servicio_Asignacion`.
   - Any other account gets 403 ("Only provider accounts can access provider services."), consistent with `customer_routes.py`.
2. `GET /api/provider/services/{serviceId}` → `ServiceDetail` for the provider viewer.
3. `GET /api/customer/services/{serviceId}` → `ServiceDetail` for the customer who owns it.
4. List item: `{serviceId, status, serviceTypeName, serviceAt, amount, currency, originCommune, destinationCommune, isExclusive, counterpartName, assignmentCount}`. `counterpartName` is the provider's display name for the customer, and the customer's first name for the provider. No contact details.
5. `ServiceDetail` = list item fields + `{chatId, description, createdAt, startedAt, completedAt, payoutDeadlineAt, viewerRole: "customer"|"provider", canManage: bool, assignments: [{driverId, driverFirstName, vehicleId, vehicleLabel ("Marca Modelo"), plate}]}`. `canManage` is true only for the profile owner.

## API contract (S2)

Both endpoints use `get_current_user` and the S1 viewer rules: a non-provider account gets 403, and a service the viewer cannot see gets 404. Both return `ServiceDetail` (camelCase) on success.

1. `PUT /api/provider/services/{serviceId}/assignments`: replaces all (driver, vehicle) pairs of the service in one transaction. The service row is locked with `FOR UPDATE`.
   - Body: `{assignments: [{driverId, vehicleId}], confirmSameDayConflicts: bool = false}`. `assignments` needs at least one pair. `driverId` and `vehicleId` must each be unique within the list.
   - Only the profile owner may call it. Drivers must be `Conductor` rows employed by the owned profile, or the owner's own independent driver row. Vehicles must belong to the owned profile.
   - Records the caller as `assignedByUserId` and the time as `assignedAt`. The caller is taken from the auth session, never from the body.
   - Errors, in evaluation order:
     - 404 `Service not found.` (not visible to the viewer)
     - 403 `Only the profile owner can manage this service.` (visible, not the owner)
     - 409 `Only confirmed services can be assigned.` (status is not `confirmed`)
     - 422 for an empty list or a duplicate `driverId`/`vehicleId` (Pydantic validation), a driver outside the profile (`driver_not_in_profile`), or a vehicle outside the profile (`vehicle_not_in_profile`). The body is FastAPI's list format, with `loc: ["body", "assignments"]`.
     - 409 same-day conflicts, body `{detail: "Some drivers already have a service on the same day.", conflicts: [{driverId, serviceId, serviceAt}]}`. A conflict is another service of the same driver with status `confirmed` or `in_progress` whose `serviceAt` falls on the same calendar day in `America/Santiago`. Nothing is written. Resend with `confirmSameDayConflicts: true` to save.
2. `POST /api/provider/services/{serviceId}/start`: no body. Allowed for the profile owner and for assigned drivers. An employed driver who is not assigned cannot see the service, so gets 404. The service row is locked with `FOR UPDATE`, and the status is re-checked after the lock.
   - Sets `status` to `in_progress`, `startedAt` to the current UTC time, and records the caller as the starter.
   - Errors:
     - 404 `Service not found.`
     - 409 `Only confirmed services can be started.` (also returned on a second start)
     - 409 `Assign at least one driver and vehicle before starting.`
3. `GET /api/provider/services/{serviceId}/assignment-options`: the drivers and vehicles that `PUT .../assignments` accepts, for the assignment form. Owner only; no status requirement.
   - 200: `{drivers: [{driverId, firstName, lastName, isOwner}], vehicles: [{vehicleId, vehicleLabel ("Marca Modelo"), plate}]}`. Drivers are the `Conductor` rows employed by the owned profile, plus the owner's own independent driver row (`isOwner: true`). Vehicles are the rows of the owned profile. Drivers are sorted by first name, last name, id; vehicles by label, plate, id. No contact details. The PUT and this endpoint share the same driver and vehicle predicates.
   - 404 `Service not found.` (not visible to the viewer)
   - 403 `Only the profile owner can manage this service.` (visible, not the owner)
   - Non-provider accounts get the S1 403 (`Only provider accounts can access provider services.`).

## API contract (S3)

Public JSON is camelCase. All endpoints use `get_current_user` and the S1 viewer rules: a non-provider account gets 403 on provider routes, a non-customer gets 403 on customer routes, and a service the viewer cannot see gets 404.

1. `POST /api/provider/services/{serviceId}/complete`: `multipart/form-data` with one required file field, `photo`. No other fields.
   - Only an assigned driver can complete: the viewer's `Conductor` must have a `Servicio_Asignacion` row for the service. The profile owner who is not assigned gets 403. The service row is locked `FOR UPDATE` and its status is re-checked after the lock.
   - The type is decided by magic bytes (JPEG, PNG or WebP). The declared content type and the client file name are ignored.
   - The bytes are uploaded before any write, to the private bucket under `services/{serviceId}/{uuid}.{jpg|png|webp}`. The database is written only after the upload succeeds.
   - Sets `status` to `completed`, `delivery_evidence_key`, `completed_at` = now, `completion_notified_at` = now and `payout_deadline_at` = now + `SERVICE_CLAIM_WINDOW_HOURS`.
   - 200: `ServiceDetail` with `status: "completed"` and `deliveryPhotoAvailable: true`.
   - Errors, in evaluation order:
     - 404 `Service not found.` (not visible to the viewer)
     - 403 `Only an assigned driver can complete this service.` (visible, not assigned)
     - 409 `Only in-progress services can be completed.` (also on a second completion)
     - 413 `The delivery photo is larger than the allowed size.` (cap: `SERVICE_EVIDENCE_MAX_BYTES`; the size is counted on the bytes read, not on Content-Length)
     - 415 `The delivery photo must be a JPEG, PNG or WebP image.`
     - 502 `The delivery photo could not be stored. Try again.` (nothing written; the service stays `in_progress`)
     - 422 FastAPI validation when `photo` is missing
     - 503 `Delivery photo storage is not configured.` (`SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` unset; the storage dependency resolves before the handler, so this applies to every request on the route)
2. `GET /api/provider/services/{serviceId}/delivery-photo`: any provider viewer who can see the service (owner or assigned driver).
3. `GET /api/customer/services/{serviceId}/delivery-photo`: the customer who owns the service.
   - 200: `{url, expiresAt}`. `url` is a signed read URL valid for `SERVICE_EVIDENCE_URL_TTL_SECONDS`; `expiresAt` is now + that TTL.
   - 404 `Service not found.` (not visible, not owned, including another customer's service).
   - 404 `Delivery photo not found.` (no evidence yet).
   - 502 `The delivery photo could not be retrieved. Try again.` (signing failed).
   - 503 as in endpoint 1.
4. `ServiceDetail` (provider and customer detail) gains `deliveryPhotoAvailable: bool`. The storage key and signed URLs never appear in list, detail or completion responses.

New settings (read from the backend environment; setup in `backend/README.md`, "Delivery photos"):

| Setting | Default | Notes |
| --- | --- | --- |
| `SUPABASE_URL` | unset | Project URL. Required for photo endpoints. |
| `SUPABASE_SERVICE_ROLE_KEY` | unset | Server-side only. Never a `NEXT_PUBLIC_*` value. |
| `SERVICE_EVIDENCE_BUCKET` | `service-evidence` | Private bucket, created by an operator, not by code. |
| `SERVICE_EVIDENCE_MAX_BYTES` | `8388608` (8 MiB) | Must be positive. |
| `SERVICE_EVIDENCE_URL_TTL_SECONDS` | `300` | Must be positive. |
| `SERVICE_CLAIM_WINDOW_HOURS` | `24` | Must be positive. |

## API contract (S4)

Public JSON is camelCase. The customer routes use `get_current_user` and the customer rules of S3: a non-customer gets 403 and a service the customer does not own gets 404 (`Service not found.`). Both writes lock the service row `FOR UPDATE` and re-check its state after the lock. Nothing is written on any error.

1. `POST /api/customer/services/{serviceId}/claims`: body `{reason}`. `reason` is trimmed and required, 1 to 1000 characters; anything else is 422. Checks run in this order:
   - 409 `This service already has an open claim.`
   - 409 `Only completed services can be claimed.` (covers a service that is not yet completed)
   - 409 `Consent was already given for this service.`
   - 409 `The claim window for this service has closed.` (now at or after `payoutDeadlineAt`, or no deadline)
   - 200 on success: inserts a `Reclamo` with status `open` and the reason, sets the service `status` to `disputed`, and returns `ServiceDetail`.
2. `POST /api/customer/services/{serviceId}/consent`: no body. Checks run in this order:
   - 409 `A service with an open claim cannot receive consent.`
   - 409 `Only completed services can receive consent.`
   - 409 `Consent was already given for this service.`
   - 200 on success: sets `customerConsentAt` to now, keeps `status` `completed`, and returns `ServiceDetail`. The payout is due at the next release run.
3. `ServiceDetail` (provider and customer) gains:

   | Field | Type | Meaning |
   | --- | --- | --- |
   | `customerConsentAt` | datetime or null | When the customer gave consent |
   | `claimOpen` | bool | True while a claim on the service is open |
   | `canClaim` | bool | Customer only: completed, no open claim, no consent, inside the claim window |
   | `canConsent` | bool | Customer only: completed, no open claim, no consent yet |

   Providers always get `canClaim: false` and `canConsent: false`. No claim text is exposed in any response.

4. Payout release (no HTTP endpoint). `release_due_payouts(session, now, provider)` in `payout_service.py` releases a service when all of these hold: `status` is `completed`; there is no open claim; there is no `Desembolso` for the service; and either `customerConsentAt` is set or `payoutDeadlineAt` is at or before `now`. Each service runs in its own transaction and is locked with `FOR UPDATE SKIP LOCKED`; the conditions are checked again under the lock. It needs an approved `Pago` for the accepted quotation and an enabled `Cuenta_Desembolso` on the service's profile. It returns a `PayoutSummary` with the counts `due`, `released`, `missing_account`, `missing_payment`, `skipped` and `failed`. A provider failure rolls back that service only and counts it as `failed`. The payout idempotency key is `service:{serviceId}:payout`, so a repeat run creates no second payout.
5. Port and adapter: `PayoutProvider` in `payout_provider.py` (`create_payout(PayoutRequest) -> PayoutResult`, raising `PayoutProviderError` on refusal). `SimulatedPayoutProvider` in `simulated_payout_provider.py` never moves money. It refuses to start unless `APP_ENV` is an allowlisted development value, the same allowlist as the simulated payment adapter.
6. CLI and cron: `python -m amira_api.release_payouts` (`release_payouts.py`). It exits 0 when the run completes, including when single services failed. It exits 1 when the job cannot run: the adapter is refused for this `APP_ENV`, `APP_ENV` is not set explicitly, or `DATABASE_URL` is not configured. The summary is logged. `render.yaml` has the Render Cron Job `amira-release-payouts-dev` (`schedule: "*/15 * * * *"`, `dockerCommand: python -m amira_api.release_payouts`) with the same `envVars` as the web service, which is unchanged.

Settings: no new variables. `SERVICE_CLAIM_WINDOW_HOURS` (S3) sets the window.

## Tasks

### S1 — Backend: assignments table and query endpoints (route: delegated direct, writer trigger: 3+ non-trivial files)

- [x] T1 Alembic migration plus model: table `Servicio_Asignacion` (`ID`, `ID_Servicio`, `ID_Conductor`, `ID_Vehiculo`, `Fecha_Asignacion`, `ID_Usuario_Asigna`), unique (`ID_Servicio`, `ID_Conductor`) and (`ID_Servicio`, `ID_Vehiculo`), RLS enabled with privileges revoked from `anon`/`authenticated` like the other tables. Add CHECK `Servicio.Estado IN ('confirmed','in_progress','completed','disputed')`. Add `Servicio.Fecha_Inicio_Real` (`started_at`) and `ID_Usuario_Inicio` only if `starts_at` does not already cover it (`starts_at` maps to `Fecha_Inicio`; reuse it for the actual start).
- [x] T2 `GET /api/provider/services` and `GET /api/provider/services/{id}` with the visibility rules above, in a new `provider_service_routes.py` with `provider_service_schemas.py`.
- [x] T3 `GET /api/customer/services/{id}` detail. Extend the customer list with `status` only if this does not break the rating flow.
- [x] T4 Tests: owner sees the profile's services; an employed driver sees only assigned ones; another provider gets 404; a customer gets 403 on provider routes; a customer cannot read another customer's service; migration structural test like the existing `test_*_migration.py`.

### S2 — Backend: assignments and start (route: delegated direct, Haiku worker in a Herdr pane; writer trigger: 2+ non-trivial files)

- [x] T5 `PUT /api/provider/services/{id}/assignments` (owner only, status `confirmed`) replaces all pairs. It validates that drivers belong to the profile (or are the independent owner) and vehicles belong to the profile, and applies the same-day 409 with `confirmSameDayConflicts`.
- [x] T6 `POST /api/provider/services/{id}/start` (assigned driver or owner; needs ≥ 1 assignment; `FOR UPDATE` and re-check the status).
- [x] T5b (added 2026-10-11, plan gap found before T11) `GET /api/provider/services/{id}/assignment-options` (owner only): drivers and vehicles accepted by the PUT, sharing its filters.

### S3 — Backend: completion with delivery photo (route: delegated direct, Haiku worker in a Herdr pane; writer trigger: 2+ non-trivial files)

- [x] T7 `POST /api/provider/services/{id}/complete` multipart (assigned driver; `in_progress`; JPEG/PNG/WebP, size cap). It uploads to a private Supabase Storage bucket and sets `delivery_evidence_key`, `completed_at`, `completion_notified_at` and `payout_deadline_at`. It also adds a signed-URL endpoint for the customer and the provider.

### S4 — Backend: claims, consent and payout release (route: delegated direct, Haiku worker in a Herdr pane; writer trigger: 2+ non-trivial files)

- [x] T8 `POST /api/customer/services/{id}/claims` (within the window → `disputed`) and `POST /api/customer/services/{id}/consent`.
- [x] T9 `PayoutProvider` port plus a simulated adapter; idempotent `release_due_payouts` (`FOR UPDATE`, no open claim, no existing `Desembolso`, payout account required); a CLI entry point and a Render Cron Job in `render.yaml`.

### S5 — Frontend

Skills: `ui-ux-pro-max`, `impeccable`, `vercel-react-best-practices`, `boneyard`.

- [x] T10 Shared presentational `ServiceCard` / `ServiceDetail`; role-based containers at `/cuenta/servicios` and `/cuenta/servicios/[serviceId]`; rename the menu entry to "Mis servicios".
- [x] T11 Assignment form with the same-day warning dialog; Iniciar / Finalizar (with photo) actions.
- [x] T12 Customer: delivery photo, deadline countdown, "Todo conforme", "Reclamar".

## Checks

- Backend: `uv run pytest`, `uv lock --check`. Frontend: `npm run lint`, `npm run build`. Playwright is not used for verification.

## Progress

- 2026-10-11: plan approved; branch `feat/services-lifecycle` created. Next: S1.
- 2026-10-11: S1 done (route: delegated direct, writer trigger: 3+ non-trivial files). Migration `20261011_0003_service_assignments` adds `Servicio_Asignacion` (RLS, revoked from `anon`/`authenticated`, indexes on driver and vehicle), `Servicio.ID_Usuario_Inicio` (nullable FK, for S2) and `ck_service_status_allowed` (NOT VALID then VALIDATE). Shared query/shaping in `service_views.py`; provider routes in `provider_service_routes.py`; customer detail in `customer_routes.py`, and the customer list now also returns `status`. RED: new route tests failed at import (`ServicioAsignacion` missing), migration tests failed (file missing), customer list test failed (no `status`). GREEN: `uv run pytest` 428 passed; `uv lock --check` passed. Commit `441a4ca`. Native review (reliability lens): approved and acknowledged (lineage `review-7b7dfe5d20a480d3`). Parent spot check: `uv run pytest` 428 passed.
- 2026-10-11: T10 done in parallel (route: delegated direct in an isolated worktree, Haiku worker), cherry-picked as `ab5a431`. Role comes from `GET /api/account/me` (`isProviderRole`); the menu entry is now "Mis servicios". RED exception: no frontend unit runner, Playwright not used. Parent check: `npm run lint` and `npm run build` passed. Native review (reliability lens): approved and acknowledged (lineage `review-c06172a440bbfa43`). Next: S2 (launch the worker in a Herdr pane, with Haiku).
- 2026-10-11: S2 (T5, T6) done by `worker-1` (Haiku, Herdr pane), commit `f4c15fb`. RED: 19 of 22 new tests failed before implementation (routes missing). GREEN: `uv run pytest` 450 passed; `uv lock --check` passed. Parent spot check: `uv run pytest` 450 passed. The API contract (S2) section was added. Follow-ups: `R3-viewer-query-multiple-rows` cannot occur (`uq_conductor_user` and the unique `Perfil.ID_user` / `Usuario.ID_Auth_Supabase` limit the join to one row), but the lookup is now ordered and limited to one row anyway. `R3-started-by-fk-validate` was not reproducible (migration 0003 line 62 already validates `fk_service_started_by`), so no 0004 migration was added; a guard test was added instead. Native review (assess: medium, `slice_budget_reached`; reliability lens) granted, approved and acknowledged (lineage `review-ed85fcd06adaf678`). Next: S3 (T7).
- 2026-10-11: branch review (base `1e72235`..`1f273a8`, requested by the stop hook, granted): approved and acknowledged (lineage `review-f906f2bf9346b57c`).
- 2026-10-11: S3 (T7) done by `worker-1` (Haiku, Herdr pane), commit `1ab9984`. RED: collection failed with `ModuleNotFoundError: amira_api.evidence_storage`; settings tests failed on missing `supabase_url`. GREEN: `uv run pytest` 483 passed; `uv lock --check` passed. Parent spot check: `uv run pytest` 483 passed. The API contract (S3) section was added. Gap: `backend/.env.example` was not updated (the worker's permissions denied access); the six new variables are documented in `backend/README.md` and the S3 contract. Native review (assess: medium, `slice_budget_reached`; reliability lens) granted, approved and acknowledged (lineage `review-08a95a100032fcbd`). Next: S4 (T8, T9) and T11 in parallel.
- 2026-10-11: T5b done by `worker-1`, commit `66fbe7b`. RED: 11 of 11 failed (route missing; detail texts asserted). GREEN: `uv run pytest` 494 passed; `uv lock --check` passed. Parent spot check: 494 passed. Branch review (base `1e72235`, includes T5b) approved and acknowledged (lineage `review-45a21e63e75a56c0`).
- 2026-10-11: T11 done by `worker-2` (Haiku, second Herdr pane, in parallel with S4; frontend-only surface), commit `0460973`. RED exception: no frontend unit runner, Playwright not used. `npm run lint` and `npm run build` passed (worker); parent spot check `npm run lint` passed.
- 2026-10-11: S4 (T8, T9) done by `worker-1`, commit `ee05151`. RED: claim/consent tests got 404 (routes missing, detail texts asserted); payout tests failed at import. GREEN: `uv run pytest` 522 passed; `uv lock --check` passed. Parent spot check: 522 passed. No new env variables.
- 2026-10-11: a branch-wide review (5035 lines) stopped with `lens_context_budget_exceeded`; the reduced candidate T11 + S4 (base `66fbe7b`, 1777 lines) was granted, approved and acknowledged (lineage `review-e20c3dcf15c36461`). Next: T12.
- 2026-10-11: T12 done by `worker-2`, commit `de94225`. RED exception: no frontend unit runner, Playwright not used. `npm run lint` and `npm run build` passed (worker); parent spot check `npm run lint` passed. Shared query keys in `service-query-keys.ts`; provider mutations now also invalidate the customer list (closes that T11 gap). Native review (assess: medium, `slice_budget_reached`; base `ee05151`) granted, approved and acknowledged (lineage `review-d0f3cd3ef53bbc61`). All tasks done. Next: user decisions on follow-ups, then delivery (push/PR) when the user asks.

### Review follow-ups (non-blocking)

- S1 `R3-employed-driver-owner-precedence` (`provider_service_routes.py:33-35`): a profile owner who is also employed elsewhere only sees their own profile's services.
- S1 `R3-customer-detail-assignments` (`customer_routes.py:146-147`): the customer detail's assignments are not covered by a test.
- S1 `R3-status-check-existing-rows` (migration `0003`, lines 55-59): before upgrading the live DB, confirm every `Servicio.Estado` value is `confirmed`.
- S1 `R3-provider-list-status-filter-untested-combo`: the status filter combined with employed-driver visibility is not tested.
- T10 `R3-role-query-error-falls-back-to-customer` (`app/cuenta/servicios/page.tsx:20-29`): a failed role lookup shows the customer view to a provider.
- T10: the role query (`["services-account-role"]`, staleTime 60 s) is not cleared on sign-out; there is also no retry on transient errors, and the 404 handling and list filter keys could be tightened.
- Branch review (lineage `review-99ed10dbd12a7060`, approved): `R3-viewer-query-multiple-rows` (`provider_service_routes.py:41-47`): the viewer lookup may return several rows. `R3-started-by-fk-validate` (migration `0003`, lines 49-51): the `fk_service_started_by` FK is not validated. Fix both in S2. (Resolved in S2, see Progress.)
- S2 `R3-001` (`provider_service_routes.py:149-167`, WARNING): the same-day conflict check is not serialized across services; two concurrent assignments of one driver to different services on the same day can both pass. Double booking is allowed by design, so only the warning is skipped.
- S2 `R3-002` (`test_service_started_by_fk_migration.py:22-23`, SUGGESTION): the guard does not tie `NOT VALID` to the `fk_service_started_by` statement.
- Branch review `R3-002` (`provider_service_schemas.py:23`): `currency` is `Literal["CLP"]`; a non-CLP row makes the whole provider list or detail fail.
- Branch review `R3-005` (`test_service_assignment_migration.py:68`): the ordering guard matches the started-by FK's `NOT VALID`, not the status CHECK's.
- S3 `R3-001` (`provider_service_routes.py:344`): a commit failure after a successful upload leaves an orphaned photo; the storage port has no delete.
- S3 `R3-002` (`provider_service_routes.py:327`): the upload runs while the service row lock is held (up to the 10 s httpx timeout).
- S3 `R3-003` (`evidence_storage.py:61-62`): the 503 "not configured" branch is untested.
- S3 worker notes: Starlette spools the multipart part to disk before the size cap runs (add a proxy body limit); 503 precedes 403/404 when storage is not configured; add the new variables to `backend/.env.example`.
- Branch review `R3-003` (`models.py:474-475`): `fk_service_started_by` is `ON DELETE RESTRICT`, so deleting a user who started a service fails.
- T11 gaps: `ServiceDetail` does not say whether the viewer is assigned, so Iniciar/Finalizar show for every provider viewer and the backend decides (suggest `viewerAssigned`); no success notice after saving assignments; provider mutations do not invalidate the customer list query; `ui-ux-pro-max` and `boneyard` were not read; not exercised in a browser.
- S4 decisions to confirm: `Monto_Neto` equals the gross payment (no commission model); release requires an approved `Pago` (else `missing_payment`); `claimOpen` is `status == 'disputed'` (a `Reclamo` join broke SQLite fixtures; the release job still checks `Reclamo`).
- S4 `R3-001` (`render.yaml:41-42`): the cron sets `APP_ENV=production`, so the simulated adapter refuses and every run exits 1 until a real payout adapter exists.
- S4 `R3-002` (`test_payout_release.py:202-205`): the production-refusal CLI test only asserts exit 1, which other failures also produce.
- S4 `R3-003` (`customer_routes.py:318-323`): consent is accepted after the payout was already released.
- S4 environment note: with `DEV_SKIP_SMS_MFA` set, settings reject `APP_ENV=production`; check the real deploy config.
- T12 `R3-001` (`claim-window-countdown.tsx:22`): before mount the window counts as open, so "Reclamar" can flash for an expired window (the backend still rejects with 409).
- T12 `R3-002` (`claim-window-countdown.tsx:40`): a missing deadline is shown as "Plazo vencido. El pago se libera sin reclamo."
- T12 `R3-003`/`R3-004`: the countdown transition and the 409 copy mapping (which matches the backend's English `detail` strings) are untested; there is no frontend unit runner.
- T12 `R3-005` (`customer-service-actions.tsx:68`): the double-submit guard reads a render-time `busy`, so two fast clicks can send two POSTs.

### API notes (S1)

- Contract implemented as written. Unknown (unprovisioned) accounts get 403 "A provisioned provider account is required."; provisioned non-provider accounts get "Only provider accounts can access provider services.".
- `amount` is an integer CLP (or null); `currency` comes from the accepted quotation; `chatId` is the accepted quotation's chat.
- A user who both owns a profile and is employed by another company is treated as the owner.
