# Provider Profile Mockups and Demo Fixtures

## Objective
Create two Spanish static public-profile mockups sharing one design, implement the backend rule that adding a driver to an independent provider transitions that same profile into a company, and seed one separate synthetic company profile for demo data. The existing independent production profile remains a one-owner/one-driver sample and is not converted or mutated by the fixture seed. The separate company fixture has two synthetic `company_driver` records and two vehicles.

## Problem and rationale
The existing design reference is an authenticated, company-focused dashboard. The demo needs a public-facing, consistent profile for company and independent providers, plus clearly synthetic sample content. Existing role semantics and driver associations must remain accurate: a demo role must not satisfy the fixture requirement. Product behavior is settled: an independent provider who adds a second driver transitions the same profile to company; the added user becomes a company driver linked to that profile, never a second independent provider/profile.

## Scope and constraints
- Design reference: `C:\Users\matia\Downloads\stitch_amira_logistics_marketplace\code.html`.
- Two dependency-free static HTML mockups in Spanish: existing independent-driver profile and one new company profile. Shared public header/anchor navigation, profile identity/type/location/rating/quote CTA, services, and vehicle cards. The existing independent mockup shows its owner as the only driver. The separate company mockup shows two synthetic company drivers. Any mock-only vehicle content on the independent mockup is local sample content, not a production fixture write. Reviews may appear only when explicitly labeled synthetic.
- Profile type is a displayed field, not a separate template or authorization role.
- Fixture target: one new company profile with one synthetic company owner, two synthetic company-driver users/`Conductor` records linked to that profile, and two new vehicles. The existing independent owner is already `Usuario` + `Perfil(owner_user_id=Usuario.ID)` + `Conductor(user_id=Usuario.ID)` with `employer_profile_id=NULL`; show this owner as the profile’s one driver and do not convert or mutate that existing production profile/driver in the seed. The fixture adds three synthetic `Usuario` rows (company owner + two company drivers) and shows three driver records total across the existing independent sample and new company profile. Static mockup-only sample vehicle values do not imply inserts for the existing profile.
- Use `[DEMO]` names/content, `.invalid` emails, DEMO-only plates, deterministic IDs, and narrowly scoped/idempotent fixture keys. Never create `auth.users` rows or login credentials.
- Resolve profile roles by canonical `Rol_Perfil.code`: `independent_driver` and `company`. Never create or insert `Rol_Perfil` `[DEMO] proveedor de prueba`; preserve the user's manually corrected existing role and planned removal of that demo role row.
- Existing public provider code lists drivers through `Conductor.employer_profile_id`; independent providers have no such association. Include an independent owner through `Perfil.owner_user_id = Conductor.user_id`. Required transition behavior: owner-authorized atomic conversion of the same `Perfil` to company, upgrade the owner account capability to `company_owner`, reuse/link the owner's unique `Conductor`, and add the new `company_driver` account/`Conductor` linked through `employer_profile_id` to that same profile. Never create a second `Perfil` for the added driver. Existing code has no profile-transition or standalone `company_driver` provisioning endpoint; implement and test this backend behavior. Keep this real transition out of fixture seeding for the current production profile.
- Inspect canonical `Tipo_Conductor` values before fixture implementation. Use a deterministic synthetic type only if no suitable canonical value exists; this remains an implementation task.
- Public production fixtures will be visible. Document exact IDs and natural cleanup keys for possible future cleanup, but cleanup/deletion is not authorized.
- This documentation stage performs no app/source change or remote operation. The design spec and this ODD task document were committed as documentation in `2408c5c`. Implementation and production fixture writes remain gated on written-spec review, local tests, and narrow exact-target verification. Production seed writes are limited to the new company profile, its synthetic owner, two company-driver users/records, and two company-profile vehicles; do not convert/update the existing independent production profile or its existing owner/driver. Do not create `auth.users` rows or credentials, create/insert/reference `Rol_Perfil` `[DEMO] proveedor de prueba`, delete existing data, or broaden access.

## Authorized scope
- Documentation only: this design spec and this ODD task document.
- Design: `docs/superpowers/specs/2026-10-03-provider-profile-mockups-and-demo-fixtures-design.md`.
- Future implementation route: delegated direct; multiple non-trivial presentation/data/test files and schema relationship discovery are expected.
- The user clarified and settled the transition rule: a second driver changes the same independent profile into a company; the added account is `company_driver` and links to that existing profile. The fixture request remains distinct: leave the existing independent production profile unchanged and seed a separate company profile. The design and task artifacts were committed as documentation in `2408c5c`.

## TDD and checks
- `strict_tdd: true`; source: explicit user/project instruction; sequence RED → GREEN → REFACTOR is required for future code changes.
- Backend runner: `uv run pytest` from `backend`.
- Future focused tests: owner-authorized atomic same-profile conversion; company_owner capability and company tax data; owner Conductor reuse/linking; standalone company_driver provisioning without a second Perfil; rollback, idempotency/concurrency and authorization; public DTO behavior before/after transition; fixture isolation/idempotency; canonical role mapping/no demo role; privacy.
- Future full checks: `uv run pytest` from `backend`, static HTML structure/responsive/offline review, `graphify update .`, and `git diff --check` after source changes.
- This documentation-only task is checked by reading both artifacts back and `git diff --check`; no tests/builds or database access are needed.

## Forecast and delivery
- Forecast: approximately 600 authored changed lines (rough) across the company-transition/provisioning behavior, public DTO, tests, two mockups, and a separate company fixture. Refresh after the transition API contract is mapped; the estimate is a planning heuristic, not a cap or reason to omit tests.
- Delivery strategy: `ask-on-risk`; no prior current-session cached delivery choice was observed. If the forecast/running count exceeds about 400 authored changed lines, ask once for the chain strategy before the next commit; do not split work solely to satisfy the heuristic.
- Production fixture application remains gated by written-spec review, local test success, and exact-target verification. It seeds only the new company fixture and must not convert or mutate the existing independent production profile/owner-driver. Cleanup/deletion remains unauthorized.

## Tasks
- [ ] PPM-1 — Add failing tests for owner-authorized atomic independent-to-company transition, owner capability and Conductor reuse, linked company_driver provisioning, rollback/idempotency/concurrency, and before/after public DTO semantics.
- [ ] PPM-2 — Implement transition and company_driver provisioning as one authorized, atomic backend capability: retain the same Perfil/owner; change profile/account role; reuse and link the existing owner Conductor; create/link the new company_driver without a Perfil; update public API and tests.
- [ ] PPM-3 — Build two static Spanish mockups with one shared public profile design: the current independent profile with its owner as sole driver, and a separate company profile with two demo company drivers.
- [ ] PPM-4 — Add a narrowly scoped, idempotent seed for only the new company profile, synthetic owner, two company-driver records, and two vehicles; prove the existing independent profile and owner-driver are unchanged. Record fixture IDs and cleanup keys.
- [ ] PPM-5 — Review static mockups and public payloads, run `graphify update .` and applicable final checks; record implementation commit identities when authorized.

## Acceptance criteria
- Exactly two mockups represent the existing independent-driver profile and a new company profile with the same public layout; type is a field only.
- Both show public navigation, profile identity/type/location/rating/quote CTA, services, and vehicle cards. The independent mockup shows its owner as sole driver; the separate company mockup shows two synthetic company drivers. Any sample vehicles/reviews on the independent static mockup are clearly mock-only.
- The fixture creates one separate company profile, one synthetic company owner, two synthetic `company_driver` users/driver records linked to that profile, and two company-profile vehicles, with no Auth users or usable credentials. The existing independent production profile remains one owner/one driver and is not mutated by the seed.
- Both profiles use canonical profile role codes. No fixture operation refers to or inserts `Rol_Perfil` `[DEMO] proveedor de prueba`.
- Driver associations are accurate: independent owner is included through `Perfil.owner_user_id = Conductor.user_id`. For the real transition flow, the same profile becomes company; owner remains owner, gains `company_owner` capability, and their existing unique Conductor is reused/linked; the added account is `company_driver` and its Conductor links to that same profile, with no second Perfil. In the fixture seed, the existing independent profile and owner-driver are unchanged; both separate company fixture drivers are employer-linked.
- Fixture setup is idempotent and narrowly guarded; conflicting non-fixture rows cause a safe failure. Public fields exclude email, phone, RUT, auth ID, plate, storage key, and other private data.
- No production query/write, migration application, or deletion occurs during this documentation stage. Production fixture writes remain gated by written-spec review, local tests, and narrow exact-target verification; they are limited to the separate new company fixture and must not convert or mutate the existing independent profile/owner-driver. No Auth users, forbidden demo role, or cleanup/deletion. Public visibility and future cleanup identifiers are documented.

## Progress and evidence
- 2026-10-03: Read the existing auth/public-profile design, provider-demo task, public provider route/schema, profile/driver/vehicle models, and prior public fixture migration. The public API's driver query is employer-profile-only; include an independent owner by joining `Perfil.owner_user_id` to `Conductor.user_id`.
- 2026-10-03: Existing role codes include canonical `company` and `independent_driver`; the initial fixture migration contains the legacy `[DEMO] proveedor de prueba` role, but the new design explicitly forbids referencing/recreating it. `Conductor.driver_type_id` is required; inspect canonical driver types and add a deterministic synthetic type only if necessary.
- 2026-10-03: Static mockup ratings/reviews are mock-only; the current live public provider DTO has no rating/review data. Production writes remain gated by written-spec review, local tests, and narrow exact-target verification.
- 2026-10-03: Read-only account-role audit confirmed current provision flow rejects role changes, creates a Perfil for `independent_driver`, and lacks standalone `company_driver` provisioning. The clarified product behavior therefore needs an explicit owner-authorized atomic transition; its fixture seed remains separate and leaves the existing independent profile unchanged.
- 2026-10-03: Design spec written at `docs/superpowers/specs/2026-10-03-provider-profile-mockups-and-demo-fixtures-design.md`. No code, database, or production changes made.
- 2026-10-03: Committed the design and task artifacts in `2408c5c` (`docs: design provider profile mockups and fixtures`). The written spec still awaits user review; this commit does not authorize source or database work before the remaining gates.
- 2026-10-03: Updated the design for the user's one-owner/company-driver transition rule and committed it in `d331b7f` (`docs: specify provider company transition`). The written spec is ready for review; implementation and fixture writes have not started.

## Progress
- [x] Design spec and task document created and read back.
- [ ] Implementation/production fixture writes remain gated on written-spec review, local tests, and exact-target verification; the fixture must not convert or mutate the existing independent profile.

## Next step
Have the user review the written spec. Then implement and test the owner-authorized atomic transition: keep the same Perfil/owner; switch profile kind/role and owner account capability to company/company_owner; reuse and link the owner’s existing unique Conductor; add the new account as company_driver linked to that same Perfil; create no second Perfil. Keep the production demo seed separate: one-owner/one-driver existing independent profile unchanged, plus a new company profile with two synthetic company drivers. Preserve canonical profile-role codes and never recreate the legacy demo profile role. Apply seed only after local tests and exact-target verification; no auth.users or real credentials.

## Relevant files
- `docs/superpowers/specs/2026-10-03-provider-profile-mockups-and-demo-fixtures-design.md` — implementation design and safety contract.
- `backend/src/amira_api/public_routes.py` — public profile query currently lists drivers only via employer profile.
- `backend/src/amira_api/public_schemas.py` — public provider response allowlist.
- `backend/src/amira_api/models.py` — canonical profile/account roles, driver, and vehicle schema.
- `backend/alembic/versions/20260927_0002_public_browse_rls_and_demo_seed.py` — historical demo seed with legacy demo role; do not replicate that role pattern.

## Implementation authorization and clarified service roles

The user explicitly approved implementation after reviewing the design and clarified these required runtime boundaries:

- The existing profile owner is the only client-facing account: the owner talks with customers, schedules services, and chooses which linked driver performs each service.
- A linked `company_driver` only performs services assigned by the owner. Profile membership must not grant chat participation, scheduling, or customer messaging permissions.
- Driver assignments must be validated against the same company profile; never allow the owner to assign a driver belonging to another profile.
- The transition remains same-profile: preserve `Perfil.ID` and owner; change the profile to canonical `company`, owner capability to `company_owner`, reuse/link the owner's unique `Conductor`, and create the added user as `company_driver` with no second `Perfil`.
- Keep the synthetic company fixture distinct from the real transition and do not mutate the existing independent profile. This request does not authorize applying migrations or fixture data to Supabase/production; do not perform remote DB operations.

Authorized route is delegated direct because implementation spans non-trivial backend, frontend/mockup, fixture, and test files. Preserve strict TDD (`uv run pytest` in `backend`), run `graphify update .` after source edits, and do not stage unrelated existing working-tree changes.

Implementation tasks:
- [x] Implement the owner-authorized atomic same-profile transition: owner capability/profile role upgrade, owner Conductor reuse/link, and linked company-driver account provisioning without a second profile.
- [x] Enforce owner-only request decisions/chat participation and driver assignment; reject cross-profile drivers and keep public payloads allowlisted.
- [x] Complete both dependency-free Spanish mockups and the isolated local-only company SQL fixture; do not add it to Alembic or apply it.
- [x] Run final checks, update the graph, record fixture IDs and work-unit commit identity.

## Implementation progress (2026-10-03)

- Added `POST /api/account/company/transition`. It locks and validates the authenticated owner, existing profile, owner driver, and invited existing client account; changes the existing owner/profile in place; links the owner's unique Conductor; and upgrades the linked client to `company_driver` with a same-profile Conductor. It creates no profile for the driver. Company profile/account role codes are resolved canonically; invalid configuration and mismatched/conflicting state fail closed.
- Added `PUT /api/provider/services/{service_id}/driver`. Only the profile owner can use it; the service must belong to that profile and the selected driver must be a linked `company_driver` or the authenticated owner. Cross-profile IDs are hidden as not found. Provider inbox decisions keep the company owner as the only provider chat participant; `company_driver` remains ineligible for provider/client quote actions.
- Public driver listing now includes an independent profile owner's existing Conductor through the owner-user association as well as employer-linked company drivers. Public response schemas remain explicit and exclude account/private fields.
- Added `docs/mockups/public-provider-independent.html` and `docs/mockups/public-provider-company.html`, which share the same responsive, offline Spanish layout; mock rating and vehicle data are clearly labeled as illustrative.
- Added `backend/tests/fixtures/company_profile_demo.sql` as a local-test-only, standalone fixture (not an Alembic migration and not applied). The repository has no canonical driver-type seed; this isolated fixture inserts the deterministic synthetic type only for the local test dataset. It resolves canonical `company_owner`, `company_driver`, and `company` roles and fails on conflicting fixture IDs; no existing independent profile is referenced or updated.

Fixture UUIDs and natural cleanup keys (cleanup is not authorized):
- Company profile `b3000000-0000-4000-8000-000000000002` — `[DEMO] Logística del Valle`.
- Owner user `b3000000-0000-4000-8000-000000000001` — `demo-compania@example.invalid`; synthetic auth UUID `b3000000-0000-4000-8000-00000000000a` is an application field only, not an `auth.users` row.
- Driver user `b3000000-0000-4000-8000-000000000003` — `demo-mateo@example.invalid`; synthetic auth UUID `b3000000-0000-4000-8000-00000000000b`. Driver record `b3000000-0000-4000-8000-000000000005` links to profile `b3000000-0000-4000-8000-000000000002`.
- Driver user `b3000000-0000-4000-8000-000000000004` — `demo-lucia@example.invalid`; synthetic auth UUID `b3000000-0000-4000-8000-00000000000c`. Driver record `b3000000-0000-4000-8000-000000000006` links to profile `b3000000-0000-4000-8000-000000000002`.
- Vehicle `b3000000-0000-4000-8000-000000000007` — plate `DEMO-001`; vehicle `b3000000-0000-4000-8000-000000000008` — plate `DEMO-002`. Both link to profile `b3000000-0000-4000-8000-000000000002`.
- Local synthetic driver-type lookup `b3000000-0000-4000-8000-000000000009` — `[DEMO] Conductor de empresa`.
- The company's `DEMO-76000000` tax marker is deliberately synthetic and never included in a public DTO.


Work-unit commits on `feature/auth-and-public-provider-profiles`:
- `34c70e1` — `feat: transition independent providers into companies`.
- `860ffcc` — `feat: enforce owner-managed service assignments`.
- `09cf3a1` — `docs: add provider profile mockups and local fixture`.

Focused RED/GREEN evidence: `uv run pytest tests/test_company_transition.py tests/test_company_demo_fixture.py tests/test_provider_mockups.py tests/test_public_provider_routes.py tests/test_provider_request_routes.py -q` — 36 passed, including owner-only chat/assignment, foreign-driver rejection, transition retry and commit-rollback tests. Full suite `uv run pytest -q` from `backend` — 102 passed. `graphify update .` succeeded (SQL AST plugin unavailable; SQL fixture not represented in graph); `git diff --check` succeeded. Pytest emitted a cache-write permission warning for the pre-existing `.pytest_cache`. Earlier RED for assignment failed with route-not-found as expected. No database was connected, no migration/fixture was run, and no remote or Auth operation occurred.

## Verification correction follow-up (2026-10-03)

The independent read-only verifier identified two confirmed in-scope blockers in the committed implementation. Reopen only these bounded corrections:

- [x] Require an owner-driver assignment candidate to be either an independent owner's unlinked `Conductor` (`employer_profile_id IS NULL`) or a conductor linked to the same profile; add a regression test for a foreign-linked owner driver.
- [x] Make the local fixture's nullable-column identity guards null-safe with `IS DISTINCT FROM` (or equivalent), and add a regression test for a NULL-valued conflicting row.

Strict TDD evidence: the first focused run failed on both regressions (the assignment endpoint accepted the foreign-linked owner driver's canned result with HTTP 200; the fixture had no null-safe comparisons). After correction, the focused command `uv run pytest tests/test_public_provider_routes.py::test_company_owner_cannot_assign_their_driver_record_when_it_is_linked_to_another_profile tests/test_company_demo_fixture.py::test_nullable_fixture_identity_fields_detect_null_collisions -q` passed (2 passed). Full `uv run pytest` from `backend` passed (104 passed). `graphify update .` succeeded; its SQL extraction plugin is unavailable, so SQL did not contribute to the graph. `git diff --check` passed. Pytest emitted only the existing `.pytest_cache` permission warning. No database was connected and the fixture was not executed. A separate product/security question about unilateral promotion by UUID remains intentionally unresolved for the parent to ask the user.

## Security finding — direct driver promotion must be removed

The independent verifier found that `POST /api/account/company/transition` currently lets an authenticated profile owner promote an arbitrary existing `client` account identified by UUID into `company_driver`; it does not require an invitation acceptance or other consent from that user. This endpoint is not safe for production use and its direct UUID promotion must be removed. The user has resolved the consent question below.

## Decision update — driver invitation acceptance is required

On 2026-10-04, the user confirmed that the driver must accept an owner-issued invitation before the account is linked to the company or its role changes. Do not allow an owner to promote or modify an arbitrary client account by UUID alone. The prior approved account/auth task also settles a 7-day expiry, signup-from-invitation, owner list/revoke/reissue, one-use hashed/email-bound tokens, and automatic Resend delivery as a future configured adapter; no live provider credentials or operations are authorized, so use a fake mailer in tests and do not send real email.

Add a bounded follow-up task:
- [x] PPM-6 ? Complete owner-issued, email-bound invitation acceptance: independent profiles remain independent while pending; first acceptance atomically transitions owner/profile and provisions the invited driver; subsequent accepts only add drivers. Acceptance throttling, clean-checkout router isolation, and owner RUT UI are included. Work-unit commit: `0041237`.

The direct-UUID promotion path was removed by the first PPM-6 implementation. The company transition must not leave an independent profile converted before the invitee accepts; complete that state change atomically on the first acceptance.

PPM-6 first-pass checks (2026-10-04): backend `uv run pytest` passed (115 tests); frontend `npm run lint` passed; full Playwright E2E passed (37 tests) using repository fakes and installed Chrome; isolated webpack build, graphify, and diff checks passed. Independent review found a clean-checkout import failure (`main.py` depends on an untracked `fallback_routes.py`), non-atomic independent-to-company conversion before driver acceptance, and missing rate limiting on acceptance. Thus the feature is not complete despite those test results. Fake tests verify token hashing, email normalization, expiry, wrong identity, replay, rollback, row locking, reissue and configured-delivery failure. Email confirmation uses a server-verified Auth `/user` result and fails closed without a matching confirmed identity. No live Auth/Resend request or database operation was run. Native RDD status remains parent-managed.

To preserve the approved “same profile becomes a company when the second driver joins” rule without leaving an empty company on decline/expiry, keep pending invitation metadata private and leave the owner/profile independent until a target invitee accepts. The first acceptance then atomically upgrades owner/profile, reuses the owner Conductor, and links the accepting driver. A subsequent accepted invitation only adds another company driver.

## Migration ancestry blocker — user decision required before changing history

Independent verification of clean commit `0041237` found that tracked migration `20261003_0001_activate_demo_profile_publication.py` has `down_revision = 20260928_0004`, but `20260928_0004_email_fallback_proofs.py` is untracked and absent from the commit. The new invitation-attempt migration follows `20261003_0001`, so a clean checkout cannot resolve the full Alembic history. Do not include or stage the unrelated email-fallback migration/files to hide this dependency. Because changing the parent of an already committed migration can be unsafe if it was applied to production, ask the user whether `20261003_0001` or the email-fallback migration was applied remotely before altering migration history. No remote query or migration apply has been performed in this task.


## PPM-6 correction progress (2026-10-04)

- [x] Pending invitations keep an independent owner/profile independent; the required company RUT is retained only in the private profile field and is normalized before storage.
- [x] First valid acceptance atomically upgrades that same profile and owner, reuses/links the owner Conductor, consumes the invite, and creates exactly one linked company-driver Conductor; later invites only add drivers. The direct company transition endpoint is removed.
- [x] Acceptance attempts are rate-limited by authenticated user/session using a server-private, RLS-protected attempt table; no token or email is stored in attempt rows.
- [x] Owner UI collects the pending company RUT and explains that conversion occurs only after acceptance.
- [x] Backend `uv run pytest -q -p no:cacheprovider`: 119 passed; frontend lint passed; Playwright E2E: 37/37 with the preinstalled Chrome binary; isolated Next webpack production build passed; `graphify update .` and `git diff --check` passed.
- [x] Clean-checkout archive import and full backend suite verified after the correction commit: `uv run pytest -q -p no:cacheprovider` ? 119 passed.

## PPM-7 — Repair clean migration ancestry (2026-10-04)

User reports that none of the migrations under discussion have been applied. This is user-provided deployment status, not a remote verification. Local history repair is authorized as continuation; applying or inspecting Supabase is not.

- [ ] PPM-7: Inspect tracked migration dependencies, reproduce the missing ancestor with a regression test, repair only the tracked local chain, and verify clean Alembic history/offline SQL plus the backend suite. Preserve the unrelated untracked email-fallback migration and all dirty auth overlays. Commit only this bounded fix and its regression.
- Route: delegated direct; preparation for a write and migration/test analysis require a bounded worker. Strict TDD: RED → GREEN → REFACTOR, `uv run pytest` from `backend`.
- Acceptance: committed migrations resolve without untracked files, a single committed head is present, and no live database or remote operation occurs.
- Native review ownership blocker remains unavailable; require writer self-checks, independent verification, and parent spot-check.
- PPM-6 implementation checks remain valid, but release readiness is pending PPM-7. Next step: repair and validate the clean committed migration chain.

## PPM-7 verified closure (2026-10-04)

- [x] PPM-7 completed in `bea1be3` (`fix: restore tracked Alembic migration ancestry`): publication migration now follows tracked `20260928_0003`, which introduces its required `Perfil.public_activated_at` column. The unrelated untracked fallback migration was not included or edited.
- Strict TDD: tracked-only regression failed with missing parent `20260928_0004` before repair, then passed. Writer full backend suite: 120 passed. Parent spot-check `uv run pytest tests/test_tracked_migration_graph.py -q -p no:cacheprovider`: 1 passed.
- Independent verifier: PASS for local repair. Isolated clean archive of `bea1be3` resolves five revisions and one head `20261003_0002`; offline SQL generated all five upgrades with a dummy localhost URL and a guard against database connection. Full backend: 120 passed, existing pytest-cache permission warning only. Graphify and diff checks passed.
- Important remaining local state: dirty migration directory still has TWO heads (`20260928_0004` and `20261003_0002`) because the unrelated fallback migration remains untracked. Do not use bare `alembic upgrade head` on that directory until the fallback work is deliberately integrated. The regression reads tracked worktree files; independent archive verification provides proof for committed bytes.
- Native RDD assessment is unassessable/high due untracked inventory; preflight safely refused before mutation due Git authority directory ownership. No receipt claimed; writer checks, fresh independent verification, and parent spot-check are recorded instead. No ownership/settings changes made.
- No Supabase, Auth, email-provider or database connection/application occurred. No fixtures applied. Deployment and deliberate fallback migration integration remain pending, outside this local repair. Dirty task documentation and unrelated auth overlays remain unstaged.
