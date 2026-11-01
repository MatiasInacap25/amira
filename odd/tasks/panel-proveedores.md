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
- **S3 Provider profile publication.** User: "agrega todo lo que necesita configurar los proveedores para que su perfil quede publico y aparezca cuando un usuario busca un servicio".
  - Backend contract (owner-only via `invitation_routes._owned_provider`: `company_owner` and `independent_driver`; client and `company_driver` get 403):
    - `GET /api/provider/profile` → `{name, kind, description, commune_code, service_type_ids, published, missing}`; `missing` lists the absent items among `"description"`, `"commune"`, `"service_types"`, in that order.
    - `PUT /api/provider/profile` body `{description, commune_code, service_type_ids, name?}`; `name` only accepted for `kind == "company"`; unknown commune or service type → 422; replaces `ServicioDisponible` rows for the profile; returns the GET shape; a save that leaves a published profile incomplete unpublishes it.
    - `POST /api/provider/profile/publish` → sets `public_activated_at` if unset; 422 with `{message, missing}` when the description is blank, the commune is missing or there is no service type; returns the GET shape.
    - `POST /api/provider/profile/unpublish` → clears `public_activated_at`; returns the GET shape.
    - A published profile with a service type appears in the public provider search; after unpublish it does not.
    - User (2026-10-31): "haz que cuando se relelnen los campos para publicar sea necesario rellenar todo". Publishing requires every profile field: a non-blank description, a commune, at least one service type (and the existing non-blank name for companies). `missing` keys: `"description"`, `"commune"`, `"service_types"`, in that order.
    - User chose option A: a `PUT` that leaves a published profile incomplete unpublishes it automatically (clears `public_activated_at`) and returns `published: false` with `missing`.
  - Frontend fixes (user: "mejora los 3 puntos"): a `null` description from the backend renders as an empty controlled textarea; "Publicar perfil" saves unsaved form edits first and then publishes; publishing is disabled until every field is filled, and the checklist includes "Escribe una descripción". When a save unpublishes the profile, the page says so.
  - Frontend `/cuenta/perfil` for providers: form for description, commune and service types (company also name), a checklist of missing items, and publish/unpublish. Clients and company drivers keep the read-only view.
  - Out of scope (user confirmed 2026-10-31): vehicles (DB requires an image upload) and logo (no public asset mechanism).
  - Risk: high (data writes, authorization); needs an independent verifier.

## Tasks

| ID | Specs | Route | Status | Evidence |
|----|-------|-------|--------|----------|
| T1 | S1 | delegated (herdr worker-1, parallel with T2) | done | `03dc60e`; unit RED→GREEN 10/10; independent verifier PASS, no blockers |
| T2 | S2 | delegated (herdr worker-2, parallel with T1) | done | `d7713b7`; page-panel.spec 5/5, cuenta/servicios specs green |
| T3a | S3 backend | delegated (herdr worker-1, parallel with T3b) | done | `5691a55`; profile routes 39/39, backend 716/716, uv lock clean |
| T3b | S3 frontend | delegated (herdr worker-2, parallel with T3a) | done | `2dce87f`; unit 145/145, e2e 57/57, lint and tsc clean |

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
- L11 (2026-10-30) user: "si y despues sube todo a una rama de develop". Open redirect fixed in `4f34406` (reject normalized paths starting with "//" or containing "\"); unit RED→GREEN 12/12, auth and login e2e 28/28. Branch review of the whole feature approved and acknowledged (no blockers). Assessment of `4f34406`: medium, under_budget.
- L12 Pushed to a new `develop` branch on origin at the user's request. T3 (S3) remains planned only.
- L13 (2026-10-31) user: "sigue con el mensaje confuso". Fixed in `5d2ad40`: accountAccessMessage(reason, subject) in provider-request-access.ts; /panel and /cuenta/perfil show "Verifica tu teléfono por SMS para ver tu panel/perfil." for AAL1 sessions. /login does not resume SMS for an AAL1 session, so the button stays "Iniciar sesión". User chose option 2: explicit field instead of the constructor parameter property, plus tests/support/alias-loader.mjs registered from the unit test so node can import modules with "@/" imports. Unit 129/129, e2e 20/20, lint and tsc clean. Assessment: medium, under_budget.
- L14 (2026-10-31) user: "sigue con el punto 3"; plan approved ("si") with vehicles and logo out of scope. Contract fixed in S3 so T3a (backend) and T3b (frontend) run in parallel with disjoint files.
- L15 (2026-10-31) Verifier: no blockers; advisories: null description in textarea, published profile can be saved incomplete, Publish ignores unsaved edits. User: "A, mejora los 3 puntos y haz que cuando se relelnen los campos para publicar sea necesario rellenar todo". S3 updated; T3a/T3b reopened for the correction.
- L16 (2026-10-31) Corrections done; verifier recheck PASS, no blockers, three advisories resolved. Public-search visibility checked by reasoning over the SQL only (Postgres-only query). User approved the extra "Escribe el nombre de la empresa" label and asked: "si, y despues sube todo a develop". Commits `5691a55` (backend), `2dce87f` (frontend).
- L17 (2026-10-31) Branch review of `5691a55..fd95e2e` approved and acknowledged, 7 non-blocking advisories. User: "si, y súbelo a develop, despues corrige las 7 observaciones". S3 contract lines updated to match the implemented rules.
- L18 (2026-10-31) Seven review advisories addressed: doc contract (`bc20fca`), commune code constant and Postgres search test guarded to local hosts (backend), field-error mapping, refresh after failed publish, fixture kinds and test name (frontend). Unit 148/148, e2e 30/30, backend 732 passed 1 skipped (Postgres search test, needs AMIRA_TEST_DATABASE_URL), lint, tsc, uv lock clean.
