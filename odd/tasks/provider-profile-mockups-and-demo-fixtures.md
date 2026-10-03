# Provider Profile Mockups and Demo Fixtures

## Objective
Create two Spanish static public-profile mockups (existing independent driver and a new company) sharing one design, and plan narrowly scoped synthetic fixture data with two visible drivers and two vehicles per profile.

## Problem and rationale
The existing design reference is an authenticated, company-focused dashboard. The demo needs a public-facing, consistent profile for company and independent providers, plus enough clearly synthetic sample content to demonstrate the same sections for each. Existing role semantics and driver associations must remain accurate: a demo role must not be used to satisfy the fixture requirement.

## Scope and constraints
- Design reference: `C:\Users\matia\Downloads\stitch_amira_logistics_marketplace\code.html`.
- Two dependency-free static HTML mockups in Spanish: existing independent-driver profile and one new company profile. Shared public header/anchor navigation, profile identity/type/location/rating/quote CTA, services, drivers, and vehicles. Reviews may appear only when explicitly labeled synthetic.
- Profile type is a displayed field, not a separate template or authorization role.
- Fixture target: existing independent-driver profile plus one new company profile; two synthetic driver users and two synthetic vehicles each (4 drivers and 4 vehicles total).
- Use `[DEMO]` names/content, `.invalid` emails, DEMO-only plates, deterministic IDs, and narrowly scoped/idempotent fixture keys. Never create `auth.users` rows or login credentials.
- Resolve profile roles by canonical `Rol_Perfil.code`: `independent_driver` and `company`. Never create or insert `Rol_Perfil` `[DEMO] proveedor de prueba`; preserve the user's manually corrected existing role and planned removal of that demo role row.
- Existing public provider code lists drivers through `Conductor.employer_profile_id`; independent drivers have no such profile association today. Do not misuse the employer field or company role: implementation must add the smallest explicit roster relationship required for the approved visible-driver count and test it.
- Inspect canonical `Tipo_Conductor` values before fixture implementation. Use a deterministic synthetic type only if no suitable canonical value exists; this remains an implementation task.
- Public production fixtures will be visible. Document exact IDs and natural cleanup keys for possible future cleanup, but cleanup/deletion is not authorized.
- This documentation stage performs no app/source change or remote operation. The design spec and this ODD task document are to be committed as documentation before implementation; no such commit has been made yet. Implementation and production seed application remain gated on the user reviewing the written spec, local tests passing, and narrow exact-target verification. Production writes are limited to the synthetic fixtures, the current independent-driver profile, and two synthetic driver users plus two vehicles per profile; do not create `auth.users` or credentials, create/insert/reference `Rol_Perfil` `[DEMO] proveedor de prueba`, delete existing data, or broaden access.

## Authorized scope
- Documentation only: this design spec and this ODD task document.
- Design: `docs/superpowers/specs/2026-10-03-provider-profile-mockups-and-demo-fixtures-design.md`.
- Future implementation route: delegated direct; multiple non-trivial presentation/data/test files and schema relationship discovery are expected.
- The user authorized the implementation direction in the established production context, but the written-spec review, local-test, and narrow-target gates above remain mandatory. No implementation or production write occurs during this documentation stage. Commit the design and task artifacts as documentation before implementation; that commit is still pending.

## TDD and checks
- `strict_tdd: true`; source: explicit user/project instruction; sequence RED → GREEN → REFACTOR is required for future code changes.
- Backend runner: `uv run pytest` from `backend`.
- Future focused tests: canonical role mapping/no demo role, fixture scoping and idempotency, driver roster response for both kinds, and public-field privacy.
- Future full checks: `uv run pytest` from `backend`, static HTML structure/responsive/offline review, `graphify update .`, and `git diff --check` after source changes.
- This documentation-only task is checked by reading both artifacts back and `git diff --check`; no tests/builds or database access are needed.

## Forecast and delivery
- Forecast: approximately 450 authored changed lines (additions plus deletions; generated files excluded) across two static mockups, fixture/roster persistence, public DTO behavior, and regression tests. This is a planning heuristic, not a cap or reason to omit tests.
- Delivery strategy: `ask-on-risk`; no prior current-session cached delivery choice was observed. If the forecast/running count exceeds about 400 authored changed lines, ask once for the chain strategy before the next commit; do not split work solely to satisfy the heuristic.
- Production fixture application is a separate authorized implementation step, gated by design-spec review, local test success, and exact-target verification. This delivery planning does not broaden the authorized fixture rows or allow cleanup/deletion.

## Tasks
- [ ] PPM-1 — Build two static Spanish mockups with one shared public profile design and explicit demo-only content.
- [ ] PPM-2 — Implement idempotent synthetic fixtures using canonical role codes and a semantically correct independent/company driver roster relationship; record all fixture IDs and cleanup keys.
- [ ] PPM-3 — Add RED/GREEN/REFACTOR tests for role mapping, forbidden demo role, idempotency/scoping, required counts, public roster, and privacy; run backend checks.
- [ ] PPM-4 — Review static mockups and public fixture payloads, run `graphify update .` and applicable final checks; record implementation commit identities when authorized.

## Acceptance criteria
- Exactly two mockups represent the existing independent-driver profile and a new company profile with the same public layout; type is a field only.
- Both show public navigation, profile identity/type/location/rating/quote CTA, services, two drivers, and two vehicles. Reviews, if included, are visibly fake.
- The fixtures create one new company profile and 4 synthetic driver users/4 vehicles total (2 drivers and 2 vehicles associated with each target profile), with no Auth users or usable credentials.
- Both profiles use canonical profile role codes. No fixture operation refers to or inserts `Rol_Perfil` `[DEMO] proveedor de prueba`.
- Driver associations are accurate for company and independent profile semantics; independent drivers are not forced into the company-employer relationship.
- Fixture setup is idempotent and narrowly guarded; conflicting non-fixture rows cause a safe failure. Public fields exclude email, phone, RUT, auth ID, plate, storage key, and other private data.
- No production query/write, migration application, or deletion occurs during this documentation stage. Later, production seed writes are authorized only for exact synthetic fixtures, the current profile, and 2 drivers/2 vehicles per profile after design review, local tests, and narrow target verification. Public visibility and future cleanup identifiers are documented.

## Progress and evidence
- 2026-10-03: Read the existing auth/public-profile design, provider-demo task, public provider route/schema, profile/driver/vehicle models, and prior public fixture migration. The public API's driver query is employer-profile-only; independent drivers currently have `employer_profile_id = NULL`, so the requested two visible independent-profile drivers require an explicit, semantically valid association rather than a role/FK workaround.
- 2026-10-03: Existing role codes include canonical `company` and `independent_driver`; the initial fixture migration contains the legacy `[DEMO] proveedor de prueba` role, but the new design explicitly forbids referencing/recreating it. `Conductor.driver_type_id` is required; inspect canonical driver types and add a deterministic synthetic type only if necessary.
- 2026-10-03: Static mockup ratings/reviews are mock-only; the current live public provider DTO has no rating/review data. The approved production write remains gated on design-spec review, local tests, and narrow exact-target verification.
- 2026-10-03: Design spec written at `docs/superpowers/specs/2026-10-03-provider-profile-mockups-and-demo-fixtures-design.md`. No code, database, or production changes made.
- 2026-10-03: Reconciled the written-spec review gate and documentation commit requirement: direction is agreed, but the written spec still awaits user review; source/DB/Supabase work remains gated. The documentation commit has not been made.

## Progress
- [x] Design spec and task document created and read back.
- [ ] Implementation is authorized; it remains pending design-spec review, local tests, and narrow exact-target verification before production seed application.

## Next step
Have the user review the written design spec. Only after that review, begin implementation by resolving the explicit profile-to-driver roster relation in code/test context, then run local tests and verify exact production targets before any narrowly scoped fixture write. Preserve canonical role codes and never recreate the legacy demo profile role.

## Relevant files
- `docs/superpowers/specs/2026-10-03-provider-profile-mockups-and-demo-fixtures-design.md` — implementation design and safety contract.
- `backend/src/amira_api/public_routes.py` — public profile query currently lists drivers only via employer profile.
- `backend/src/amira_api/public_schemas.py` — public provider response allowlist.
- `backend/src/amira_api/models.py` — canonical profile/account roles, driver, and vehicle schema.
- `backend/alembic/versions/20260927_0002_public_browse_rls_and_demo_seed.py` — historical demo seed with legacy demo role; do not replicate that role pattern.
