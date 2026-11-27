# Admin panel implementation report

Branch: `feat/admin-panel` · Baseline: `8441ff1` (`develop`)
Status: **Paused before T6 for the admin cancellation policy.** T1–T5 are checkpointed; the remaining S8 and S11 limitations are listed below. The local integration of `origin/develop` at `1efc57e` was committed as `62f64c2`. The strict Next.js 16.4.6 build passes.

## Task status

| Task | Status | Commit |
|---|---|---|
| T1 — Access and audit foundation | Done under the user-authorized build exception | `7be1749` |
| T2 — Layout and shared components | Done | `b180465` |
| T3 — Dashboard, finance, and settings | Done | `0037b17` |
| T4 — People and vehicles | Done; invitation attempt attribution open | `ddf02b2` |
| T5 — Moderation and claims | Done; claim transcript depends on S16 | `20b5c86` |
| T6 — Operations | Not started; admin cancellation retention is undefined | — |
| T7 — Payments, refunds, and payouts | Not started | — |
| T8 — Catalogs and final verification | Not started | — |

T1 adds a deny-by-default allowlist using verified Supabase subjects, a guarded admin router, server-rendered access checks, a private audit migration, transaction-bound audit writes, filtered audit queries and CSV, and an audit page. T2 adds the responsive sidebar, pending badges, server-gated section routes, audit table integration, URL filters, CSV download, keyboard-accessible row detail, reusable confirmation dialogs, and shared formatters. Unimplemented T6–T8 sections retain placeholders until their own task implements them.

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

The full browser suite is not yet green; its final run belongs to T8. Keep the user-approved isolated retry for the known role-lookup failure if it recurs.

## Open questions and risks

- S15 uses the existing cancellation path, which retains 10% for a customer cancellation and 0% for a provider cancellation. S15 does not establish a rule for an administrator-initiated cancellation. No T6 code was started, no refund amount was assumed, and T7–T8 remain pending.
- S8 displays “Sin dato” for attempts: the historical session-scoped attempts do not carry an invitation ID. T5 shows the claim’s chat link; displaying the audited read-only transcript in the claim detail depends on S16.
- **Risk: items 1, 2 and 4 (refund and moderation writes, privileged authorization, row-lock ordering).** Local verification used SQLite or offline SQL; production PostgreSQL concurrency and real storage/money infrastructure were not exercised. All admin refunds exercised here were simulated.
- No fetch, pull, push, PR, further merge, native review, or edits to the main checkout were performed after authorization of the single local merge.
