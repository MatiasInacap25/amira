# Data consistency and usability

## Objective

Replace free-text location, category, and identity inputs with constrained, validated values so stored data is consistent and search reliably finds providers.

## Problem

- Registration never captures provider location; `Perfil.location` ("Ubicacion", `String(200)`) is only set by seed data, so real providers never match the location filter.
- No Chilean region/commune catalog exists anywhere in the repository.
- Public filters use accent-sensitive `ILIKE '%x%'` on free text ("Valparaiso" misses "Valparaíso").
- The category filter compares frontend slugs (`mercadería` in `/servicios`, `mercaderia` on the home page) against `Tipos_Servicio` display names, so most categories return nothing.
- Origin/destination in quote requests and shared routes are free text.
- RUT, phone, status, and currency have no DB-level constraints; RUT has no client-side validation; requested dates accept past values; backend validation messages are English and the UI shows only a generic error.

## Decisions

- Location granularity: Región → Comuna, one base commune per provider (confirmed by the user on 2026-10-10; multi-commune coverage is out of scope for now).
- Catalog keys are official CUT codes (strings): region `"13"`, commune `"13101"`. Source: official SUBDERE/INE CUT list; 16 regions, 346 communes.
- Existing free-text columns stay for street addresses and backward compatibility; new code columns are the source of truth for filtering.
- Workers do not commit; the orchestrator commits each verified work unit.

## API contract (shared by backend and frontend)

Public JSON uses camelCase (existing `_to_camel` alias generator). Account provisioning keeps snake_case like its existing fields.

1. `GET /api/locations` (public, cacheable):
   `{"regions": [{"code": "13", "name": "Metropolitana de Santiago", "communes": [{"code": "13101", "name": "Santiago"}]}]}`
   Regions ordered by CUT code (north → south), communes ordered alphabetically (Spanish collation).
2. `GET /api/service-types` (public): `{"items": [{"id": "<uuid>", "slug": "mudanzas", "name": "Mudanzas"}]}`.
3. `GET /api/services` query: `q`, `serviceType` (slug), `regionCode`, `communeCode`, `limit`, `offset`. Remove `category` and `location`. Each item adds `communeCode`, `communeName`, `regionName`; `location` stays as a display string `"<Comuna>, <Región>"` (or null).
4. `GET /api/shared-routes` query: `originCommuneCode`, `destinationCommuneCode`, `departureFrom`, `departureTo`, `limit`, `offset`. Remove free-text `origin`/`destination` filters. Items add `originCommuneCode`, `destinationCommuneCode` (nullable for legacy rows).
5. `POST /api/service-requests` (`ServiceRequestCreate`) adds required `originCommuneCode`, `destinationCommuneCode`; `origin`/`destination` become the optional street address (max 300). `requestedAt` must not be in the past.
6. `POST /api/account/provision` adds `commune_code: str | None`; required when role is not `client`, rejected as unknown when not in the catalog.
7. Validation errors keep FastAPI's 422 shape (`detail[].loc`, `detail[].msg`, `detail[].type`). Custom validator messages are Spanish. The frontend maps `loc[-1]` to the field and shows the message inline.

## Tasks

### Backend (worker `backend`, run sequentially, from `backend/`)

Route: delegated direct (Herdr worker, Haiku 5.5). Skills: `sqlalchemy-alembic-expert-best-practices-code-review`, `supabase`, `fastapi-templates`.

- [x] B1 Location catalog: Alembic migration creating `Regiones` (`Codigo` PK varchar(2), `Nombre`, `Orden`) and `Comunas` (`Codigo` PK varchar(5), `Codigo_Region` FK, `Nombre`), seeded from the official CUT list with the source URL in the migration docstring; enable RLS and revoke `anon`/`authenticated` like the public-browse migration. SQLAlchemy models `Region`, `Commune`. New `location_routes.py` + `location_schemas.py` exposing contract 1, wired in `main.py`. Tests assert 16 regions and 346 communes and the response shape.
- [x] B2 Provider location: add `Codigo_Comuna` FK (nullable) to `Perfil` and `Conductor`; backfill the demo seed (`'Santiago'` → `13101`, `'Valparaíso'` → `05101`). Extend `AccountProvisionRequest` and `provision_account` per contract 6. `/api/services` filters per contract 3 (`regionCode` via join). Tests for required/unknown commune and for filtering.
- [x] B3 Service categories: add unique `Slug` to `Tipos_Servicio` (backfill from names without the `[DEMO] ` prefix, lowercase, no accents, hyphens). `GET /api/service-types` (contract 2) and `serviceType` filter by slug. Tests.
- [x] B4 Routes and quote requests: add `Codigo_Comuna_Origen`/`Codigo_Comuna_Destino` FKs to the trip (`Viaje`) and service-request (`Formulario_servicio`) tables; contracts 4 and 5; reject past `requestedAt`. Tests.
- [x] B5 DB constraints: CHECK RUT format `^\d{7,8}-[0-9K]$` on `Usuario.Rut` and `Perfil.Rut_Empresa` plus partial unique indexes; CHECK phone `^\+[1-9]\d{7,14}$`; CHECK `Moneda = 'CLP'`; CHECK non-negative estimated volume; CHECK allowed values for each `Estado` column (derive the allowed sets from code that writes them, normalize existing seed values such as `'[DEMO] publicado'` first). Migration must normalize or fix violating seed/fixture rows before adding constraints. Tests where feasible offline.
- [x] B6 Spanish validation messages: translate custom validator messages (RUT, phone, dates, commune) to Spanish; keep 422 shape (contract 7). Update affected tests.

Backend verification (each task): `uv run pytest`, `uv lock --check`, and the offline migration/SQL checks described in `backend/README.md`.

### Frontend (worker `frontend`, run sequentially, from `frontend/`)

Route: delegated direct (Herdr worker, Haiku 5.5). Read `frontend/CLAUDE.md` first. Skills: `vercel-react-best-practices`, `supabase`, `playwright-cli`. UI copy in Spanish; identifiers in English.

- [x] F1 Catalog client and component: `getLocations()` and `getServiceTypes()` in `src/lib/marketplace-api.ts` (contracts 1–2); reusable accessible `RegionCommuneSelect` component (two linked selects: Región then Comuna; proper labels, `required`, disabled commune until region chosen, keyboard friendly).
- [x] F2 Registration: in `auth-panel.tsx` account step, require Región → Comuna when role is not `client`; send `commune_code` via `account-api.ts` (contract 6).
- [x] F3 Service search: `/servicios` uses `RegionCommuneSelect` (optional) and categories from `getServiceTypes()` by slug (contract 3); remove hardcoded category lists in `servicios/page.tsx` and `page.tsx`; home search navigates to `/servicios?serviceType=&regionCode=&communeCode=`.
- [x] F4 Routes and quotes: `/rutas-compartidas` filters by origin/destination commune (contract 4); `quote-request-dialog.tsx` adds origin/destination commune selects plus optional street address, and `min` = now on the requested date (contract 5).
- [x] F5 Identity inputs: shared `src/lib/validation/rut.ts` (clean, format `12.345.678-K` for display, validate check digit, normalize to `12345678-K` for the API) used by every RUT input (`auth-panel.tsx`, `cuenta/invitaciones/page.tsx`); phone input defaults to `+56`, `inputMode="tel"`, validated in step 1; map 422 `detail[].loc` to inline per-field errors (contract 7).
- [x] F6 E2E: update the Playwright fake API endpoint/fixtures for the new endpoints and params; add specs for registration with commune, service search by commune/category, and RUT validation.

Frontend verification (each task): `npm run lint`, `npm run build`; `npm run test:e2e` at F6 and before handoff.

## Backlog (not in this feature)

- Structured cargo dimensions (length/width/height) instead of free-text measurements.
- Vehicle body-type catalog, `code` columns for `Tipo_Conductor`, Chilean plate CHECK.
- Shared-route DST boundary fix in `marketplace-api.ts` `dateBoundary`.
- Provider profile edit endpoint and UI.

## Progress

- 2026-10-10: Audit completed (read-only explorer). Plan created. Branch `feat/data-consistency-usability`. Workers launched in Herdr panes.

- 2026-10-10: B1–B6 done (7a3395b), region order north→south (65a3f5b), B7 service types without [DEMO] + towing (7635923). F1–F6 done plus slug alignment (frontend commit below).
- Next: apply migrations to Supabase (`alembic upgrade head`) once `backend/.env` has `DATABASE_URL`; run e2e in an environment where headless Chromium fires requestAnimationFrame.

## Verification evidence

- Backend: `uv run pytest -q` → 171 passed; `uv lock --check` → ok; offline `alembic upgrade --sql` → exit 0. Migrations NOT yet run against a live database.
- Frontend: `npm run lint` → ok; `npx tsc --noEmit` → exit 0; `npm run build` → exit 0.
- E2E: 20 passed / 37 failed locally. Cause is environmental: headless Chromium here never fires requestAnimationFrame, so every click times out even on a blank page (verified with a probe); failures reproduce on the previous HEAD. E2E status for this feature is unverified.
- RDD native review (`gentle-ai review`) not run.
