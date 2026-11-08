# Seguimiento del conductor

Objective: when the driver starts a service, they must share their location so the customer can follow it on a map until delivery.
Branch: feat/seguimiento-conductor (from main 5e40b42). Delivery strategy: ask-on-risk; chained PRs through develop if over budget. Test runners: `uv run pytest` (backend), `node --test tests/unit/*.mjs` and Playwright (frontend).

## Specs

- S1: "cuando el conductor inicia el servicio debe compartir su ubicacion para que el cliente pueda seguir la ruta". Approved rules:
  - Starting a service requires the driver's location: if the browser permission is denied, the service does not start and the driver sees how to enable it ("No puede iniciar").
  - While the service is `in_progress`, the driver's browser sends its position periodically; the customer of that service sees only the current position and the time of the last update ("Solo posición actual"), no trail.
  - When the service is completed, location updates stop and the stored position is deleted ("Se borra (Recomendado)").
  - The customer sees an embedded map, Leaflet with OpenStreetMap tiles and its attribution ("Mapa en la página").
- Assumptions, not confirmed by the user: the provider who owns the service may also see the position; positions are sent about every 15 seconds and the customer page refreshes about every 15 seconds; tracking works only while the driver keeps the service page open in the browser (a web app cannot track in the background).

## Tasks

- [x] T1, S1 backend, delegated (herdr worker-11). Migration RED observed (5 failed); the actions file RED was an ImportError, not per assertion. Backend 857 passed. Surface extended by the parent to `backend/tests/test_public_db.py` (table count 33). Accuracy capped at 100000 m (worker choice). Endpoints: POST start with {latitude, longitude, accuracy?}; PUT, GET `/api/provider/services/{id}/location`; GET `/api/customer/services/{id}/location`. Original line: new table for the current service location (migration), start requires a location, driver position updates, customer and provider read, delete on completion. High risk: migration, permissions and personal data.
- [x] T2, S1 frontend, delegated (after T1, herdr worker-12). leaflet 1.9.4, react-leaflet 5.0.0, @types/leaflet 1.9.22, pinned exactly. RED observed (unit module missing; 6 Playwright tests). Service detail spec 33 of 33, unit 167, lint and build clean. next.config.ts has no CSP. Location errors are shown from service-detail-view.tsx because the start button lives in service-actions.tsx. Original line: add leaflet and react-leaflet, driver permission flow on start and periodic updates, customer map.
- [ ] T3, delegated: independent verification and Codex gpt-6.1-sol native gentle-ai review.

Route evidence: sequential herdr workers per the project orchestrator rule; T2 depends on T1's contract. The parent owns git. Outward step needing user authorization: applying the migration to the Supabase database.

## Log

- L1 (2026-11-07), user's request: "falto eso, cuando el conductor inicia el servicio debe compartir su ubicacion para que el cliente pueda seguir la ruta". Answers: permission denied "No puede iniciar"; customer view "Solo posición actual"; on completion "Se borra (Recomendado)"; display "Mapa en la página".
- L2: today the start endpoint (`provider_service_routes.py:332`) takes no coordinates, the frontend has no geolocation, and `Ubicacion` columns are free text, not GPS. `PROJECT_OVERVIEW.md` does not mention tracking.
- L3 (2026-11-07): parent full suite on 6fe0b40: backend 857 passed, 3 skipped; unit 167; lint clean; Playwright 421 passed. Independent verifier: S1 PASS by every rule, no blockers; migration up, down and up on real PostgreSQL 17 with RLS and anon/authenticated denied. Advisories: NaN or Infinity in the body returns 500 (baseline FastAPI behavior); numeric strings and booleans are accepted as coordinates (no strict mode); the DB accuracy check lets NaN through; an owner who starts the service stores their own position until the assigned driver sends one.
