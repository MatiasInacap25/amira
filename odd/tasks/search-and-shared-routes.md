# Search and Shared Routes

## Goal and authorization
Create the 26-table Amira schema in Supabase project xzjnsacaewlzzudawllt, insert isolated demonstration records, and implement service search and shared-route pages using the backend API. User explicitly approved remote schema creation after confirming public is empty.

## Tasks
- [x] T1: Backend migration safety check, RLS default-deny and schema application. Independent offline SQL inspection then atomic upgrade through 20260927_0002. 26 application tables plus Alembic history have RLS, no anon/authenticated SELECT grants.
- [x] T2: Idempotent labeled seed and whitelisted public read APIs. 18 backend tests passed. Real database ASGI reads returned 2 services and 1 shared route. No real Auth users or payment records seeded.
- [x] T3: `/servicios` and `/rutas-compartidas`, filters, API integration, loading/error/empty states and landing navigation. 15 mocked Playwright tests passed; types, ESLint and isolated Webpack build passed.
- [ ] T4: Independent integration verification and progress reconciliation.

## Constraints
Workers own disjoint frontend/backend directories. No real identities, verified badges, bank details, payments or booking mutations. No sensitive columns in public DTOs. Enable RLS for exposed tables, no broad anonymous grants. Preserve real records; seed only explicitly labeled fixtures. Secrets remain local ignored environment files. No destructive schema reset or deployment.

## Checks and delivery
Strict TDD is not established; observed functional tests required. No Git repository exists, so commits/native Git review unavailable. No push or PR authorized. Authored lines likely exceed400 but no commit boundary exists; task split follows coherent backend/frontend units rather than size-only edits.

## Evidence and next step
Exploration confirmed no public tables or Supabase migration history before application. Independent review caught mixed-timezone filter error (fixed, regression tested) and private stop address exposure (removed from DTO).

Final live-browser integration is pending: execution helper failed process setup for both independent verifier and parent, preventing local backend launch. Frontend preview was left on localhost3000 by worker but is not freshly checked. Backend live DB reads were verified through ASGI, not a browser. Graphify failed UV trampoline path canonicalization. Existing public.rls_auto_enable SECURITY DEFINER advisor warning was not created or modified by this work and needs separate review. No commits: workspace not Git.
