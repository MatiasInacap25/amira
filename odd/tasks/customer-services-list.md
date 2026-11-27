# Customer Services List and Rating in Detail

Objective: the customer's service history (`/cuenta/servicios`, customer view) lists each service with date, time, origin and destination, and rating moves from the list to the service detail page (`/cuenta/servicios/[serviceId]`).
Branch: `feat/customer-services-list` from `develop`. Shared tree, parent owns git: workers do NOT commit, push, switch branches, run repo-wide formatters or installs. Runners: backend `uv run pytest`; frontend `npm run lint`, `npx tsc --noEmit`, `node --test tests/unit/*.mjs`, `npm run build`, `npx playwright test`.

## Specs

### S1. List API (backend)
- `CustomerServiceItem` (`backend/src/amira_api/customer_schemas.py`, built in `customer_routes.py` / `service_views.py`) gains `scheduled_at` (datetime | None: the requested date and time of the service, from the request form `FormularioServicio.requested_at`), `origin` (str | None) and `destination` (str | None) — the customer's own request origin/destination (the customer may see their own addresses; keep commune names if that is what the form stores). Existing fields stay; `rating` stays in the list response for backwards compatibility.
- The service detail response for the customer (`GET /api/customer/services/{serviceId}`, `ServiceDetail`) gains `rating` (same shape as `CustomerServiceRating`, null when not rated; always null for the provider viewer) so the detail page can show the existing rating without another call.
- Rating creation endpoint is unchanged.
- Tests: list item includes the three new fields (and null when missing); customer detail includes `rating` after rating and null before; provider detail has `rating` null. Update tests that compare whole dicts (`test_customer_routes.py:140-148` and any ServiceDetail dict comparisons).

### S2. List UI (frontend)
- `components/marketplace/customer-services-view.tsx`: each row shows the service type, provider name, status badge, **date and time** (format `dd-mm-aaaa · HH:mm` in America/Santiago, "Fecha por confirmar" when null), and **origin → destination** ("Sin dirección" when missing). The whole row is a link to `/cuenta/servicios/{serviceId}` with an accessible name that includes the service type and date.
- **Remove the rating form and rating display from the list.** Replace the intro text "Valora los servicios completados. Tu valoración aparece en el perfil del prestador." with "Revisa tus servicios. Entra a un servicio completado para valorarlo." A completed service without rating shows a small chip "Pendiente de valorar"; a rated one shows "Valorado".

### S3. Rating in the detail page (frontend)
- In the customer's service detail (`components/marketplace/service-detail-view.tsx` / `service-detail.tsx`, route `/cuenta/servicios/[serviceId]`), add a "Valora este servicio" section, only for the customer and only when the service status is `completed`:
  - Not rated → the existing rating form (stars 1–5 + optional comment), reusing the current validation (`lib/customer-rating-validation.ts`), error mapping (`lib/customer-rating-errors.ts`) and `createCustomerServiceRating`. Move the existing `ServiceRatingRow`/`RatingForm`/`StarDisplay` code into a reusable component (e.g. `components/marketplace/service-rating.tsx`) instead of duplicating it.
  - Already rated → show the stars and comment read-only ("Tu valoración").
  - After a successful rating, the section switches to the read-only view without a full page reload, and the same success notice as today is shown.
- Providers and non-completed services do not see the section.
- Playwright: list shows date/time and origin → destination and no rating form; clicking a row opens the detail; a completed unrated service shows the form in the detail and rating it shows "Tu valoración"; a provider detail has no rating section. Update existing rating tests (they currently rate from the list) to rate from the detail.

## Log

- L1 (2026-11-27, user): "por mientras quiero que cambies en la vista del cliente que en /servicios aparezcan la lista con los servicios con fecha, hora, origen, destino y que al entrar en la pagina de ese servicio ahi dentro donde sale toda la informacion detallada, ahi puedan valorar el servicio, no en la pagina de /servicios donde estan todo msu historial de servicios"
- L2: The customer's history lives at `/cuenta/servicios` (customer-services-view.tsx); `/servicios` is the public catalog, so the change applies to `/cuenta/servicios`.
