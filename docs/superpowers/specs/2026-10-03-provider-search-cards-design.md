# Provider-Level Service Search Cards — Design

## Goal
Make `/servicios` return and render one result per distinct active provider profile, while letting customers request a quote for an actual matching offered service.

## Approved behavior
- `GET /api/services` returns one item per active public provider profile matching the current general text, category, and location filters. The total and offset/limit pagination count and page provider profiles, not joined service rows.
- Each item carries the allowlisted provider data already needed by the page plus the IDs and display names of that provider’s matching offered services. Search results remain public-only; private profile data is not added. Real provider first and last names remain visible where currently used.
- `/servicios` displays one card per provider profile and exactly two primary actions: `Ver perfil` and `Cotizar`. `Ver perfil` opens the public provider profile. `Cotizar` opens the existing quote dialog scoped to the services returned for that card. One service is preselected; several matching services can be selected from that restricted set.
- Category filtering is a native select/list of allowed categories, not free-typed input. The independent general “Buscar por servicio o prestador” text search remains intact. The current page already uses a native `<select>` for category, so implementation preserves it and adds regression coverage for its allowed options.

## Design decisions
- Provider identity is the result entity; offered services are nested offerings. This makes pagination stable when a profile offers multiple services and avoids duplicate provider cards.
- The API returns matching service IDs and names so a quote submission targets a real offering and the customer cannot choose an unrelated service from the full profile.
- The existing quote modal is reused, with its service choices narrowed to the card’s matching offerings. No new quote workflow or backend mutation is introduced.
- Existing active-only visibility and DTO allowlisting remain unchanged; no production Supabase or hosted service calls are part of this work.

## Verification
Strict TDD is required for this task by explicit user preference: source changes follow RED → GREEN → REFACTOR. Backend runner: `uv run pytest`; frontend runner: `npm run test:e2e` from `frontend`. Also run applicable backend and frontend full checks, `graphify update .`, and `git diff --check` before completion.
