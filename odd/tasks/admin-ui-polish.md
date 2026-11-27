# Admin Panel Visual Polish

Objective: give the admin panel (`/admin`) basic visual design — table separators, KPI cards on a grey ground, tidy filters — without changing data, routes or backend.
Branch: `feat/admin-ui-polish` from `develop`. Frontend only. Runners (from `frontend/`): `npm run lint`, `npx tsc --noEmit`, `node --test tests/unit/*.mjs`, `npm run build`, `npx playwright test` (admin specs at least, full suite at the end).
Read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing Next.js code (this Next version has breaking changes).

## Specs

### S1. Root cause: design tokens missing in the admin scope
- `frontend/src/app/admin/admin.css` styles everything with `var(--lp-*)` tokens, but `frontend/src/styles/lp-tokens.css:4` defines them only for `.lp, .lp-app, .lp-app-header, .lp-app-footer, .lp-auth, .quote-dialog, .shared-trip-dialog-backdrop`. Inside `.admin-frame` they are undefined, so table borders, card backgrounds, input borders and the primary button colour disappear (and the daily chart renders a black bar).
- Fix: add `.admin-frame` (and the admin `dialog`s if they render outside it) to that selector; make sure the token file is imported by the admin layout. Check every `var(--lp-*)` used in `admin.css` and admin components resolves.

### S2. Dashboard (`/admin`, "Principal")
- User request: "que en la pagina principal cada dato este en su propio card con un fondo de un color mas gris".
- Page ground grey (`--lp-surface` or `--lp-bg`), each KPI in its own white card with border, radius and a subtle shadow.
- Group KPIs under three headings: "Dinero" (Recaudado, Reembolsado, Recaudado neto, Comisiones, IVA débito de Amira), "Transportistas" (Por pagar a transportistas, Pagado a transportistas), "Operación" (Servicios en curso/completados/cancelados, Documentos de conductores, Reclamos abiertos, Cuentas bancarias pendientes).
- Card content: small muted label, large figure, optional description below. Grid: 4 columns desktop, 2 tablet, 1 phone.
- Period filter (select + "Aplicar") inside a toolbar card; "Aplicar" styled as primary button.
- Daily chart ("Recaudación y comisiones diarias") inside its own card, brand colours (blue = recaudado, orange = comisiones) matching the legend text, visible axis/baseline; no black bars.

### S3. Tables (shared `components/admin/data-table.tsx` / `resource-table.tsx`)
- User request: "lineas en las tablas para separar cada campo".
- Table inside a white card; header row grey background, small uppercase/semibold muted text; horizontal line between rows and subtle vertical separators between columns; zebra rows and hover.
- Money columns right-aligned with tabular numbers; dates `white-space: nowrap`; the ⋮ actions column narrow and right-aligned.
- Long UUID cells (e.g. Pagos: N°, Servicio, Cotización, ID externo) show a shortened value (first 8 chars + "…") with the full value in `title` and a copy button with an accessible label; links keep working. Rows must no longer wrap an id over several lines.
- Pagination text ("Mostrando 1–4 de 4") below the card, aligned with it.

### S4. Filters (`components/admin/filters.tsx`)
- Filters inside a card using a grid: label above control, every control same height with visible border (`.admin-input`), consistent gaps.
- Buttons grouped at the end: "Aplicar filtros" primary; "Limpiar filtros" and "Exportar CSV" secondary (`.admin-button`).
- When a section has more than ~5 filters (e.g. Pagos), show search, estado and fechas, and put the rest under a "Más filtros" disclosure (`<details>` is fine). Existing filter behaviour, query params and test ids must not change.

### S5. Sidebar and page header
- Active item: soft background plus a coloured left bar, no box that looks like a focus ring (keep a real `:focus-visible` ring).
- Pending counters (e.g. "9" on Desembolsos) as an orange badge.
- Each page header: title, description and a bottom separator line with spacing before the content.

### S6. Verification
- No backend changes, no route/data/copy changes except the new "Dinero", "Transportistas", "Operación", "Más filtros" labels and the copy-button label.
- lint, tsc, node unit, build and Playwright pass (update only selectors/expectations that the new markup legitimately changes).
- Before/after screenshots of `/admin`, `/admin/clientes` and `/admin/pagos` (desktop 1440px and phone 390px) saved under `output/admin-ui-polish/`; no horizontal page scroll at 390px except inside table scroll containers.

## Tasks

| ID | Specs | Route | Status | Commit |
|---|---|---|---|---|
| T1 | S1, S5 | inline (Codex) | complete | `4be0bf3` |
| T2 | S2 | inline (Codex) | complete | `4b1d1dc` |
| T3 | S3, S4 | inline (Codex) | complete | `feat(admin): polish resource tables and filter controls` |
| T4 | S6 | inline (Codex) | pending | |

Route: sequential inline work in the already-checked-out Codex branch; each slice has its own local commit. No branch or remote changes. Risk: presentational CSS/markup and narrowly scoped browser interaction, with no data or auth changes.

## Log

- L1 (2026-11-27, user): "mira como se ve el panel, muestra toda la informacion(que esta bien) pero le falta diseno basicom, como lineas en las tablas para separar cada campo, que en la pagina principal cada dato este en su propio card con un fondo de un color mas gris, cosas asi, haz un plan para mejorar esto."
- L2: Root cause found by the parent: `--lp-*` tokens are not defined inside `.admin-frame` (see S1).
- L3 (2026-11-27, user): "con codex, primero abre un panel a la derecha y cuando te diga le pasas el plan" → "pasaselo".
- L4 (2026-11-27, user): Work in /mnt/data/projects/amira on the already-checked-out branch feat/admin-ui-polish (do not switch branches, no remote git operations, no repo-wide formatters or installs). Spec: odd/tasks/admin-ui-polish.md — read it fully until ## Log, then implement T1..T4 in order (S1-S6). Frontend only. Follow existing conventions in frontend/src/app/admin/admin.css and frontend/src/components/admin/. Before writing Next.js code read the relevant guide in frontend/node_modules/next/dist/docs/. After each task run its checks, make one conventional commit (no AI attribution, no Co-Authored-By) and update the Tasks table/Log in the spec file. The known backend env failure is irrelevant here. At the end report: commits, which S# are covered, check results (lint, tsc, node unit, build, Playwright) and where the screenshots are.
- T1: S1/S5. Playwright reproduced a transparent frame before the fix; all 13 admin Playwright checks passed after it. Lint and Node unit (246 pass, one existing TODO) passed; tsc passed after regenerating stale route types with next typegen. All 12 referenced admin tokens resolve. Captured six baseline screenshots with the local fixture before editing the UI.
- T2: S2. The new grouping test was RED before implementation; then all 14 admin Playwright checks passed, including the 4/2/1 grid, period query, and chart colors. Lint, tsc, and Node unit (246 pass, one existing TODO) passed. Native assessment for T1: medium, under budget.
- T3: S3/S4. RED reproduced the full UUID and always-visible advanced filters; 16 admin Playwright checks passed after the change, including clipboard, original detail URLs, pagination, disclosure and query/reset behavior. Lint, tsc and Node unit (246 pass, one existing TODO) passed. Native assessment through T2: medium, under budget.
