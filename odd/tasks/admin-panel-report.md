# Admin panel implementation report

Branch: `feat/admin-panel` · Baseline: `8441ff1` (`develop`)
Local integrations: `62f64c2` (Next.js 16.4.6) and `c6f52aa` (tax documents and admin migration renumbering). T1–T8 are complete under the documented test exceptions. The strict production build passes.

## Task status

| Task | Status | Commit |
|---|---|---|
| T1 — Access and audit foundation | Done; historical build exception closed by local integration | `7be1749` |
| T2 — Layout and shared components | Done | `b180465` |
| T3 — Dashboard, finance, and settings | Done | `0037b17` |
| T4 — People and vehicles | Done; invitation attempt attribution open | `ddf02b2` |
| T5 — Moderation and claims | Done; audited claim transcript added in T6 | `20b5c86` |
| T6 — Operations | Done; confirmed admin cancellation refunds 100% | `2de65fe` |
| T7 — Payments, refunds, and payouts | Done | `dd5f322` |
| T8 — Catalogs and final verification | Done | `71a32a7` |

T1 adds a deny-by-default allowlist using verified Supabase subjects, a guarded admin router, server-rendered access checks, a private audit migration, transaction-bound audit writes, filtered audit queries and CSV, and an audit page. T2 adds the responsive sidebar, pending badges, server-gated section routes, audit table integration, URL filters, CSV download, keyboard-accessible row detail, reusable confirmation dialogs, and shared formatters.

## T1 verification

Commands ran from the designated worktree, or from its app directory as indicated.

| Command | Observed result |
|---|---|
| `git status --short --branch`, `git branch --show-current`, `git merge-base --is-ancestor develop HEAD` | Correct branch and base; pre-existing untracked requirements were not included in the implementation commit. |
| `gentle-ai codegraph init --cwd "$PWD"`; `codegraph sync -q "$PWD"` | CodeGraph unavailable with the active Node version. Used scoped source reads; Graphify was available after its index was generated. |
| Backend: `uv sync` | Installed the locked dependencies locally; no credentials or environment file added. |
| Frontend: `npm ci` | Installed the locked dependencies. Reported 15 moderate and 5 high vulnerabilities and one blocked optional install script. No package updates made. |
| Backend: `uv run pytest -q tests/admin/test_access_audit.py --tb=short` | RED: 7 expected failures before the admin API and audit module existed. |
| Backend: `uv run pytest -q tests/admin/test_access_audit.py tests/test_public_db.py --tb=short` | Initial implementation exposed two integration issues (nested router introspection and query parsing); corrected. Latest: 32 passed, 1 PostgreSQL integration skipped. Independent verifier separately observed 32 passed, 1 skipped and verified CSV and rejected-write behavior. |
| Backend: `uv run pytest -q --tb=short` | 1,256 passed, 201 skipped, 1 xfailed, 1 failed. The sole failure was the explicitly allowed `test_payment_composition_root_constructs_configured_adapter`. |
| Backend: `uv lock --check` | Passed. |
| Backend: `DATABASE_URL=postgresql://local.invalid/amira uv run alembic upgrade head --sql` | Passed offline: SQL shows additive audit DDL, index, RLS enablement, and revocation from PUBLIC, anon, and authenticated. No database connection made. |
| Frontend: `node --test tests/unit/*.mjs` | Exit 0: 231 passed and one existing TODO for `authenticatedApiFetch` header handling. |
| Frontend: `npm run lint` | Initial attempt raced with Playwright deleting its result directory; serial retry passed. |
| Frontend: `npx eslint src/app/admin src/lib/admin tests/admin.spec.ts tests/support/fake-auth-server.mjs playwright.config.ts` | Passed on the final T1 change. |
| Frontend: `npx playwright test tests/admin.spec.ts` | RED: signed-out routes did not redirect before implementation; later audit test reproduced missing filters. Latest GREEN: 4 passed, including server-side non-admin denial and filtered audit entity links. Both audit fixes also passed independent readback. |
| Frontend: `npx playwright test --reporter=dot` | Interrupted after an observed failure: 279 passed, 1 failed, 1 interrupted, 187 did not run. The failed case was `page-cuenta-servicios.spec.ts:149`, which observed one customer-list request where it expected none. |
| Frontend: `npx playwright test tests/page-cuenta-servicios.spec.ts -g 'a failed role lookup shows a retryable error and never the customer list'` | Isolated rerun passed on both baseline `8441ff1` and T1 `7be1749`. The failure was not reproduced; its cause remains unconfirmed. |
| Frontend: `npm run build` | First attempt exposed an admin prerender failure without .env; fixed by deferring authorization to request time. An intermediate build passed with a security warning. Latest build compiled, type-checked, and generated pages, then returned exit 1 (`SecurityFatalError`) for the pinned Next.js version (16.4.2). No security escalation, bypass, or update was run. |
| `git diff --check`; `git diff --cached --check` | Passed locally and in the independent readback where applicable. |
| `graphify update .` | Passed after implementation and correction. SQL extraction was skipped because the optional parser is unavailable. Generated graph files are ignored. |

## T2 verification

| Command | Observed result |
|---|---|
| Frontend: `node --test tests/unit/admin.node-test.mjs` | RED: missing formatter module. GREEN: 2 passed; verifies CLP, Santiago dates, RUT and URL filter round-trip. |
| Frontend: `npx playwright test tests/admin.spec.ts -g 'sidebar\|mobile'` | RED: no sidebar navigation and no mobile menu. |
| Frontend: `npx playwright test tests/admin.spec.ts` | Default ports already in use by another checkout; did not stop those processes. |
| Frontend: `AMIRA_TEST_APP_PORT=3180 AMIRA_TEST_AUTH_PORT=54330 npx playwright test tests/admin.spec.ts -g mobile` | Reproduced and isolated an absolutely positioned table descendant widening the page. Giving the table's scroll container a positioning context fixed it. |
| Frontend: `AMIRA_TEST_APP_PORT=3180 AMIRA_TEST_AUTH_PORT=54330 npx playwright test tests/admin.spec.ts` | GREEN: 6 passed, including browser back navigation, pending badges, and internal-only table scrolling on mobile. |
| Backend: `uv run pytest tests/admin/test_access_audit.py -q -k badges --tb=short` | RED: badges route did not exist. |
| Backend: `uv run pytest -q tests/admin/test_access_audit.py tests/test_payout_service.py --tb=short` | The guessed payout file does not exist; no tests ran. |
| Backend: `uv run pytest -q tests/admin/test_access_audit.py tests/test_public_db.py tests/*payout* --tb=short` | GREEN: 56 passed, 1 PostgreSQL test skipped. |
| Backend: `uv lock --check`; `uv run pytest -q --tb=short` | Lock passed; 1,257 passed, 201 skipped, 1 xfailed and only the already permitted payment-adapter failure. |
| Frontend: `npm run lint`; `node --test tests/unit/*.mjs` | Lint passed. Node: 233 passed, 1 existing TODO, exit 0. |
| Frontend: `npm run build` | Intermediate run compiled and type-checked, then stopped only with the known `SecurityFatalError` recorded under L7. Final run compiled, passed type-check, and completed with the advisory (exit 0). Next.js stayed on 16.4.2. |
| `git diff --check`; `git diff --cached --check`; `graphify update .` | Passed. Optional Graphify SQL parser still absent. |


## T3–T5 verification

| Scope | Check | Observed result |
|---|---|---|
| Local integration | `git merge --no-edit origin/develop`; `git stash pop`; frontend `npm ci --offline --no-audit --no-fund` | Local reference `1efc57e` verified; merge and stash restore completed without conflicts. Installed the locked Next.js 16.4.6 package without fetching. |
| T3 | `uv run pytest -q tests/admin/test_finance.py --tb=short`; focused admin tests; full backend | RED: missing finance code; GREEN: 11 focused, 1,260 full passed and the known fixture failure. |
| T3 | Node unit suite; isolated admin Playwright; lint/build | 234 Node passes, 1 TODO; 7 admin browser passes after SVG hydration fix. Compile/typecheck passed under the historical 16.4.2 exception. |
| T4 | `uv run --offline pytest -q tests/admin/test_people.py --tb=short`; focused auth/public/request regressions | 5 people tests passed after provider detail correction. Independent verifier ran 133 tests and additional HTTP probes; scoped readback confirmed provider lists and the open-service warning. |
| T4 | `uv run --offline pytest -q --tb=short` | After accommodating the new fixture dependencies, 1,264 passed, 201 skipped, 1 xfail, and only the permitted payment-adapter fixture failure, before the final scoped provider detail addition. |
| T4 | Frontend `npx --offline playwright test tests/admin.spec.ts` with ports 3180/54330 | RED: customer directory had no search control; GREEN: 8 passed. |
| T4 | `uv lock --offline --check`; offline Alembic SQL; `npm run lint`; Node unit suite; Next.js build; diff and Graphify | All completed successfully. Node: 234 passed, 1 existing TODO. Build exited 0 on 16.4.6; only the workspace-root warning remained. |
| T5 | `uv run --offline pytest -q tests/admin/test_review.py --tb=short`; review/payout/cancellation/public focused suite | RED: two missing review modules. GREEN: 5 direct and 132 focused passed. Independent verifier passed 5 tests plus memory-only refund, masking, rating, and audit probes; verified the PDF layout correction. |
| T5 | `uv run --offline pytest -q --tb=short` | 1,270 passed, 201 skipped, 1 xfail, and only the permitted payment-adapter fixture failure. |
| T5 | `uv lock --offline --check`; `DATABASE_URL=postgresql://local.invalid/amira uv run --offline alembic upgrade head --sql` | Passed; generated additive DDL through `20261124_0003`, without opening a PostgreSQL connection. |
| T5 | Frontend isolated `npx --offline playwright test tests/admin.spec.ts`; repeat with `-g 'document rejection'` | 9 passed; rejection-with-reason and next-document navigation passed again after the two-column PDF fix. |
| T5 | `npm run lint`; `node --test tests/unit/*.mjs`; `NEXT_TELEMETRY_DISABLED=1 npm run build`; `git diff --check`; `graphify update .` | Lint raced with Playwright's test-results cleanup once, then passed serially. Node 234 passed/1 TODO. Build compiled, type-checked and exited 0 on 16.4.6. Diff and Graphify passed. |

## Local tax integration and T6–T8 verification

Backend commands ran in `backend/`, frontend commands in `frontend/`. Browser runs used local fake Supabase, no real credentials or money.

| Scope | Command or probe | Observed result |
|---|---|---|
| Tax integration | `git merge --no-edit --no-commit origin/develop` at `78a6ba2` | One test conflict resolved, retaining tax and admin RLS coverage. Committed the merge as `c6f52aa` after renumbering the three previously unapplied admin migrations. |
| Tax integration | `uv run --offline alembic heads`; `DATABASE_URL=postgresql://local.invalid/amira uv run alembic upgrade head --sql` | RED: duplicate heads and missing renamed migration fixture. GREEN: one head `20261125_0003`, offline SQL generated successfully. Migration/RLS tests: 26 passed, 1 skipped. Full backend: 1,298 passed and only the permitted fixture failure, 201 skipped, 1 xfail. |
| T6 | Focused operations, cancellation, public route, and admin pytest tests; `uv run --offline pytest -q` | RED: missing operations modules and unrelated chat from the same request allowed. GREEN: 73 focused; 1,302 full passed plus the permitted fixture failure, 201 skipped, 1 xfail. Independent run: 4 tests plus refund/audit rollback, pagination privacy, and trip preservation probes passed. |
| T6 | `npx --offline playwright test tests/admin.spec.ts` with ports 3180/54330; `npm run lint`; `NEXT_TELEMETRY_DISABLED=1 npm run build`; diff and Graphify | 10 admin browser tests passed; lint, strict 16.4.6 build, diff and Graphify passed. |
| T7 | Focused payment/payout/cancellation/finance/admin pytest tests; `uv run --offline pytest -q` | RED: missing transaction module and rejected evidence not stored. GREEN: 132 focused before scoped correction, 85 after; 1,306 full passed plus the permitted fixture failure, 201 skipped, 1 xfail. Independent money, state, and evidence verification passed. |
| T7 | `uv lock --offline --check`; `uv run --offline alembic heads`; `DATABASE_URL=postgresql://local.invalid/amira uv run --offline alembic upgrade head --sql` | Lock passed, one head `20261125_0004`, offline SQL passed. |
| T7 | `npx --offline playwright test tests/admin.spec.ts` with ports 3180/54330; `npm run lint`; `NEXT_TELEMETRY_DISABLED=1 npm run build`; diff and Graphify | 11 admin browser tests passed; lint, strict 16.4.6 build, diff and Graphify passed. |
| T8 | `uv run --offline pytest -q tests/admin/test_catalog.py -k new_quote_selection --tb=short` | RED: public profile still listed a deactivated type and direct POST returned 201. |
| T8 | `uv run --offline pytest -q tests/admin/test_catalog.py tests/test_service_type_visibility.py tests/test_public_provider_routes.py tests/test_shared_trip_routes.py --tb=short` | GREEN: 88 passed. Independent real-HTTP probes confirmed GET omission and POST 404 after deactivation, with active selection and existing references preserved. |
| T8 | `uv run --offline pytest -q` | 1,310 passed, 201 skipped, 1 xfail. Sole failure was the user-exempted `test_payment_composition_root_constructs_configured_adapter` without local .env. `uv run --offline pytest -q --deselect tests/test_whitebox_critical.py::test_payment_composition_root_constructs_configured_adapter` exited 0 with the same counts and one deselected. |
| T8 | `uv lock --offline --check`; `uv run --offline alembic heads`; `DATABASE_URL=postgresql://local.invalid/amira uv run --offline alembic upgrade head --sql` | Lock and offline SQL passed, one head `20261125_0005`. No database connection attempted. |
| T8 | `node --test tests/unit/*.mjs`; `npm run lint`; `NEXT_TELEMETRY_DISABLED=1 npm run build` | Node: 241 passed, 1 existing TODO. Lint passed. Next.js 16.4.6 build compiled, type-checked, and exited 0 without SecurityFatalError. |
| T8 | `AMIRA_TEST_APP_PORT=3180 AMIRA_TEST_AUTH_PORT=54330 NEXT_TELEMETRY_DISABLED=1 npx --offline playwright test --workers=3 --reporter=dot` | 474 passed, 9 failed. New catalog test used a non-exact locator (matched both `Cliente` and `client`); fixed to exact. Other cases covered finance navigation, account/auth, invitations, services, vehicles and chat. Only the already-known role-lookup failure recurred in the final serial run. |
| T8 | `AMIRA_TEST_APP_PORT=3180 AMIRA_TEST_AUTH_PORT=54330 NEXT_TELEMETRY_DISABLED=1 npx --offline playwright test tests/page-cuenta-servicios.spec.ts -g 'a failed role lookup shows a retryable error and never the customer list' --reporter=dot` | Known role-lookup failure rerun in isolation: 1 passed after each full run. |
| T8 | Same port and telemetry environment, `npx --offline playwright test --reporter=dot` | First serial run had already loaded the old locator and was interrupted: 78 passed, 1 failed, 1 interrupted, 403 not run. Final serial run on corrected files: 482 passed and only the permitted role-lookup failure at line 149; isolated retry passed. |
| T8 | `AMIRA_TEST_APP_PORT=3181 AMIRA_TEST_AUTH_PORT=54331 NEXT_TELEMETRY_DISABLED=1 npx --offline playwright test tests/admin.spec.ts --output=node_modules/.cache/admin-t8-focused-results --reporter=dot` | 12 passed, including type creation and read-only roles. |
| T8 | `git diff --check`; `git diff --cached --check`; `graphify update .` | Passed. Optional Graphify SQL parser remained unavailable. |

## Open questions and risks

- S8: historical session-scoped attempts do not carry an invitation ID and display “Sin dato”; prospective per-invitation attribution was not implemented. Another user's Supabase assurance is not available from a local record and is not inferred.
- T7: unknown historic provider evidence stays null. New verified metadata is allowlisted; rejected attempts are not duplicate approvals. S15 permits manual refunds only through confirmed-service cancellation; disputed refunds use S11.
- **Risk: items 1, 2 and 4 (privileged writes, authorization, and row-lock ordering).** Local verification used fake services, SQLite, or offline SQL. Production PostgreSQL locking and real storage/payment integrations were not exercised. All admin money actions used simulated adapters.
- No fetch, pull, push, PR, or native Gentle AI review. The only merges were the two requested local integrations. Pre-existing untracked `docs/requisitos/` was left untouched.
