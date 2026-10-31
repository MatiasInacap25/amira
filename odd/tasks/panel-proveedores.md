# Panel de proveedores

Objective: role-based post-login redirect, a `/panel` dashboard, and (planned only) provider profile publication settings.
Branch: `feat/panel-proveedores` · Delivery: ask-on-risk · Runners: `node --test tests/unit/*.node-test.mjs`, `npx playwright test` (frontend), `uv run pytest` (backend).

## Specs

- **S1 Redirect by role.** Source (Notion "Cambios Amira"): "Cuando un proveedor(conductor independiente/dueño empresa) o un conductor inician sesion se le redirige a una pagina de dashboard".
  - After sign-in, roles `independent_driver`, `company_owner` and `company_driver` go to `/panel`; `client` keeps the current destination.
  - An explicit, safe `next` query parameter keeps priority over `/panel`.
  - If `GET /api/account/me` fails, fall back to the current destination.
  - Checks: unit test for the pure path function; `auth.spec.ts`, `page-login.spec.ts`, `page-registro.spec.ts` still pass.
- **S2 `/panel` dashboard.** Source: "(los proveedores tiene botones de mensajes, servicios, configuracion de perfil y el conductor ve los servicios que tiene y tambien un boton para ver su perfil y configurarlo)". User: "la ruta se llama panel, agrega tambien el boton de invitacion".
  - Providers (`independent_driver`, `company_owner`): buttons to Mensajes (`/mensajes`), Servicios (`/cuenta/servicios`), Configuración del perfil (`/cuenta/perfil`).
  - `company_owner` also gets Invitaciones (`/cuenta/invitaciones`).
  - `company_driver`: list of assigned services (from `GET /api/provider/services`, reusing the existing services view) and a Mi perfil button (`/cuenta/perfil`).
  - `client`: redirected to `/servicios`. Signed out: the sign-in prompt used by other private pages.
  - Checks: e2e spec covering provider, company owner, driver, client and signed out; lint and tsc clean.
- **S3 Provider profile publication (PLANNED, not implemented).** User: "agrega todo lo que necesita configurar los proveedores para que su perfil quede publico y aparezca cuando un usuario busca un servicio".
  - Backend `/api/provider/profile`: `GET` (data, offered service types, publication state); `PUT` (description, commune, company display name, service types); `POST /publish` (requires at least one service type and a commune, 422 listing what is missing); `POST /unpublish`. Owner-only, via `invitation_routes._owned_provider`.
  - Frontend `/cuenta/perfil` for providers: form for description, commune and service types, a checklist of missing items, and publish/unpublish. Clients keep the read-only view.
  - Out of scope (assumption, to confirm): vehicles (DB requires an image upload) and logo (no public asset mechanism).
  - Risk: high (data writes, authorization); needs an independent verifier.

## Tasks

| ID | Specs | Route | Status | Evidence |
|----|-------|-------|--------|----------|
| T1 | S1 | delegated (herdr worker-1, parallel with T2) | done | `03dc60e`; unit RED→GREEN 10/10; independent verifier PASS, no blockers |
| T2 | S2 | delegated (herdr worker-2, parallel with T1) | done | `d7713b7`; page-panel.spec 5/5, cuenta/servicios specs green |
| T3 | S3 | not started (user asked to plan only) | planned | |

## Log

- L1 (2026-10-30) user: "cuando termines haz un plan para los 3 puntos (1.redireccion sgun el rol, 2. pagina /panel (dashboard), 3. la configuracion del perfil para hacerlo publico) y haz solo el punto 1 y 2"
- L2 (2026-10-30) user: "la ruta se llama panel, agrega tambien el boton de invitacion, ademas agrega todo lo que necesita configurar los proveedores para que su perfil quede publico y aparezca cuando un usuario busca un servicio"
- L3 Evidence: public search (`public_routes.py:567`) needs `Perfil.public_activated_at` set and at least one `ServicioDisponible`; no endpoint writes them today. `GET /api/provider/services` already scopes company drivers to their assigned services.
- L4 Earlier unrelated work committed on this branch: `c71be81` (RUT mask), `2cad0c2` (profile menu and page).
- L5 Next: T1 and T2 in parallel via herdr workers; parent runs the e2e seam check once.
- L6 (2026-10-30) User chose option 1: extract a chrome-less ProviderServicesBody from provider-services-view.tsx for the driver panel. User approved making lib/auth/safe-next-path.ts a re-export so safeNextPath has one implementation (post-login-path.ts).
- L7 Seam check: node unit 122/122, Playwright 106/106 (auth, login, registro, panel, cuenta/servicios, header, invitaciones), lint and tsc clean.
- L8 Verifier advisory (pre-existing at baseline, reproduced): safeNextPath("/..//evil.example") returns "//evil.example", which resolves to https://evil.example/ (open redirect in /auth/callback and now in the post-login redirect). Fix pending user decision.
- L9 Advisory: /panel and /cuenta/perfil show the "Inicia sesión" message when the session is AAL1 (SMS pending); requestErrorMessage could distinguish it.
- L10 Next: decide the open-redirect fix; T3 (S3) stays planned only.
