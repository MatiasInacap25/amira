# Spec: Linked drivers list for company owners

## Objective

A company owner opens the provider panel (`/panel`) and sees a "Conductores" button. It leads to a page that lists every driver linked to their company, so they can check who belongs to it and whether each driver is verified.

User request (verbatim): "en el panel de proveedor agrega en el caso de ser company owner que tengan en el panel un boton para ver los conductores enlazados a su compania"

Users: only accounts with role `company_owner`. Independent drivers and customers never see the button or the page.

### Acceptance criteria

1. In `/panel`, a `company_owner` sees a "Conductores" action linking to `/cuenta/conductores`. An `independent_driver` does not see it.
2. `/cuenta/conductores` lists the company's linked drivers (including the owner when they are also a driver, marked "Dueño"), sorted by first name, showing for each one: full name, email, phone (or "No indicado") and verification state ("Verificado" / "Sin verificar").
3. With no linked drivers, the page shows an empty state with a link to `/cuenta/invitaciones` to invite one.
4. A non-owner who opens `/cuenta/conductores` sees a "not available for your account" state, and the API answers 403 (enforced by the backend, not only hidden in the UI).
5. Loading and error states follow the existing `/cuenta/*` pages (skeleton, retry message).
6. The page is read-only: no unlinking or editing in this iteration.

## Tech Stack

- Backend: FastAPI (Python 3.12, `uv`). New owner-only `GET /api/company/profiles/me/drivers` in `invitation_routes.py`, returning `{ items: [{ driverId, firstName, lastName, email, phone, verified, isOwner }] }`. It reuses `provider_drivers_query` and `verified_driver_condition`. The existing `GET /api/provider/drivers` stays unchanged, so shared trips never receive contact data.
- Frontend: Next.js 16 App Router, React 19, TanStack Query, Tailwind/`lp-*` styles. Reuses the client in `frontend/src/lib/shared-trip-api.ts:57`.

## Commands

```bash
# backend/
uv run pytest tests/test_shared_trip_routes.py -k drivers
uv run pytest
# frontend/
npx playwright test tests/page-panel.spec.ts tests/page-cuenta-conductores.spec.ts
npm run lint
npm run build
```

## Project Structure

```
frontend/src/app/panel/page.tsx                 → add the owner-only "Conductores" action
frontend/src/app/cuenta/conductores/page.tsx    → new page (container)
frontend/src/components/account/linked-drivers-list.tsx → presentational list
frontend/tests/page-cuenta-conductores.spec.ts  → new Playwright spec
frontend/tests/page-panel.spec.ts               → button visibility per role
backend/tests/test_shared_trip_routes.py        → only if the 403 for non-owners is not yet pinned
```

## Code Style

Follow the existing panel actions and `/cuenta/*` pages. UI copy and routes in Spanish, identifiers in English:

```tsx
{role === "company_owner" && (
  <li><Link className="panel-action" href="/cuenta/conductores">Conductores <ArrowRight aria-hidden="true" size={16} /></Link></li>
)}
```

Container-presentational: the page fetches with `useQuery`; `LinkedDriversList` only renders props.

## Testing Strategy

- Playwright (fake Supabase/API on `127.0.0.1:3179`): button visible for `company_owner`, absent for `independent_driver`; list with verified and unverified drivers; empty state with the invitations link; API error state; non-owner state.
- Backend pytest: confirm `GET /api/provider/drivers` answers 403 to a non-provider and returns only the caller company's drivers (add a test only if missing).
- RED before GREEN for each new behavior.

## Boundaries

- Always: enforce access in the backend; run the focused specs and the suite before committing; keep Spanish UI copy.
- Ask first: adding fields to the API response (email, phone, plate), unlinking drivers, any schema change.
- Never: expose other companies' drivers; trust a client-side role check alone; put service-role keys in `NEXT_PUBLIC_*`.

## Success Criteria

All six acceptance criteria are covered by passing Playwright/pytest tests, lint and build pass, and an owner can open the list from `/panel` in the deployed app.

## Decisions (2026-11-16)

1. Owner who is also a driver: included.
2. "mas datos y ver si esta vereficado": email, phone and verification state.
3. Route: `/cuenta/conductores`.
