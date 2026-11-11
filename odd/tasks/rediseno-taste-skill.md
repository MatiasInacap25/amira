# Redesign with taste-skill (landing, /servicios, /rutas-compartidas, /login, /registro)

Objective: apply taste-skill (`.claude/skills/design-taste-frontend`, tasteskill 2.5.1) to the landing and to the public search and auth pages, with the landing's system (Amira's colours, Geist, one button pair, one radius family). Branch: `feat/landing-redesign`. Delivery: `ask-on-risk`. Runners: Playwright (`npx playwright test`), `npm run lint`, `npx tsc --noEmit`, plus the skill's checkers (`assets/layout/check.mjs`, `scripts/consistency.mjs`).

## Specs

- **S1 — Landing (done before this document).** "redisena la landing page con la skill de taste-skill"; the page lives in `frontend/src/app/page.tsx` + `landing.css`, credits in `/creditos`, the counter-rolls moment served from `public/moments`.
- **S2 — Shared look for the four pages.** "usa la misma skill para mejorar las paginas de /servicios, /rutas-compartidas, /login y /register". `/register` is the app's `/registro` route. The four pages take the landing's tokens, type, buttons and header/footer look. Assumption: the shared `MarketplaceHeader` / `MarketplaceFooter` get an opt-in variant used only by these pages, so panel, solicitudes, cuenta, pagos and the 404 keep their current look (not requested).
- **S3 — /servicios.** Same data, filters, pagination, quote dialog, states (loading, error, empty) and transparency note; redesigned head, filter bar and result cards. Every existing behaviour and id the specs use keeps working.
- **S4 — /rutas-compartidas.** Same as S3 for shared routes: origin/destination filters, date validation, join flow, stops, pagination.
- **S5 — /login and /registro.** Presentation only in `components/auth/auth-panel.tsx`; no change to the Supabase, MFA, provisioning or redirect logic.
- **S7 — Provider-only "Mis servicios" (L6).** "en el header de las pagina principales quita el boton de 'mis servicios' ese boton es para los proveedores". `MarketplaceHeader` shows the `/cuenta/servicios` link, desktop and mobile, only to panel roles (`independent_driver`, `company_owner`, `company_driver`, the existing `usesPanelNavigation`); anonymous visitors and customers no longer see it. This is the one logic change, requested explicitly.
- **S6 — Scope limit (L4).** "no cambies la logica de las paginas, solo el diseno visual". S2–S5 change styles, class names and presentational wrappers only: no state, handler, query, route, id, label or visible text changes. The existing specs must pass unchanged.

## Tasks

| ID | Specs | Route | Status | Evidence |
|---|---|---|---|---|
| T1 | S1 | inline | done | `6565c37`; Playwright 413/413; layout check clean at 5 sizes |
| T2 | S2, S6 | inline | done | `d129b91`; specs untouched, Playwright 415/415 |
| T3 | S3, S6 | inline | done | `d129b91`; shots 1440 and 390 |
| T4 | S4, S6 | inline | done | `d129b91`; shots 1440 and 390 |
| T5 | S5, S6 | inline | done | `d129b91`; auth handlers untouched; auth specs pass |
| T6 | S7 | inline | done | RED/GREEN in `header-roles.spec.ts`; Playwright 415/415 |

Route evidence: one model writing sequential, shared-surface units (header variant and shared CSS feed every page), so no Writer trigger; T5 touches auth UI only (no logic) — Risk item 2 is checked by keeping every handler untouched and running the auth specs.

## Log

- **L1 (2026-11-10, user):** "1. instala https://github.com/leonxlnx/taste-skill para este proyecto 2. crea una nueva rama 3. redisena la landing page con la skill de taste-skill 4. levanta el frontend en local para ver el nuevo diseno"
- **L2 (2026-11-11, user):** "ahora usa la misma skill para mejorar las paginas de /servicios, /rutas-compartidas, /login y /register"
- **L3:** Mapped the pages: `servicios/page.tsx` and `rutas-compartidas/page.tsx` (≈195 lines each) use `MarketplaceHeader`/`MarketplaceFooter` from `site-navigation.tsx`, which nine other routes share; `/login` and `/registro` render `AuthPanel` (686 lines, security logic). Specs pin ids (`#auth-*`, `#resultados`), classes (`.service-result-card`, `.shared-route-card`, `.results-count`, `.auth-error`, `form.auth-form`) and many strings; those are kept, and strings changed on purpose are updated in the specs.
- **L4 (2026-11-11, user):** "no cambies la logica de las paginas, solo el diseno visual" — added S6; copy changes the skill would ask for (tracked-capital kickers, greeting headings) are left as they are and listed in the report instead.
- **L6 (2026-11-11, user):** "en el header de las pagina principales quita el boton de 'mis servicios' ese boton es para los proveedores" — added S7. RED: two new `header-roles` tests (anonymous on /servicios desktop+mobile, client on /servicios) failed with "Expected: 0, Received: 1"; GREEN after gating both links on `panelNav`; the provider test that expects the link in the mobile menu still passes (10/10).
- **L5:** Engram mirror pending: `mem_save` is blocked in this session by a hook the auto-mode classifier cannot review.
