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

## Tasks

### S1 — Backend: assignments table and query endpoints (route: delegated direct, writer trigger: 3+ non-trivial files)

- [x] T1 Alembic migration plus model: table `Servicio_Asignacion` (`ID`, `ID_Servicio`, `ID_Conductor`, `ID_Vehiculo`, `Fecha_Asignacion`, `ID_Usuario_Asigna`), unique (`ID_Servicio`, `ID_Conductor`) and (`ID_Servicio`, `ID_Vehiculo`), RLS enabled with privileges revoked from `anon`/`authenticated` like the other tables. Add CHECK `Servicio.Estado IN ('confirmed','in_progress','completed','disputed')`. Add `Servicio.Fecha_Inicio_Real` (`started_at`) and `ID_Usuario_Inicio` only if `starts_at` does not already cover it (`starts_at` maps to `Fecha_Inicio`; reuse it for the actual start).
- [x] T2 `GET /api/provider/services` and `GET /api/provider/services/{id}` with the visibility rules above, in a new `provider_service_routes.py` with `provider_service_schemas.py`.
- [x] T3 `GET /api/customer/services/{id}` detail. Extend the customer list with `status` only if this does not break the rating flow.
- [x] T4 Tests: owner sees the profile's services; an employed driver sees only assigned ones; another provider gets 404; a customer gets 403 on provider routes; a customer cannot read another customer's service; migration structural test like the existing `test_*_migration.py`.

### S2 — Backend: assignments and start

- [ ] T5 `PUT /api/provider/services/{id}/assignments` (owner only, status `confirmed`) replaces all pairs. It validates that drivers belong to the profile (or are the independent owner) and vehicles belong to the profile, and applies the same-day 409 with `confirmSameDayConflicts`.
- [ ] T6 `POST /api/provider/services/{id}/start` (assigned driver or owner; needs ≥ 1 assignment; `FOR UPDATE` and re-check the status).

### S3 — Backend: completion with delivery photo

- [ ] T7 `POST /api/provider/services/{id}/complete` multipart (assigned driver; `in_progress`; JPEG/PNG/WebP, size cap). It uploads to a private Supabase Storage bucket and sets `delivery_evidence_key`, `completed_at`, `completion_notified_at` and `payout_deadline_at`. It also adds a signed-URL endpoint for the customer and the provider.

### S4 — Backend: claims, consent and payout release

- [ ] T8 `POST /api/customer/services/{id}/claims` (within the window → `disputed`) and `POST /api/customer/services/{id}/consent`.
- [ ] T9 `PayoutProvider` port plus a simulated adapter; idempotent `release_due_payouts` (`FOR UPDATE`, no open claim, no existing `Desembolso`, payout account required); a CLI entry point and a Render Cron Job in `render.yaml`.

### S5 — Frontend

Skills: `ui-ux-pro-max`, `impeccable`, `vercel-react-best-practices`, `boneyard`.

- [ ] T10 Shared presentational `ServiceCard` / `ServiceDetail`; role-based containers at `/cuenta/servicios` and `/cuenta/servicios/[serviceId]`; rename the menu entry to "Mis servicios".
- [ ] T11 Assignment form with the same-day warning dialog; Iniciar / Finalizar (with photo) actions.
- [ ] T12 Customer: delivery photo, deadline countdown, "Todo conforme", "Reclamar".

## Checks

- Backend: `uv run pytest`, `uv lock --check`. Frontend: `npm run lint`, `npm run build`. Playwright is not used for verification.

## Progress

- 2026-10-11: plan approved; branch `feat/services-lifecycle` created. Next: S1.
- 2026-10-11: S1 done (route: delegated direct, writer trigger: 3+ non-trivial files). Migration `20261011_0003_service_assignments` adds `Servicio_Asignacion` (RLS, revoked from `anon`/`authenticated`, indexes on driver and vehicle), `Servicio.ID_Usuario_Inicio` (nullable FK, for S2) and `ck_service_status_allowed` (NOT VALID then VALIDATE). Shared query/shaping in `service_views.py`; provider routes in `provider_service_routes.py`; customer detail in `customer_routes.py`, and the customer list now also returns `status`. RED: new route tests failed at import (`ServicioAsignacion` missing), migration tests failed (file missing), customer list test failed (no `status`). GREEN: `uv run pytest` 428 passed; `uv lock --check` passed. Next: S2.

### API notes (S1)

- Contract implemented as written. Unknown (unprovisioned) accounts get 403 "A provisioned provider account is required."; provisioned non-provider accounts get "Only provider accounts can access provider services.".
- `amount` is an integer CLP (or null); `currency` comes from the accepted quotation; `chatId` is the accepted quotation's chat.
- A user who both owns a profile and is employed by another company is treated as the owner.
