# Terms and Conditions Acceptance at Registration

Objective: every new user (client, company owner, independent driver, invited company driver) must accept the Terms and Conditions in the registration form; the backend refuses provisioning without the current version and stores the acceptance.
Branch: `feat/terms-acceptance` (shared tree, parent owns git — workers do NOT commit, push, or run repo-wide formatters/installs). Runners: backend `uv run pytest` (from `backend/`); frontend `npx playwright test`, `npm run lint`, `npm run build` (from `frontend/`).

## Specs

### S1. Contract (fixed by the parent, both workers must match it exactly)
- Current version string: `"2026-11-23"`.
- Backend constant `TERMS_VERSION = "2026-11-23"` in new module `backend/src/amira_api/terms.py`.
- Frontend constant `TERMS_VERSION = "2026-11-23"` in new module `frontend/src/lib/legal/terms.ts`.
- `POST /api/account/provision` body gains a required field `accepted_terms_version` (string). Missing, empty, or different from `TERMS_VERSION` → HTTP 422 with message "Debes aceptar los Términos y Condiciones vigentes." (use the same 422 detail-list shape the endpoint already uses for `commune_code`: `[{"loc": ["body", "accepted_terms_version"], "msg": "Debes aceptar los Términos y Condiciones vigentes.", "type": "value_error"}]`).

### S2. Backend storage (worker-1)
- New model `TermsAcceptance` in `models.py`, table `"Aceptacion_Terminos"`: `ID` (UUID PK, `gen_random_uuid()` like the others), `ID_Usuario` (FK → `Usuario.ID`, `ON DELETE CASCADE`, indexed), `Version` (String(20), not null), `Fecha_Aceptacion` (timestamptz, not null), `IP` (String(64), nullable), `User_Agent` (String(512), nullable). Unique constraint on (`ID_Usuario`, `Version`).
- New additive Alembic migration after `20261120_0001_payment_provider_transactions.py` (follow its naming and `down_revision` pattern). Enable RLS on the new table and revoke privileges from `anon` and `authenticated`, exactly like the existing migrations do for their tables. Downgrade drops the table.
- In `provision_account` (`backend/src/amira_api/account_routes.py`): validate S1 before any write; after the `Usuario` exists, insert one `TermsAcceptance` row in the same transaction with the request IP (`request.client.host`, or the first `X-Forwarded-For` value when present) and the `User-Agent` header (truncate to 512). If a row for (user, version) already exists, do not insert another and do not fail (re-provision is idempotent).
- Add the field to `AccountProvisionRequest` in `account_schemas.py`.
- Tests in `backend/tests/` (new file `test_terms_acceptance.py`, reuse the fixtures/helpers the existing provision tests use): missing field → 422 with the exact message; wrong version → 422; valid → 201 and exactly one row with version, timestamp and user agent; second provision with the same version → no duplicate row; update every existing provision test payload so the whole suite stays green.

### S3. Frontend (worker-2)
- `frontend/src/lib/legal/terms.ts`: `TERMS_VERSION` and the terms content as structured data (sections with title + paragraphs/lists/table) transcribed from `docs/legal/terminos-y-condiciones.md` **verbatim** (Spanish). Drop the blockquote draft note at the top of the doc; keep everything else, including bracketed placeholders.
- `frontend/src/components/legal/terms-dialog.tsx`: accessible modal (`role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing at the title "Términos y Condiciones de Uso de Amira"), scrollable body rendering the content, closes with Escape, the "Cerrar" button and backdrop click; focus moves into the dialog on open and returns to the trigger on close. Footer buttons: "Cerrar" and "Aceptar". "Aceptar" closes the modal and marks the checkbox. Follow the existing dialog in `frontend/src/components/account/publish-shared-trip-dialog.tsx` for structure and styling conventions.
- In `frontend/src/components/auth/auth-panel.tsx`, register mode only: a required checkbox above the submit button with the label "Acepto los Términos y Condiciones", where "Términos y Condiciones" is a button that opens the modal (it must not toggle the checkbox by itself). The submit button is disabled until the checkbox is checked. Store `acceptedTermsVersion: TERMS_VERSION` in the `RegistrationDraft` and send it as `accepted_terms_version` in the provision request (find where the draft is turned into the provision payload). The login form itself shows no checkbox. When an already-confirmed account reaches the account/provision step through login (no registration draft carrying `TERMS_VERSION`), that step shows the same required checkbox and dialog, the provision button stays disabled until it is checked, and `accepted_terms_version` is never sent empty. When the draft already carries `TERMS_VERSION`, the account step does not ask again.
- Do not create a `/terminos` route.
- Update `frontend/tests/support/fake-auth-server.mjs` / the fake API if it validates the provision payload, so it accepts the new field.
- Playwright (add to `frontend/tests/page-registro.spec.ts` or `auth.spec.ts`, whichever already covers the register form): submit disabled until the checkbox is checked; clicking "Términos y Condiciones" opens the dialog with its title visible; "Aceptar" closes it and checks the box; Escape closes it without checking; the provision request carries `accepted_terms_version: "2026-11-23"` (if the existing tests already intercept provision). Update existing register tests so they check the box first.
- Read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing Next.js code (this Next version has breaking changes).

## Tasks

| ID | Specs | Route | Status |
|---|---|---|---|
| T1 | S1, S2 | delegated (worker-1, fixer-1, herdr) | done |
| T2 | S1, S3 | delegated (worker-2, fixer-2, herdr) | done |

Route reason: project CLAUDE.md orchestrator role under `HERDR_ENV=1`; two independent units with disjoint edit surfaces launched together.

## Log

- L1 (2026-11-23, user): "agrega los temrinos y condiciones en el registro de los usuarios (tanto cientes como proveedores o conductores) y despues subleo a develop y main"
- L2 (2026-11-23, user): "que los terminos y condiciones se abran como un modal mejor"
- L3: All roles register through `frontend/src/components/auth/auth-panel.tsx` (roles client, company_owner, independent_driver; invited drivers use the same form with `intent=invite`) and are provisioned by `POST /api/account/provision`, so one checkbox + one backend check covers everyone.
- L4 (decision by parent): worker-2 found that login-path provisioning had no draft and would send an empty version (backend 422). Resolved by showing the checkbox on the account step for that path; S3 rewritten accordingly.
- L5: Native gentle-ai review (Codex, consent granted by the user) returned correction_required with 4 blockers: race on the acceptance insert (500), modal without focus trap, S3 drift (resolved by L4), version > 20 chars returning the generic 422. Fixes delegated to fixer-1 (backend) and fixer-2 (frontend).
- Verification so far: backend 1247 passed (1 pre-existing env-dependent failure, also failing on the base); frontend lint/tsc 0, unit 231/231, Playwright full suite 461 passed after fixing the stale shared-routes assertion from cceb5c7.
- L6: Native review escalated (not approved): 7 findings validated as resolved (race, focus trap, long-version message); R2-002/R3-002 remain only because the validator applies the frozen original S3. User accepted the L4 decision and asked to deliver under ordinary repository policy.
