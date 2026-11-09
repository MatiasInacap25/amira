# Black-box testing (caja negra)

Objective: verify Amira's behavior against its specifications only, through the public HTTP contract of the real backend running on a real PostgreSQL, and report results in detail. Branch: `test/caja-negra`. Delivery: `ask-on-risk`. Runner: `uv run pytest` (backend, opt-in black-box suite), `npx playwright test` (frontend). Executor: Codex (`gpt-6.1-sol`) via herdr; Claude orchestrates and verifies.

## Specs

- **S1 — Test oracle = specifications, not code.** Derive every expected result from these documents only: `PROJECT_OVERVIEW.md`, `backend/README.md` (public browse, payments, contracted services, delivery photos, live location, claims/consent/payout, chat, attachments, request images, vehicles, unread counts, shared trips), the `## Specs` sections of `odd/tasks/*.md`, and the OpenAPI schema served by the app (`/openapi.json`). Do **not** read `backend/src/**` or `frontend/src/**` to decide what a test expects. Each test docstring cites its source (`README.md#<section>` or `odd/tasks/<file>.md S#`). When a spec is ambiguous, record it as an "ambiguity" in the report instead of guessing.
- **S2 — Black-box harness (backend).** New directory `backend/tests/blackbox/` with its own `conftest.py`:
  - Opt-in: the whole directory skips unless `AMIRA_BLACKBOX_DATABASE_URL` is set, and reuses the localhost-only allowlist of `tests/postgres_support.py` (`destructive_test_skip_reason`). The default `uv run pytest` must stay green and unchanged.
  - Database: a disposable PostgreSQL that already exists at `postgresql://postgres:postgres@127.0.0.1:55432/postgres` (container `amira_blackbox_db`, SSL on with a self-signed cert, `alembic upgrade head` already applied). Tests may truncate and seed data in it; never touch any other database (port 54322 is the developer's local Supabase: forbidden).
  - App: start the real API as a subprocess (`uvicorn amira_api.main:app` on a free 127.0.0.1 port) with `APP_ENV=test`, `DATABASE_URL` = the disposable DB, and the Supabase settings pointing to a local JWKS HTTP server started by the harness. Tests talk to it only through `httpx` over HTTP.
  - Auth: the harness generates a signing key, serves its JWKS, and mints Supabase-shaped tokens (`iss`, `aud=authenticated`, `exp`, `iat`, `sub`, `aal`, `amr`, `session_id`, `email`, `role`, `is_anonymous`) for test actors: anonymous, customer, provider owner, driver, other customer (for access-control tests).
  - Seeding: arrange data with SQL against the documented data model (Spanish table names from the migrations), or through API calls when an endpoint exists for it.
- **S3 — Techniques (every endpoint group must state which ones it uses in the report).**
  - Equivalence partitioning (valid/invalid classes per input).
  - Boundary value analysis: `limit` 0/1/MAX/MAX+1, `offset` 0/MAX/MAX+1, `q` 120/121 chars, `regionCode` 2 digits vs 1/3/letters, `communeCode` 5 digits vs 4/6, UUID valid/malformed, file sizes and MIME types at documented limits.
  - Decision tables for authentication/authorization: no token, malformed, expired, wrong issuer, wrong audience, `aal1` vs `aal2`, anonymous, wrong role, owner vs non-owner (IDOR).
  - State-transition testing for the business lifecycle: request → quotation (create/reject) → payment (simulated complete) → service assignment → start (with driver location) → live location → complete (delivery photo) → consent/claim → payout eligibility; invalid transitions must be rejected (e.g. complete before start, pay a rejected quotation, pay twice).
  - Error guessing: duplicate submissions, unknown IDs (404 vs 403 policy as documented), oversized bodies, extra/unknown JSON fields where the spec says strict.
- **S4 — Coverage of the contract.** One test module per area: `test_bb_public_browse.py`, `test_bb_auth_account.py`, `test_bb_requests_quotations.py`, `test_bb_payments.py`, `test_bb_services_lifecycle.py`, `test_bb_claims_payouts.py`, `test_bb_chat.py`, `test_bb_provider_profile_vehicles.py`, `test_bb_invitations_shared_trips.py`. Build a traceability matrix (requirement → test IDs → result). Storage-dependent endpoints (Supabase Storage) are tested only up to the documented validation errors unless a local fake is part of the harness; list what was not reachable.
- **S5 — Frontend black-box.** Run the existing Playwright suite (`cd frontend && npx playwright test`, isolated app on `127.0.0.1:3179` with its fake endpoints) and record pass/fail/flaky per spec file. Do not add new Playwright specs in this campaign; instead list user flows from the specs that have no E2E coverage (gap list).
- **S6 — Defects.** Tests only: never modify `backend/src` or `frontend/src`. A test that shows behavior contradicting the spec stays as `pytest.mark.xfail(strict=True, reason="BUG: <spec ref>: expected X, got Y")`. Record each with reproduction (HTTP request + response), spec reference and severity.
- **S7 — Report.** `docs/testing/informe-caja-negra.md`, detailed, in neutral professional Spanish: objective and scope; why black-box (oracle = specs); environment and harness (disposable DB, real uvicorn, local JWKS) and exact commands; techniques per area; traceability matrix; results per module (passed/failed/xfail/skipped) and for Playwright; defects (D#) with evidence and severity; spec ambiguities found; what was not tested and why; recommendations; conclusion. Use only real measured numbers.

### Rules for all specs
- Allowed edit surfaces: `backend/tests/blackbox/**`, `backend/pyproject.toml` (only if a test-only dependency is strictly needed; then `backend/uv.lock`), `backend/README.md` (document how to run the black-box suite), `docs/testing/informe-caja-negra.md`, `odd/tasks/caja-negra.md` (Tasks table + Log only).
- No network beyond 127.0.0.1. No hosted Supabase, Render or Vercel.
- Deterministic: no wall-clock dates baked in, no sleeps other than bounded readiness polling of the subprocess.
- Artifacts in English (code, test names, comments); only the report is in Spanish.
- One Conventional Commit per task, no Co-Authored-By or AI attribution. Do not push.

## Tasks

| ID | Specs | Route | Status | Commit |
|----|-------|-------|--------|--------|
| T1 | S1, S2 | delegated (Codex) | done: 2 passed; opt-out 2 skipped; baseline failure confirmed | efead07 |
| T2 | S3, S4 (public browse, auth/account) | delegated (Codex) | done: accumulated 61 passed | hash recorded in next task |
| T3 | S3, S4 (requests, quotations, payments) | delegated (Codex) | pending | |
| T4 | S3, S4 (services lifecycle, claims, payouts) | delegated (Codex) | pending | |
| T5 | S3, S4 (chat, provider profile, vehicles, invitations, shared trips) | delegated (Codex) | pending | |
| T6 | S5 | delegated (Codex) | pending | |
| T7 | S6, S7 | delegated (Codex) | pending | |

Route evidence: user explicitly asked for Codex (`gpt-6.1-sol`) as executor; Claude designs and verifies.

## Log

- L1 (2026-11-09, user): "si, sigue con la caja negra" (continuation of: "usa codex para hacer las pruebas, tu disena el plan detallado y depues que codex lo ejecute con sol 6.1, los resultados dejalos en un informe" / "un informe detallado").
- L2: Disposable DB prepared by Claude: container `amira_blackbox_db` (image `public.ecr.aws/supabase/postgres:17.11.0.006`), `127.0.0.1:55432`, user/password `postgres`, SSL enabled with a self-signed cert (the app forces `sslmode=require`), `alembic upgrade head` applied successfully up to `20261108_0001`. The developer's local Supabase DB (port 54322) is out of bounds.

- L3 (2026-11-09): User confirmed no concurrent executor remains and authorized reconciling the duplicate README section. T1 harness: real HTTP smoke 2 passed; opt-out 2 skipped. Default suite: 856 passed, 1 failed, 5 skipped; existing test `test_quote_request_uses_server_account_actor_and_creates_only_request` uses past `requestedAt=2026-11-08T10:00:00-03:00` and returns 422 instead of 201. No production code read or changed; baseline run excluding black-box tests pending. No new dependency.

- L4 (T2): Public catalog boundary partitions, CUT codes, timezone filters, UUID classes, privacy and hidden types; authentication decision table and account identity; email proof validation. Accumulated suite: 61 passed (2.66 s), XML `/tmp/amira-bb-t2.xml`. Baseline without black-box directory: 856 passed, 1 failed, 3 skipped (11.86 s), identical existing past-date failure; adding this opt-in directory does not cause it. T1 commit `efead07`.
