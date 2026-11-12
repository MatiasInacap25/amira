# Redesign with taste-skill (landing, /servicios, /rutas-compartidas, /login, /registro)

Objective: apply taste-skill (`.claude/skills/design-taste-frontend`, tasteskill 2.5.1) to the landing and to the public search and auth pages, with the landing's system (Amira's colours, Geist, one button pair, one radius family). Branch: `feat/landing-redesign`. Delivery: `ask-on-risk`. Runners: Playwright (`npx playwright test`), `npm run lint`, `npx tsc --noEmit`, plus the skill's checkers (`assets/layout/check.mjs`, `scripts/consistency.mjs`).

## Specs

- **S1 — Landing (done before this document).** "redisena la landing page con la skill de taste-skill"; the page lives in `frontend/src/app/page.tsx` + `landing.css`, credits in `/creditos`, the counter-rolls moment served from `public/moments`.
- **S2 — Shared look for the four pages.** "usa la misma skill para mejorar las paginas de /servicios, /rutas-compartidas, /login y /register". `/register` is the app's `/registro` route. The four pages take the landing's tokens, type, buttons and header/footer look. Assumption: the shared `MarketplaceHeader` / `MarketplaceFooter` get an opt-in variant used only by these pages, so panel, solicitudes, cuenta, pagos and the 404 keep their current look (not requested).
- **S3 — /servicios.** Same data, filters, pagination, quote dialog, states (loading, error, empty) and transparency note; redesigned head, filter bar and result cards. Every existing behaviour and id the specs use keeps working.
- **S4 — /rutas-compartidas.** Same as S3 for shared routes: origin/destination filters, date validation, join flow, stops, pagination.
- **S5 — /login and /registro.** Presentation only in `components/auth/auth-panel.tsx`; no change to the Supabase, MFA, provisioning or redirect logic.
- **S7 — Provider-only "Mis servicios" (L6).** "en el header de las pagina principales quita el boton de 'mis servicios' ese boton es para los proveedores". `MarketplaceHeader` shows the `/cuenta/servicios` link, desktop and mobile, only to panel roles (`independent_driver`, `company_owner`, `company_driver`, the existing `usesPanelNavigation`); anonymous visitors and customers no longer see it. This is the one logic change, requested explicitly.
- **S8 — Copy (L7).** "cambia los textos": the copy the skill flags on the four pages changes; S6's no-text rule is lifted for copy only (logic still unchanged). Tracked-capital kickers and eyebrows go (`CONECTA. COTIZA. COORDINA.`, `SERVICIOS DE TRANSPORTE`, `VIAJES COMPARTIDOS`, `PRESTADORES PUBLICADOS`, `PUBLICADAS Y DISPONIBLES`, `TRANSPORTE, MÁS CERCA`); h1s name the category and place (`Servicios de transporte en todo Chile`, `Viajes compartidos con espacio libre`, `Tu cuenta para cotizar u ofrecer transporte de carga`); no greeting or pun (`Qué bueno verte` → `Inicia sesión`; the SMS line replaces `Tu seguridad también es parte del viaje.`); no jargon (`Supabase` out of the account step). Buttons already a verb and an object stay.
- **S9 — The rest of the pages (L8).** "ahora usa la misma skill para mejorar el resto de paginas, pero no modifiques la logica de las paginas". Pages: `/panel`, `/cuenta/{perfil,servicios,servicios/[serviceId],vehiculos,viajes-compartidos,invitaciones}`, `/solicitudes`, `/solicitudes/[requestId]`, `/mensajes`, `/mensajes/[chatId]`, `/pagos/{resultado,simulado}`, `/prestadores/[profileId]`, `/invitacion/conductor`, `/invitacion/conductor/aceptar`, the 404 and `/creditos`. They take the same tokens, Geist, buttons, fields, cards, header and footer as S2. Branch `feat/taste-skill-app-pages` (from develop). Same S6 limit: styles, class names and presentational wrappers only; no state, handler, query, route, id, label or text changes (tracked-capital kickers are restyled in CSS, their text stays). Assumption: the header/footer `lp` variant becomes the default, since every page now uses it.
- **S6 — Scope limit (L4).** "no cambies la logica de las paginas, solo el diseno visual". S2–S5 change styles, class names and presentational wrappers only: no state, handler, query, route, id, label or visible text changes. The existing specs must pass unchanged.

## Tasks

| ID | Specs | Route | Status | Evidence |
|---|---|---|---|---|
| T1 | S1 | inline | done | `6565c37`; Playwright 413/413; layout check clean at 5 sizes |
| T2 | S2, S6 | inline | done | `d129b91`; specs untouched, Playwright 415/415 |
| T3 | S3, S6 | inline | done | `d129b91`; shots 1440 and 390 |
| T4 | S4, S6 | inline | done | `d129b91`; shots 1440 and 390 |
| T5 | S5, S6 | inline | done | `d129b91`; auth handlers untouched; auth specs pass |
| T7 | S8 | inline | done | RED 6 failed with the new strings in the specs; GREEN 415/415 |
| T6 | S7 | inline | done | RED/GREEN in `header-roles.spec.ts`; Playwright 415/415 |
| T8 | S9, S6 | inline | done | Playwright 415/415 (twice), tsc and lint clean; tsx diff is class names and imports only; shared wiring: Geist on `<html>`, `lp` default header/footer, scope classes on every page's `main` |
| T9 | S9, S6 | inline | done | shots of every page reviewed at 1280 (and 390 for the 404); fixed kicker colour, invitation list, centred payment text, detail link size;  `src/styles/lp-pages.css`: panel, cuenta, solicitudes, mensajes, pagos, prestadores, invitaciones, 404 |

Route evidence: one model writing sequential, shared-surface units (header variant and shared CSS feed every page), so no Writer trigger; T5 touches auth UI only (no logic) — Risk item 2 is checked by keeping every handler untouched and running the auth specs.

## Log

- **L1 (2026-11-10, user):** "1. instala https://github.com/leonxlnx/taste-skill para este proyecto 2. crea una nueva rama 3. redisena la landing page con la skill de taste-skill 4. levanta el frontend en local para ver el nuevo diseno"
- **L2 (2026-11-11, user):** "ahora usa la misma skill para mejorar las paginas de /servicios, /rutas-compartidas, /login y /register"
- **L3:** Mapped the pages: `servicios/page.tsx` and `rutas-compartidas/page.tsx` (≈195 lines each) use `MarketplaceHeader`/`MarketplaceFooter` from `site-navigation.tsx`, which nine other routes share; `/login` and `/registro` render `AuthPanel` (686 lines, security logic). Specs pin ids (`#auth-*`, `#resultados`), classes (`.service-result-card`, `.shared-route-card`, `.results-count`, `.auth-error`, `form.auth-form`) and many strings; those are kept, and strings changed on purpose are updated in the specs.
- **L4 (2026-11-11, user):** "no cambies la logica de las paginas, solo el diseno visual" — added S6; copy changes the skill would ask for (tracked-capital kickers, greeting headings) are left as they are and listed in the report instead.
- **L6 (2026-11-11, user):** "en el header de las pagina principales quita el boton de 'mis servicios' ese boton es para los proveedores" — added S7. RED: two new `header-roles` tests (anonymous on /servicios desktop+mobile, client on /servicios) failed with "Expected: 0, Received: 1"; GREEN after gating both links on `panelNav`; the provider test that expects the link in the mobile menu still passes (10/10).
- **L7 (2026-11-11, user):** "cambia los textos, y despues subelo a develop y crea en vercel otro proyecto que apunte a la rama de develop, esto para poder compartir el link con mis companeros y que vean las 2 versiones (la que esta en main y la que hiciste ahora)" — added S8; delivery to develop and the Vercel project follow.
- **L8 (2026-11-11, user):** "ahora usa la misma skill para mejorar el resto de paginas, pero no modifiques la logica de las paginas" — added S9, T8, T9. Route: inline, one model on one shared stylesheet (no Writer trigger). Map: 21 `main` wrappers (`marketplace-main` or `auth-shell`), page CSS in `globals.css` 419–1130 with hard-coded colours, so the restyle is a scoped stylesheet over the existing classes.
- **L5:** Engram mirror pending: `mem_save` is blocked in this session by a hook the auto-mode classifier cannot review.
