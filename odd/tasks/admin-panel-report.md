# Admin panel implementation report

Branch: `feat/admin-panel` · Baseline: `8441ff1` (`develop`)
Status: **Blocked at T3.** T1 and T2 are complete. The build exception in L7 applies; Next.js was not changed.

## Task status

| Task | Status | Commit |
|---|---|---|
| T1 — Access and audit foundation | Done under the user-authorized build exception | `7be1749` |
| T2 — Layout and shared components | Done | `b180465` |
| T3 — Dashboard, finance, and settings | Blocked before implementation: assigned explorer model unavailable | — |
| T4 — People and vehicles | Not started | — |
| T5 — Moderation and claims | Not started | — |
| T6 — Operations | Not started | — |
| T7 — Payments, refunds, and payouts | Not started | — |
| T8 — Catalogs and final verification | Not started | — |

T1 adds a deny-by-default allowlist using verified Supabase subjects, a guarded admin router, server-rendered access checks, a private audit migration, transaction-bound audit writes, filtered audit queries and CSV, and an audit page. T2 adds the responsive sidebar, pending badges, server-gated section routes, audit table integration, URL filters, CSV download, keyboard-accessible row detail, reusable confirmation dialogs, and shared formatters. Sections beyond audit retain placeholders until their own task implements them.

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

The complete Playwright suite is still pending for T8. There was no repeat of the known role-lookup failure in this turn's focused coverage; the case was not selected. If it fails in a future full run, rerun it in isolation and record the result without treating that case alone as a gate.

## Open questions and risks

- No open product decisions for T1 or T2. T3 requires an independent read-only domain map before implementation. The prescribed `odd-explorer` model `gpt-6.1-luna` could not be launched; approve an available equivalent to resume the mapping. The Next.js upgrade stays on a separate branch.
- **Risk: none for T2.** The badges route inherits the existing tested admin guard and performs only reads. The pre-existing Next.js advisory remains unresolved, and PostgreSQL migration/RLS execution and the complete browser suite still need verification before deployment.
- S0 money handlers and all moderation, operation, finance, and catalog workflows remain unimplemented. The checkpoint is not a usable complete admin panel.

No push, PR, merge, native review, or edits to the main checkout were performed.
