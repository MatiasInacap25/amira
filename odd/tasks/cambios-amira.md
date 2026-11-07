# Cambios Amira

Objective: implement items 1-7 and 9 of the Notion page "Cambios Amira". Items 8 and 10 (shareable service) wait for business rules.
Branch: feat/cambios-amira. Delivery strategy: ask-on-risk. Test runners: `uv run pytest` (backend), `node --test tests/unit/*.mjs` and Playwright (frontend).

## Specs

- S1 (item 1): "al enviar la cotizacion por parte del proveedor la cotizacion sale como un mensaje del cliente cuando deberia salir como un mensaje por parte del proveedor". A quotation renders on the provider's side of the chat for both viewers: right for the provider, left for the customer.
- S2 (item 2): "al pagar sale pagina no encontrada". `/pagos/simulado` must render on a deployed build when `NEXT_PUBLIC_APP_ENV` is `development`, `local` or `test`, and stay fail-closed (404) otherwise, using the allowlist pattern of `frontend/src/lib/auth/dev-mfa.ts`.
- S3 (item 3): "en el panel de proveedores y conductor quitar en el header los botones de “Buscar Servicios”, “Rutas compartidas” y “Como funciona”". Approved default: hide them for provider, company and company driver roles across the whole site, including the home page header, and also hide the "Buscar un servicio" button. Anonymous and customer users keep them.
- S4 (item 4): "Mejorar la UI del panel de proveedores". Reference: the Notion capture of "Configuración del perfil", where account data is plain text with no hierarchy.
- S5 (item 5): "en el panel de proveedor, en solicitudes hacer que todo el div sea un boton que lleve a la solicitud".
- S6 (item 6): "El modal de cotizacion por parte del cliente tiene que estar centrado".
- S7 (item 7): "en el modal que se puedan adjuntar imagenes, que la direccion de origen y destino no sea opcional, separa la fecha y la hora en 2 campos, quitar el campo de medidas de la carga, hacer que el peso y volumen estimado sea opcional". Approved default: date and time require each other. The measures column stays for old rows.
- S9 (item 9): "que el modal de cotizacion del chat por parte del proveedor tiene que estar centrado y agregar el tipo de servicio". Approved default: service type is read-only, taken from the chat.

## Tasks

- [x] T1, S1 S2 S9, delegated (parallel, herdr worker-1): quotation side class, payment page gate, service type in the provider modal. Commit fe167c3. RED not observed for S1 S9.
- [x] T2, S7 fields, delegated (parallel, herdr worker-2): required addresses, date and time, no measures, optional weight and volume. Commit e324509. RED not observed.
- [x] T4, S3 S4 S5 S6 S1-css, delegated (parallel, herdr worker-4): header by role, panel UI, clickable card, sole owner of globals.css during this wave. Commit bf37af8. S4 is visual, no RED applies; RED not observed for S3.
- [x] T3, S7 images, delegated (after T1 T2 T4, herdr worker-3): image upload and display. High risk: storage and permissions. Commit 2791fe4, close fix in the next commit. Backend RED was an import error, not behavioral; frontend RED observed on 5 tests. Independent verification: one blocker (closing the dialog during uploads lost the notice), fixed with RED observed, recheck 42 of 42.
- [x] T5, delegated (herdr reviewer): Codex gpt-6.1-sol native gentle-ai review. Lineage review-d109541af1f59814: correction_required (R4-storage-lock), fixed in 57e3a40, targeted validation accepted, acknowledged, authority burned. Non-blocking warning: photo controls stay editable during upload (quote-request-dialog.tsx:184).

Route evidence: parallelism trigger, disjoint edit surfaces. The parent owns git.

Seam: T1 adds the class `chat-timeline-quotation--own` in `chat-thread-view.tsx` when `viewerRole === "provider"` for T1's side rule; T4 styles it in `globals.css` with `align-self: flex-end`. Exact side rule in S1: T1 owns it.

## Log

- L1 (2026-11-07), user's original request: "ahora conectate a mi notion a la pagina de cambios de amira, deje los cambios que es necesario hacer a la aplicacion actualmente". Then "dale" to items 1-7 and 9, then "dale, lanza los workers" to the plan with its defaults.
- L2: root causes mapped by a read-only explorer, from static reading. Parent spot check: `frontend/src/app/pagos/simulado/page.tsx:7` calls `notFound()` when `NODE_ENV === "production"`.
- L3: pending outward steps, each needing user authorization: private Supabase bucket for images; check `NEXT_PUBLIC_APP_ENV` on Vercel and redeploy.
- L4 (2026-11-07): workers stopped on Bash prompts under acceptEdits; the user approved a project-local allowlist. `flock` can never be allowlisted, so the parent ran Playwright serially. The user set the workers to auto mode.
- L5 (2026-11-07): parent verification on the combined tree after T1 T2 T4: Playwright 380 passed, 2 failed (fixtures missing the new required addresses, fixed by worker-2, then 52 of 52 on auth, page-prestador and marketplace specs); unit 158 passed; backend 754 passed, 3 skipped; lint clean.
- L6 (2026-11-07): parent verification on the combined tree after T3: backend 766 passed, 3 skipped; unit 158 passed; lint clean; Playwright 388 passed. Open limits: `backend/.env.example` lacks `REQUEST_IMAGES_BUCKET` because permissions deny access to it; the limit of 5 images is not proven under concurrency because SQLite ignores `FOR UPDATE`. Operator step: private bucket `request-images` and `REQUEST_IMAGES_BUCKET=request-images`.
- L7 (2026-11-07): independent verifier on 2791fe4: S7 images FAIL on one blocker, all backend requirements PASS, including the limit of 5 on real PostgreSQL 17 (12 runs of 12 to 20 parallel uploads) and backend 769 passed with PostgreSQL. Advisories left for the user: request row lock held during the storage upload (a provider accept returned 500 with a simulated 7 s upload); signature-only image check accepts polyglots; uploads allowed on accepted or rejected requests; no ORDER BY on image read; body spooled before 401; `REQUEST_IMAGES_BUCKET` missing from `render.yaml`.
- L8 (2026-11-07): T5 Codex gpt-6.1-sol native review, lineage review-d109541af1f59814, consent granted by the user: correction_required with one blocker, R4-storage-lock (row lock held during the storage upload). Plan captured with 200 lines. Worker-3 fixed it with RED observed: upload now runs with no lock or open transaction, then ownership and the limit are revalidated under the row lock, and the object is deleted on refusal. 79 changed lines; backend 768 passed, 3 skipped.
