# White-box testing (caja blanca)

Objective: raise statement + branch coverage of backend `amira_api` and frontend `src/lib` through white-box tests, and deliver a detailed report. Branch: `test/caja-blanca`. Delivery: `ask-on-risk`. Runners: `uv run pytest` (backend, pytest-cov), `node --test --experimental-test-coverage` (frontend). Executor: Codex (`gpt-6.1-sol`) via herdr; Claude orchestrates and verifies.

## Specs

- **S1 — Tooling.** Add `pytest-cov` to the backend `dev` dependency group (update `uv.lock`; `uv lock --check` must pass). Add `[tool.coverage.run]` (`source = ["amira_api"]`, `branch = true`) and `[tool.coverage.report]` (`show_missing = true`, `skip_covered = true`) to `backend/pyproject.toml`. Document both coverage commands in `backend/README.md` and `frontend` docs (README or CLAUDE.md commands section).
- **S2 — Time-bomb test.** `tests/test_public_provider_routes.py::test_quote_request_uses_server_account_actor_and_creates_only_request` fails on 2026-11-09 with `assert 422 == 201` because `requestedAt` is hardcoded to `"2026-11-08T10:00:00-03:00"` (now in the past). Make the date relative to the current time (or freeze the clock the app already uses in `clock.py`) so the test is deterministic. Search the whole `backend/tests` and `frontend/tests` for other hardcoded future dates and fix them the same way.
- **S3 — Critical modules (money, auth, infra), target 100 % lines and branches, or a written justification per uncovered line.**
  Baseline (line-or-branch misses):
  - `auth.py` 88 % — 54, 82-83, 85, 115, 120, 141, 144, 154-156 (JWT/JWKS error paths: bad issuer, audience, expired, missing kid, JWKS fetch failure).
  - `payment_service.py` 90 % — 46, 142, 156-159, 175, 217-220.
  - `payout_service.py` 96 % — 91, 171.
  - `release_payouts.py` 73 % — 28, 36, 41-44, 48 (CLI entrypoint, fail-closed `APP_ENV`).
  - `simulated_payment_provider.py` 96 % — 38.
  - `shared_trip_service.py` 90 % — 60, 113, 118, 123.
  - `payment_routes.py` 98 % — 60, branch 106->108.
  - `quotation_routes.py` 98 % — 96.
  - `db.py` 62 % — branches 17->19, 26->34, lines 20, 40-43, 47-53 (TLS enforcement, pool/statement-timeout config) — test with monkeypatched settings, no real DB.
- **S4 — Account, invitations and fallback, target ≥ 95 % branch.**
  - `account_routes.py` 65 % — 24-33, 71, 102, 105, 114, 118, 120, 122, 129, 143-153, 161, 181-189, 190->219, 194, 205-215, 217.
  - `account_schemas.py` 92 % — 43, 79, 85, 87.
  - `invitation_routes.py` 74 % — 45-47, 51-53, 73, 82-83, 90-91, 94-108, 124, 170, 234, 244, 271-273, 290, 294, 296, 303-309, 318-331 and the rest reported by `--cov-report=term-missing`.
  - `fallback_routes.py` 87 % — 40, 87-97, 105, 106->108, 175-177, 195-196, 272-273.
- **S5 — Remaining backend modules, target ≥ 95 % branch each.**
  `vehicle_routes.py` 85 % (53, 74-75, 103, 109, 138-145, 170-171, 216-218), `request_image_routes.py` 87 % (47-48, 62, 91-93, 102-105, 134->143, 156, 165-166), `evidence_storage.py` 88 % (68, 92, 110, 120-122), `realtime.py` 93 % (88, 177, 190, 281-282, 297, 310-313, 347, 350, 355-356, 364-365), `realtime_routes.py` 94 % (31, 35, 39, 83), `public_routes.py` 95 % (215, 301, 486, 488, 498, 512-514, 542), `chat_routes.py` 96 % (357, 384-385, 400, 467, 481-482), `main.py` 84 % (32-39), `customer_routes.py` (208-209), `provider_service_routes.py` (204, 528-529), `location_routes.py` (branch 48->43).
- **S6 — Frontend `src/lib`, target ≥ 95 % lines and branches for pure logic.**
  Baseline: all files 88.91 % lines / 96.15 % branches / 83.78 % funcs. Gaps: `provider-request-access.ts` 57 % (18-27, 30-31, 34-37, 49-56), `provider-profile-api.ts` 80 % (49-53, 58-63, 66-72, 75-80, 83-88), `auth/account-api.ts` 20 % (3-5, 9-20, 23-30, 33-45), `chats.ts` 94 % (186, 190-195, 199-202), `chat-quotations.ts` (8-9, 85), `post-login-path.ts` (16-17), branch gaps in `chat-events.ts`, `chat-notifications.ts`, `geolocation.ts`. `supabase/client.ts` may be excluded with justification (browser SDK wiring). Use `fetch` stubs; never call a real API.
- **S7 — Report.** Write `docs/testing/informe-caja-blanca.md` in neutral professional Spanish (user-requested language), detailed: objective and scope; white-box techniques applied (statement, branch/decision, path, condition coverage; error-path and boundary analysis); tools and exact commands; baseline vs final table per module (stmts, miss, branch, brpart, cover) for backend and frontend; list of new test files and what paths/branches each covers; defects found (including S2 time-bomb and any production bug revealed, with file:line, reproduction and severity); lines intentionally left uncovered with justification; risks and recommendations (CI threshold, `--cov-fail-under`); conclusion.

### Rules for all specs
- Tests only. **Do not change production code** (`backend/src`, `frontend/src`). If a test reveals a real bug, keep the test as `pytest.mark.xfail(strict=True, reason="BUG: ...")` (or `test.todo` in node) and record it in the report; do not fix it.
- Follow existing test style and fixtures (`conftest.py`, `FakeSession`, `*_support.py`). Go through the public interface (HTTP via the existing request helpers, or the module's public functions). Assert every observable effect (status, body, persisted calls).
- No network, no real Supabase, no hosted DB. Postgres-only tests stay skipped without `AMIRA_TEST_DATABASE_URL`.
- Tests must be deterministic (no wall-clock dates, no sleeps).
- Artifacts in English (test names, comments); only the report is in Spanish.

## Tasks

| ID | Specs | Route | Status | Commit |
|----|-------|-------|--------|--------|
| T1 | S1, S2 | delegated (Codex) | done; backend 92.43% combined, 94.00% lines, 84.58% branches | 29585a6 |
| T2 | S3 | delegated (Codex) | done; backend 93.82% combined | e928a3b |
| T3 | S4 | delegated (Codex) | done; backend 97.38% combined | pending commit |
| T4 | S5 | delegated (Codex) | pending | |
| T5 | S6 | delegated (Codex) | pending | |
| T6 | S7 | delegated (Codex) | pending | |

Route evidence: the user explicitly asked for Codex (`gpt-6.1-sol`) to execute; Claude designs, orchestrates and verifies (project CLAUDE.md orchestrator role, HERDR_ENV=1).

## Log

- L1 (2026-11-09, user): "si, instalalas y arranca con caja blanca, usa codex para hacer las pruebas, tu disena el plan detallado y depues que codex lo ejecute con sol 6.1, los resultados dejalos en un informe" — follow-up: "un informe detallado".
- L2: Skills installed globally: `grafana/skills@k6`, `github/awesome-copilot@pytest-coverage`.
- L3: Baseline backend (`uv run --with pytest-cov pytest --cov=amira_api --cov-branch`): 4047 stmts, 243 miss, 804 branches, 98 partial, **92 %**; 856 passed, 1 failed (S2 time-bomb), 3 skipped (Postgres). Baseline frontend `src/lib`: 88.91 % lines, 96.15 % branches, 83.78 % funcs.

- L4 (T1): Reproduced S2 (422 instead of 201), froze request-schema validation at 2026-11-07 for public-provider/shared-trip fixtures only. Other historical dates are comparison fixtures or explicit frozen clocks. Frontend E2E 2099 dates lie outside authorized surfaces and remain documented risks. Focused: 78 passed; full: 857 passed, 3 skipped; uv lock --check passed. Backend 4047 statements, 243 misses, 804 branches, 98 partial, 92.43% combined. Frontend baseline 88.91% lines / 96.15% branches / 83.78% functions. Added pytest-cov 7.1.0 and coverage configuration.

- L5 (T2): Added critical infrastructure/authentication and money failure tests; focused 44 passed, 1 strict xfail; full 901 passed, 3 skipped, 1 strict xfail. TLS override reproduced at db.py:33 (caller connect_args replaces required SSL); no production fix. Remaining critical gaps are payment_service.py:175 (defensive superseded-event loop: public quotation creation already supersedes earlier pending quotations) and release_payouts.py:48 (module invocation guard; main tested directly without running a process that might access external settings). Coverage details retained for T6 report. T1 commit 29585a6.

- L6 (T3): Focused 118 passed; full 1019 passed, 3 skipped, 1 strict xfail. Branch targets met: account_routes 96.97%, account_schemas 100%, invitation_routes 96.34%, fallback_routes 100%. Tests cover every recovered account field, profile and driver insert conflicts, one-time legacy completion, invitation transport failures and company conversion, PostgreSQL advisory-lock acquire/release with a mocked connection, and failed atomic fallback updates. No real external transport or database used. T2 commit e928a3b.
