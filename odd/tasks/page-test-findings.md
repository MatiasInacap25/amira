# Page test findings

Objective: fix the defects found by the per-page Playwright sweep. Branch: `fix/page-test-findings` (base `4782747`).
Delivery: ask-on-risk. Runner: Playwright (`npx playwright test <spec>` from `frontend/`), node unit tests (`node --test tests/unit/*.mjs`).

## Specs

- S1: `tests/marketplace.spec.ts` has 8 failing tests on main. Each one is classified as an app regression (fix the app) or stale copy (update the test), and the spec passes.
- S2: The provider profile does not say "Aún no hay valoraciones" when `ratingCount > 0` and `averageRating` is null (`provider-profile-view.tsx` `RatingLine`).
- S3: A provider profile id with a space and a slash reaches the API encoded once (`perfil%20con%2F1`), not twice (`perfil%2520con%252F1`).
- S4: Signed out, `/mensajes/[chatId]` shows the sign-in prompt that `/mensajes` shows ("Inicia sesión con tu correo confirmado para ver tus mensajes."), not an empty thread.
- S5: Signed out, `/pagos/simulado` and `/pagos/resultado` show a sign-in prompt, not a generic error or a permanent loading message. Assumption: wording mirrors `/mensajes`.
- S6: `/cuenta/invitaciones`: a failed load does not also show "No hay invitaciones todavía."; a long unbroken email does not force horizontal scroll at 390px; statuses show in Spanish. Assumption: Pendiente, Revocada, Expirada, Aceptada.
- S7: On a 409 when rating a service, "Este servicio ya fue valorado." stays visible after the list refetch.
- S8: Investigate the duplicate first-load request on `/servicios` and `/rutas-compartidas`. Report only; a fix becomes a new task.

## Tasks

| ID | Specs | Route | Status | Commit |
|---|---|---|---|---|
| T1 | S1, S2 | delegated (herdr worker, Haiku) | done | `e8a5fd4` |
| T2 | S3 | delegated (herdr worker, Haiku) | done | `da742a1` |
| T3 | S4 | delegated (herdr worker, Haiku) | done | `3f3e548` |
| T4 | S5 | delegated (herdr worker, Haiku) | done | `c58552e` |
| T5 | S6 | delegated (herdr worker, Haiku) | done | `f1afcd5` |
| T6 | S7 | delegated (herdr worker, Haiku) | done | `c22c16a` |
| T7 | S8 | delegated (herdr worker, Haiku) | done (no fix) | |

Route evidence: `HERDR_ENV=1`, the project CLAUDE.md makes the parent an orchestrator that does not edit code. Workers run one at a time because Playwright uses port 3179.

## Log

- L1 (2026-10-18): "primero instala https://github.com/addyosmani/agent-skills, despues crea un plan para solucionar cada problema y despliega un worker por cada problema"
- L2 (2026-10-18): user approved the plan and its assumptions ("si"). Page specs committed as `4782747`.
- L3 (2026-10-18): T1 done (`e8a5fd4`). 2 marketplace failures were a regression from `55e21bc` (merged empty and missing ratings); 6 were stale copy/selectors from `b575860` and `9157ffe`. RED observed for S2. Parent re-ran marketplace + page-prestador: 30 passed, 1 skipped (T2 fixme); lint 0. Follow-up: empty role=status region in marketplace-skeleton.tsx stays after loading.
- L4 (2026-10-18): T2 done (`da742a1`). Cause: Next passes params.profileId still percent-encoded; marketplace-api.ts encodes again. RED/GREEN observed. Parent re-ran page-prestador + marketplace: 31 passed; lint 0. Possible same defect (unverified, not in scope): cuenta/servicios/[serviceId], mensajes/[chatId], solicitudes/[requestId].
- L5 (2026-10-18): T3 done (`3f3e548`). ChatThreadView renders the existing ChatErrorState sign-in prompt when there is no session. RED/GREEN observed. Parent re-ran page-chat + page-mensajes: 30 passed; lint 0.
- L6 (2026-10-18): T4 done (`c58552e`). Shared SignInPrompt extracted from ChatErrorState; payment message "Inicia sesión con tu correo confirmado para ver tu pago.". Checkout shows it after a decision fails for missing session; result page shows it on load. RED/GREEN observed. Parent re-ran pago-simulado + pago-resultado + chat: 42 passed; lint 0.
- L7 (2026-10-18): T5 done (`f1afcd5`). All three S6 items were RED first (both fixmes confirmed real). Parent re-ran page-cuenta-invitaciones + driver-invitation: 26 passed; lint 0.
- L8 (2026-10-18): T6 done (`c22c16a`). The already-rated notice moved from RatingForm to the service row state. RED/GREEN observed. Parent re-ran page-cuenta-servicios + account-query-cache: 17 passed; lint 0.
- L9 (2026-10-18): T7 done, no app change. Cause (a): React Strict Mode double mount in dev (default on in the App Router; next.config.ts does not set it). Dev fires every first-load request twice with identical timestamps; a production build (next start) fires each once. One query key per page, no state change on mount. Tree unchanged after the probe.
- L10 (2026-10-18): Seam check on the branch: full Playwright 277 passed, 4 failed; unit 67 passed; lint 0. The 4 failures are in tests/auth.spec.ts (lines 403, 495, 524, 549) and fail identically on main (checked in a temporary worktree), so they are pre-existing and out of scope. First one waits for "Solicitar cotización", renamed "Cotizar" in b575860. Open follow-ups: those 4 tests; possible double-encoded ids in other dynamic routes; empty role=status region in marketplace-skeleton.tsx.
