# Provider profile page

## Objective

Polish the public provider profile (`/prestadores/[profileId]`) so independent drivers and companies share one structure with a clear "Cotizar" action, catalog-backed location, company-only driver list, vehicles, services, and ratings; and let customers rate completed services so ratings can actually exist.

## Current state (2026-10-10 audit)

- `GET /api/providers/{profile_id}` (`backend/src/amira_api/public_routes.py:73`) already returns `providerName`, `kind`, `description`, free-text `location`, `ownerName`, `drivers`, `vehicles` (brand, model, year, maximumWeight), `services`, and `ratings` (average, count, 20 most recent; only customer-authored ratings of completed services, policy approved 2026-10-04).
- `frontend/src/components/marketplace/provider-profile-view.tsx` renders Resumen, Flota, Conductores, Servicios, Valoraciones, and a "Solicitar cotización" button that opens `QuoteRequestDialog` with `selectedServiceId=""`.
- No endpoint or UI exists to create a rating (`Valoracion`: one per service, rating 1–5, comment).
- Privacy allowlist stays unchanged: never expose RUT, birth date, email, phone, auth IDs, plates, storage keys, or rating author/service IDs.

## Decisions

- Same page structure for both kinds; the Conductores section renders only for `kind === "company"`.
- Rating creation is in scope (user approved 2026-10-10).
- Out of scope: real logo and vehicle photos (need Supabase Storage signed URLs), vehicle type (no column).
- Workers do not commit; the orchestrator commits each verified unit. No Playwright (headless Chromium here never fires requestAnimationFrame).

## API contract

Public JSON is camelCase (existing alias generator).

1. `GET /api/providers/{profile_id}` adds `communeCode`, `communeName`, `regionName` (nullable, from `Perfil.Codigo_Comuna` joined to the catalog). `location` becomes `"<Comuna>, <Región>"` when a commune exists, else the legacy text. Each driver adds `isOwner: boolean`.
2. `GET /api/customer/services` (authenticated, same auth dependency as `POST /api/service-requests`): the caller's services, newest first, paginated (`limit` ≤ 50, `offset`): `{"items": [{"serviceId", "providerProfileId", "providerName", "serviceTypeName", "completedAt", "rating": null | {"rating", "comment", "createdAt"}}], "total", "limit", "offset"}`.
3. `POST /api/customer/services/{service_id}/rating` (authenticated) body `{"rating": 1..5, "comment": string | null (max 1000, trimmed)}` → 201 with the stored rating. 404 when the service does not exist or the caller is not its customer (do not leak existence); 409 `already_rated`; 422 `service_not_completed`. Spanish messages, standard 422 shape.

## Tasks

### Backend (worker `backend`, from `backend/`)

Route: delegated direct (Herdr worker, Haiku 5.5). Skills: `sqlalchemy-alembic-expert-best-practices-code-review`, `fastapi-templates`, `supabase`.

- [x] PB1 Profile location from catalog: contract 1 (commune/region fields and `location` display). Tests.
- [x] PB2 Driver owner flag: contract 1 `isOwner`. Tests.
- [x] PB3 Customer services and rating creation: contracts 2 and 3, in a new `customer_routes.py` + `customer_schemas.py` wired in `main.py`; enforce ownership, completion, and one rating per service (rely on the existing unique constraint and map the integrity error to 409). Tests for each rule.

Verification: `uv run pytest -q`, `uv lock --check`.

### Frontend (worker `frontend`, from `frontend/`)

Route: delegated direct (Herdr worker, Haiku 5.5). Read `frontend/CLAUDE.md` first. Skills: `ui-ux-pro-max` and `impeccable` (mandatory for design decisions), plus `vercel-react-best-practices`. Keep the existing visual language of the site (globals.css tokens, typography) unless the skills justify a change. UI copy in Spanish.

- [x] PF1 Profile redesign: one structure for both kinds. Hero: initials avatar (no logo yet), name, kind badge, "<Comuna>, <Región>", average rating with count; primary "Cotizar" button always visible (sticky bottom bar on mobile). Sections: Servicios, Vehículos, Valoraciones (summary + recent reviews), and Conductores only for companies (mark the owner). Accessible headings, empty states, loading and error states, responsive down to 360px.
- [x] PF2 Per-service "Cotizar": each service card opens `QuoteRequestDialog` with that service preselected; hero button opens it with none selected. Tighten `ProviderProfile` types (ratings required, new fields).
- [x] PF3 Customer ratings: page `/cuenta/servicios` listing the caller's services (contract 2) with a 1–5 star input and optional comment for completed, unrated services (contract 3); show the existing rating otherwise; inline Spanish errors; requires sign-in like the quote dialog.

Verification: `npm run lint`, `npx tsc --noEmit`, `npm run build`.

## Progress

- 2026-10-10: Audit done, plan approved with rating creation. Branch `feat/provider-profile-page`.

## Verification evidence

Pending.
