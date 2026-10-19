# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

`frontend/CLAUDE.md` (via `frontend/AGENTS.md`) warns that this Next.js version has breaking changes: read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing frontend code.

## Repository layout

Two independent apps, no workspaces. The root `package.json` only holds the Supabase CLI.

- `backend/` — FastAPI API (Python 3.12, `uv`). Source in `src/amira_api/`, Alembic migrations in `alembic/versions/`, tests in `tests/`.
- `frontend/` — Next.js 16 App Router (React 19, TypeScript, Tailwind). Source in `src/`, Playwright specs in `tests/`.
- `PROJECT_OVERVIEW.md` — domain spec and approved stack. Read it before changing business rules or the data model.
- `odd/tasks/` — feature task documents. `docs/` — deployment notes and mockups.

## Commands

Backend (run from `backend/`):

```bash
uv sync                                   # install deps from uv.lock
cp .env.example .env                      # then fill values
uv run uvicorn amira_api.main:app --reload
uv run pytest                             # all tests
uv run pytest tests/test_health.py::test_name   # single test
uv run pytest -k "keyword"                # filter by name
uv lock --check                           # lockfile must match pyproject
uv run alembic upgrade head               # needs DATABASE_URL
```

Frontend (run from `frontend/`, npm with `package-lock.json`):

```bash
npm install
npm run dev                               # http://localhost:3000
npm run lint
npm run build
npm run test:e2e                          # Playwright
npx playwright test tests/auth.spec.ts    # single spec file
node --test tests/unit/*.mjs              # node unit tests (no npm script)
node --test tests/unit/chats.node-test.mjs  # single unit file
```

Frontend logic in `src/lib/` (cache policy, pagination, error mapping, validation) is unit-tested with the built-in node runner in `tests/unit/*.node-test.mjs`. There is no `npm test` script, but this runner exists, so use it for RED/GREEN on frontend logic before you fall back to lint/build-only checks.

Playwright starts its own isolated app copy and fake Supabase endpoint on `127.0.0.1:3179`, so it does not need a running dev server or real Supabase credentials. Do not point it at a hosted project.

## Architecture

**Auth is split across two systems.** Supabase Auth owns passwords, email confirmation, and phone MFA. The FastAPI backend never issues login tokens: `auth.py` verifies Supabase JWTs against the project's JWKS (issuer and audience checked), then enforces Amira's own permissions. Never trust a client-supplied user ID.

**Request path:** browser → Next.js pages → `frontend/src/lib/marketplace-api.ts` and `frontend/src/lib/auth/account-api.ts` → FastAPI at `NEXT_PUBLIC_API_URL`. The browser never talks to the database. Business-critical writes (requests, quotations, payments, payouts) must go through FastAPI.

**Frontend session handling:** `src/proxy.ts` (Next 16's replacement for middleware) calls `src/lib/supabase/proxy.ts` to refresh the Supabase session on each request. Server components use `lib/supabase/server.ts`, client components use `lib/supabase/client.ts`. `/auth/callback` verifies the confirmed user server-side before the phone-MFA step.

**Backend structure:** `main.py` only wires routers and CORS. Each domain has a `*_routes.py` router plus a `*_schemas.py` for Pydantic models: account (provisioning the private `Usuario` record after SMS AAL2), email fallback, company invitations, public browse (page-size and offset caps), customer, provider services, quotations, payments, chats, and locations. Business transactions live in `*_service.py` modules (`quotation_service`, `payment_service`, `payout_service`), not in routers.

**Ports and adapters for money:** payments and payouts sit behind `PaymentProvider` / `PayoutProvider` ports. The only adapters are simulated (`simulated_payment_provider.py`, `simulated_payout_provider.py`), and they are fail-closed: they run only when `APP_ENV` is explicitly `development`, `local` or `test`. The composition root picks the adapter (`payment_routes.py` for payments, `release_payouts.py` for payouts); the domain services never do. Payouts are released by a CLI job, `uv run python -m amira_api.release_payouts`, which is not deployed. The same fail-closed `APP_ENV` rule guards `DEV_SKIP_SMS_MFA`. See `backend/README.md` for the full payment, claim and payout rules.

**Data model:** `models.py` holds the SQLAlchemy mappings. Python names are English; PostgreSQL table and column names keep the Spanish names from the Lucid ERD, so the two differ on purpose. `db.py` forces TLS and bounds the pool and statement timeout. Supabase tables have RLS enabled and privileges revoked from `anon`/`authenticated` (see the public-browse migration), so a privileged SQLAlchemy connection bypasses those policies. Enforce authorization in endpoints.

**Invariants the ORM does not enforce:** payment signature verification, state transitions, capacity/exclusivity locking, and payout release rules are business-transaction responsibilities in the service layer (see `backend/README.md`). Foreign keys alone do not guarantee them.

**Deployment:** `render.yaml` deploys only the backend, as a Docker service rooted at `backend/`, with `/health` as the health check. The frontend is not containerized.

## Conventions

- UI copy and routes are in Spanish (`/solicitudes`, `/servicios`, `/registro`). Code identifiers in the backend are English; DB names are Spanish.
- Backend checks run without a live database for structural and offline SQL checks (`backend/README.md`).
- Never put Supabase service-role keys in `NEXT_PUBLIC_*` variables.

## Rol: orquestador (solo si HERDR_ENV=1)
- Tú planificas y coordinas. No editas código.
- Divide el plan en tareas independientes que no toquen los mismos archivos.
- Cuando yo apruebe el plan, por cada tarea:
  1. PANE=$(herdr pane split --current --direction right --cwd "$PWD" --no-focus)
     (el id del panel nuevo está en .result.pane)
  2. herdr agent start worker-N --kind claude --pane <id> -- --model haiku --permission-mode acceptEdits
  3. herdr agent prompt worker-N "<tarea con contexto, archivos y criterio de 'listo'>" --wait --timeout 900000
- Al terminar cada worker: herdr agent read worker-N --source recent --lines 80 y verifica el resultado.
- Si un worker se bloquea: herdr agent explain worker-N antes de reintentar.
- Ante dudas de sintaxis, usa `herdr <grupo> --help` en vez de adivinar.
