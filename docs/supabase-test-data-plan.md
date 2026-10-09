# Supabase test-data plan

Populate application tables with coherent, synthetic test scenarios without creating customer users. All seeded trip and stop schedule dates must fall within **2027**. This document is a plan only: it does not authorize a remote connection or data insertion.

## Scope and safeguards

- The local schema review identified 29 application tables. Confirm the deployed inventory before preparing the seed; exclude Supabase-managed schemas and migration bookkeeping from synthetic data insertion.
- Do not create customer accounts in either `Usuario` or Supabase Auth. Reuse an explicitly approved, existing test customer without modifying its account.
- If no approved test customer exists, customer-dependent scenarios remain blocked. Do not fabricate customer identities or silently omit dependent tables.
- Prefer a development/staging project. Confirm the destination, permitted operations, and credential/session to use before accessing it. Never request secrets in chat.
- Preserve existing data, schema, RLS policies, and grants. Do not trigger real payments, payouts, identity verification, emails, or usable authentication flows.

## Trip dates: 2027 only

- Set every seeded trip departure/arrival and stop pickup/delivery schedule within January 1–December 31, 2027, in the scenario's explicitly selected timezone.
- Use fixed, timezone-aware timestamps, not relative expressions such as “today plus 30 days.”
- Preserve chronological order across departure, stops, and arrival. Avoid year-boundary timezone conversions that move timestamps outside 2027.
- Keep related request, quotation, service, and payment scenario timestamps consistent with the trip timeline.
- Do not misrepresent future trips as already completed in live behavior. Historical/completed scenarios require an isolated test environment with a controlled clock; otherwise report the coverage limitation.

## Execution checklist

### 1. Authorize and inspect the connection

- [ ] Confirm project, environment, allowed operations, and approved connection/session.
- [ ] Connect read-only initially and compare deployed tables/migrations with the repository.
- [ ] Inspect foreign keys, required fields, uniqueness/check constraints, triggers, and external side effects.
- [ ] Confirm the existing test customer and the permitted provider/account setup.

The backend accesses application tables through PostgreSQL; frontend Supabase Auth access does not substitute for this connection. Select an authorized administrative connection suitable for controlled seeding rather than assuming the Data API exposes these tables.

### 2. Define scenarios and per-table coverage

Prepare a coverage matrix for every deployed application table, recording planned row counts, dependencies, and whether records will be inserted, reused, or blocked.

| Scenario group | Coverage |
| --- | --- |
| Catalogs and providers | Roles, driver types, service types, provider profiles, drivers, vehicles, and available services |
| Trips | Trips, vehicle assignments, and ordered stops, with all schedules in 2027 |
| Customer interactions | Requests, request images, quotations, chats, participants, messages, and services linked to the approved existing customer |
| Financial and post-service records | Synthetic payments, payout accounts, payouts, claims, refunds, and ratings with coherent relationships and states |
| Identity and onboarding | Inert identity-verification, invitation, fallback-challenge, and invitation-attempt fixtures, without real delivery or reusable credentials |

Sensitive or ephemeral records require verified isolation from integrations and background jobs before insertion. If safe coverage is not possible, report the affected tables and obtain a decision rather than silently excluding them.

### 3. Prepare a repeatable, reversible seed

- [ ] Use clearly fictitious data, deterministic IDs, collision checks, and an exact manifest of inserted records.
- [ ] Reuse existing catalog values where appropriate without overwriting unrelated rows.
- [ ] Insert in dependency order and define cleanup in reverse dependency order.
- [ ] Make repeat execution safe without duplicating or altering unrelated data.
- [ ] Keep provider references, media references, and identity data synthetic; do not use real financial or identity documents.
- [ ] Do not reuse the existing local-only company fixture directly against Supabase.

### 4. Validate before committing data

- [ ] Trial the seed in a transaction that rolls back, after checking that execution cannot produce external side effects.
- [ ] Check row counts, foreign keys, business-state consistency, and cross-record ownership.
- [ ] Verify every trip/stop schedule is in 2027 and chronological ordering is valid.
- [ ] Verify no customer users were created or existing customer accounts modified.
- [ ] Verify a second run is idempotent and cleanup affects only seed-owned rows.

A database rollback cannot undo external messages or financial operations. Foreign keys alone do not prove business invariants.

### 5. Apply only after approval and report evidence

- [ ] Obtain explicit authorization for the final remote data load.
- [ ] Execute the validated load and run post-insertion checks.
- [ ] Deliver per-table inserted/reused counts, blocked or skipped coverage, verification results, and exact cleanup instructions.

## Local references

- `backend/src/amira_api/models.py`: application entities and relationships.
- `backend/alembic/versions/`: schema migrations, RLS changes, and existing demo seeds.
- `backend/README.md`: connection architecture and business invariants.
- `backend/tests/fixtures/company_profile_demo.sql`: local-only fixture; not a Supabase seed.

## Next step

Confirm the target environment and approved connection, then identify an existing test customer that may be reused. No database execution has been performed as part of this plan.
