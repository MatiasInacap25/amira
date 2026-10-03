# Provider Search Cards

## Objective
Show one card per distinct active provider profile on `/servicios`, with public profile navigation and quote requests scoped to actual offerings that match the search.

## Problem and rationale
The current `/api/services` query joins profiles to service offerings, then counts and paginates joined rows. A provider with multiple matching offers can appear multiple times and distort result counts/page boundaries. The listing DTO does not carry service IDs needed to target an offered service in the existing quote dialog. The approved API makes provider profiles the result entity and includes only the matching offered service IDs/names.

## Scope
- Backend `/api/services`: distinct active provider profiles, provider-level count/order/page, allowlisted public profile fields, matching offered service IDs/names.
- Frontend `/servicios`: one card per profile, `Ver perfil` and `Cotizar` actions, existing quote modal limited to matching offerings, preserving independent free-text search.
- Keep category as native select/list of allowed values; it currently is a native `<select>`, so preserve it and verify options.
- Focused regression tests and full applicable backend/frontend verification; refresh graphify.

## Authorized scope
- Branch: `feature/auth-and-public-provider-profiles`.
- Route: `delegated direct` (single delegated writer); mapping trigger fired because understanding spans 4+ files.
- Source scope is limited to the service-search API/schema/tests and the `/servicios` page, quote-dialog/service DTO integration, and marketplace E2E tests.
- No production Supabase/hosted calls, profile activation policy changes, private DTO fields, remote operations, push, PR, deploy, or review lifecycle actions.
- Preserve all pre-existing dirty state: `backend/src/amira_api/auth.py`, `main.py`, `models.py`, `settings.py`, `backend/tests/test_account_provisioning.py`, `backend/tests/test_auth.py`, `backend/alembic/versions/20260928_0004_email_fallback_proofs.py`, `backend/src/amira_api/fallback_routes.py`, `backend/tests/test_email_fallback.py`, `backend/tests/test_email_fallback_migration.py`, and all other existing dirty/untracked files outside explicitly added feature files.
- Stage only exact feature files; never use `git add .`. Conventional commits only; no AI attribution.

## Accepted design
`GET /api/services` returns one entry per distinct active provider profile matching filters; `total`, `limit`, and `offset` describe profiles. Each entry carries allowlisted provider identity/details plus the matching offered services as `{serviceTypeId, name}` values. `/servicios` renders one provider card with exactly two primary actions: `Ver perfil` and `Cotizar`. `Cotizar` opens the existing modal; one matching service is preselected, while multiple choices are restricted to the card’s returned matches. Real first and last names remain displayed, and private PII stays private. Category remains an allowed-option native selector; general text search stays independent.

## TDD and checks
- `strict_tdd: true`; source: explicit user preference (2026-10-03). RED → GREEN → REFACTOR is required.
- Backend test runner: `uv run pytest` from `backend`.
- Frontend E2E runner: `npm run test:e2e` from `frontend`.
- Focused tests: backend service endpoint tests; frontend marketplace E2E service-search cases.
- Full checks: `uv run pytest` (backend); frontend `npm run test:e2e`, `npm run lint`, `npx tsc --noEmit`, and `npm run build` as applicable.
- Final checks: `graphify update .`, `git diff --check`, inspect exact staged paths and commits.
- Existing environment restriction: do not use production Supabase or hosted services.

## Forecast and delivery
Forecast: approximately 350 authored changed lines (additions plus deletions; generated files excluded), based on one backend query/DTO/test slice and one page/modal/E2E slice. No size-only split. Use two coherent work-unit commits on the existing feature branch, one per implementation task; push/PR/merge/deploy are not authorized.

## Tasks
- [x] PSC-1 — Return unique active providers with matching offerings from `/api/services`; add RED regression coverage for distinct count/grouping, profile-based pagination, matching service IDs/names, and privacy/active-only contract. Commit: `c2a1569`. Route: delegated direct. Acceptance: matching provider IDs are unique; total/order/offset/limit count profiles; services correspond to matching active offerings only. Checks: `uv run pytest tests/test_public_routes.py -q` passed (6 tests); full `uv run pytest` passed (89 tests).
- [x] PSC-2 — Render provider-level cards and connect profile/quote actions; preserve independent general search and native category options; update E2E to cover single/multiple quote choices restricted to matches. Route: delegated direct. Acceptance: one card per provider, exactly `Ver perfil` and `Cotizar`; existing dialog targets valid service IDs, defaults a single option, and exposes only matching options; names/privacy remain correct. Checks: focused E2E passed (5 tests); full `npm run test:e2e` passed (35 tests); `npm run lint`, `npx tsc --noEmit`, and `npm run build` passed. Commit: `70fe2c8`.

## Progress and evidence
- 2026-10-03: Refreshed `odd/tasks/search-and-shared-routes.md` and Engram observation #139; confirmed its completed T1–T3 work remains unrelated and is preserved.
- 2026-10-03: Current page already has a native category `<select>` and a separate general text input; no free-typed category input is present, so preserve both behaviors and add option regression coverage.
- 2026-10-03: Approved design persisted in `docs/superpowers/specs/2026-10-03-provider-search-cards-design.md` and committed separately as `d93ae5c`.
- 2026-10-03: PSC-1 RED reproduced the missing `services` API contract; GREEN passed `uv run pytest` (89 passed). SQL regression asserts `COUNT(DISTINCT profile ID)`, grouped provider rows, active-only filtering, and limit/offset. Commit `c2a1569` updates public route/schema/test files only.
- 2026-10-03: PSC-2 RED failed at the missing card `Cotizar` action; GREEN passed focused E2E (5 tests) and full E2E (35 tests), plus lint, TypeScript, and production build. Playwright bundled Chromium was unavailable and CDN installation timed out; tests ran using installed Chrome via `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. Commit `70fe2c8` updates only page, API type, quote dialog, CSS, and marketplace E2E tests.
- 2026-10-03: `graphify update .` completed; graph now has 4,171 nodes and 5,922 edges. `git diff --check` passed.
- Current status: PSC-1 and PSC-2 complete. No feature work remains; no remote calls, push, PR, or deploy performed.
