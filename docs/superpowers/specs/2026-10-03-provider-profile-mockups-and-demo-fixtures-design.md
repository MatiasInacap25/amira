# Provider Profile Mockups and Demo Fixtures — Design

**Date:** 2026-10-03
**Status:** Approved for implementation; owner-only client interaction, scheduling, and driver assignment clarified.
**Scope:** Two Spanish static public provider-profile mockups, the backend behavior for transitioning an independent provider profile to a company when adding a driver, and a standalone local-test fixture for one separate synthetic company profile. The fixture is not an Alembic migration and is not applied to Supabase or production. The fixture must not convert or mutate any existing independent profile.

## Goal

Show the same public profile page design for a company and an independent driver. Profile type is a displayed field, not a different page template. Provide credible demo content for both profiles while keeping every account synthetic, clearly marked, non-login, and safe to remove later by exact identifiers.

## Approved product constraints

- Create two standalone static HTML mockups in Spanish: one for the existing independent-driver profile and one for a new company profile. Use `C:\Users\matia\Downloads\stitch_amira_logistics_marketplace\code.html` as the visual/content starting reference, adapting its company-oriented dashboard into a public profile rather than copying its authenticated navigation or private/admin affordances.
- Both mockups share one public structure and visual system. Each shows profile name, a visible profile-type field (`Empresa` or `Conductor independiente`), location, rating, and a quote CTA, followed by services, drivers, and vehicle cards. The existing independent-profile sample has one owner and that owner’s existing driver record only. The separate company-profile sample has two synthetic `company_driver` records linked to its company profile. Static mockup content must not suggest the existing independent profile has an additional driver.
- A reviews section is optional. Any rating/review content in either static mockup is mock-only, visibly labeled as sample/demo content, and must not imply real customer feedback or verified identity. The current live public DTO does not provide ratings or reviews; do not present these mock values as live data.
- Header and anchor navigation are public-facing. Do not display internal dashboard navigation, login credentials, owner controls, verification claims, or private identifiers.
- The local fixture target is one new company profile with one synthetic company owner, two synthetic company-driver users/`Conductor` records linked to that same profile, and two synthetic vehicles. It is kept under test fixtures and must never be an automatically applied production seed. Use visibly fake `[DEMO]` names, `.invalid` email addresses, and `DEMO`-only plate values. Do not create any `auth.users` rows or login credentials. Static mockups may use clearly labeled sample vehicle details for the independent profile without writing those records to a database.
- Never create, reference, or assign `Rol_Perfil` `[DEMO] proveedor de prueba`. Both profiles must use the canonical profile role selected by `Rol_Perfil.code`: `independent_driver` for the existing independent profile and `company` for the new company. The user reports that the existing profile role was manually corrected and plans to delete the demo-role row; preserve that state and do not rebuild the deleted role.
- The profile owner is the sole client-facing account: only the owner communicates with clients, schedules services, and selects the driver performing an assigned service. A linked `company_driver` is an executor only; company membership does not grant customer chat, client messaging, or scheduling permissions.
- Owner-driven service assignment must validate that the selected `Conductor` belongs to the same provider profile. A driver attached to another company must be rejected.
- Fixture inserts must be idempotent and narrowly identified. Resolve canonical roles by stable `code`, never by label or assumed IDs. Do not overwrite a non-fixture row merely because a name or email resembles demo data.
- Implementation is approved. No Supabase/remote query or write, migration application, fixture execution, or production cleanup/deletion is authorized. The local fixture is standalone and manually run only against a local test database.

## Findings and data-flow implications

The public profile endpoint already returns an allowlisted provider DTO with `kind`, owner name, services, drivers, and vehicles, and it rejects profiles whose role code is not `company` or `independent_driver` or whose activation timestamp is null. It does not return rating or review fields; ratings/reviews in static mockups must remain mock-only and are not part of the live contract. Profile type should therefore be rendered from that canonical public type and must not create another role or permission category. `Perfil.kind` is also constrained to the two canonical values.

The public endpoint obtains company drivers through `Conductor.employer_profile_id = Perfil.id`. An independent provider is represented by `Usuario` + `Perfil(owner_user_id = Usuario.ID)` + `Conductor(user_id = Usuario.ID)`, with `Conductor.employer_profile_id = NULL`; the public DTO includes this owner driver by joining through the shared user ID. When that owner adds another driver, the business rule transitions this same profile to a company profile: keep the same `Perfil.ID` and owner, change `Perfil.kind` and `Rol_Perfil` to `company`, grant the owner the `company_owner` account capability, reuse the owner’s unique `Conductor` record and link it to this profile, and add the new user as `company_driver` with a `Conductor.employer_profile_id` pointing to this same profile. Do not create a second `Perfil` for the added driver. The implementation uses an owner-authorized endpoint for this transition and linked-driver provisioning. The separate local company fixture exercises company-driver visibility without touching existing independent profiles.

`Conductor.driver_type_id` is required, and independent-driver account provisioning fails closed unless a configured canonical type is supplied. Implementation must inspect existing `Tipo_Conductor` values for a suitable canonical type. If none is appropriate, create/reuse one deterministic synthetic fixture type with an exact fixture identity; do not use a profile role as a driver type and do not silently choose a label-based row.

The local test fixture is not production data. Keep public mockup names/content unmistakably demo-only; avoid real personal data, contact details, RUTs, authentic photos, and real plates. Do not create ratings/reviews as real customer feedback. Record every fixture UUID and natural cleanup key in the task document; cleanup/deletion is outside this task.

## Recommended approach and alternatives

**Recommendation:** build two dependency-free static HTML files from one shared markup/CSS pattern, implement an explicit owner-authorized company transition for the real product flow, and keep a standalone local-test fixture separate from both. Static HTML is easy to review offline and shared structure prevents profile types from drifting. The fixture creates a distinct company profile; it never changes an existing independent profile.

**Alternative — wire mockups to live API data:** closer to eventual production behavior, but it makes a design review depend on API availability and risks exposing real data. Rejected for this mockup task; API integration remains a separate implementation decision.

**Alternative — duplicate company and independent page templates:** allows profile-specific sections to diverge, but conflicts with the approved shared page design and duplicates maintenance. Rejected; type remains a field in the shared design.

**Rejected alternative — attach an independent-roster member through `employer_profile_id`:** this field represents company employment; assigning it to an independent-provider roster member would misstate the relationship.

### Required provider transition behavior

When an independent provider adds another driver, the existing provider profile becomes a company profile; it is not replaced by a second profile. The authenticated owner remains the same profile owner. The backend transition must:

1. Authorize only the authenticated owner of the exact independent profile and validate its expected current role/kind before changing state.
2. Collect and validate company data required by the company-owner contract, including the company tax ID.
3. Atomically change the owner’s account capability to `company_owner`, the existing profile’s kind/role to `company`, and the owner’s existing `Conductor.employer_profile_id` to that same profile. Reuse the existing `Conductor`; `uq_conductor_user` forbids creating a second record for the owner.
4. Provision the added account as `company_driver`, create its one `Conductor` with `employer_profile_id` set to the same `Perfil.ID`, and never create a `Perfil` for that driver.
5. Roll back the complete transition if any account/profile/driver write fails; make retries safe and define conflict behavior for concurrent or repeated requests.
6. Update public DTO/query behavior so an independent profile shows its owner as its sole driver before transition, and the transitioned company profile shows the owner-driver plus linked company drivers without exposing private account data. Provider authorization/inbox access must recognize the transitioned owner as `company_owner` for the same profile.
7. Keep customer interaction and scheduling owner-only. Where service assignment is exposed, it is performed by the authenticated profile owner and validates `Servicio.contracted_driver_id` against a driver associated with that same profile; linked drivers receive no client-facing messaging or scheduling authority.

This transition behavior is required backend scope but is not exercised by the local company fixture. Existing independent profiles remain unchanged; the separate local company profile has its own company-driver records.

## Architecture and boundaries

1. **Presentation prototype:** two static HTML documents, Spanish public header and in-page navigation, shared profile summary and section layout. Any remote image, icon, font, or script dependency must be avoided or clearly disclosed; prefer local/CSS-only assets so the mockup works offline and has no tracking/network side effects.
2. **Fixture persistence:** standalone test fixture SQL only; do not add it to Alembic or run it remotely. Resolve canonical profile/account roles by code. Seed company/driver/vehicle rows and the narrowly scoped synthetic local driver-type lookup atomically. Use deterministic UUIDs, `[DEMO]` identifying fields, `.invalid` emails, and DEMO-only plates. Use exact identity/conflict checks so an unrelated row cannot be adopted.
3. **Public data contract:** continue to use explicit response schemas/allowlists. Expose only approved public profile fields, demo driver display names, services, and vehicle brand/model/year/capacity. Never include account email, phone, personal/company RUT, auth UUID, plate, storage key, or private owner data in the public response.
4. **Local-only boundary:** no remote operation, migration application, fixture execution, or production write is authorized. The fixture file is not an Alembic migration. It creates only a separate company profile, synthetic owner, two `company_driver` users/driver records, two vehicles, and a deterministic synthetic local driver-type row. It does not change existing independent-profile rows. Do not create `auth.users` rows or credentials, create/insert/reference the `Rol_Perfil` `[DEMO] proveedor de prueba` row, delete/clean up existing records, or broaden access.

## Fixture identity and idempotency contract

- Establish deterministic fixture IDs for the new company profile, its owner user, two `company_driver` users/driver records, and two company-profile vehicle rows. Do not create fixture IDs or writes for the existing independent profile or its owner/driver records. Keep every chosen ID documented in the implementation task and tests.
- Give all fixture users visibly fake `[DEMO]` first/last names and unique `@example.invalid` emails. Set `auth_user_id` only to a synthetic deterministic UUID if required by the existing `Usuario` schema; never create that UUID in Supabase Auth.
- Use canonical account roles by code. The new fixture owner is `company_owner`; the two fixture drivers are `company_driver`. For the real transition flow, the current independent owner changes to `company_owner` and the added account is `company_driver`; do not provision that added account as `independent_driver` or create a second `Perfil` for it. The existing `/api/account/provision` endpoint does not support the transition or standalone company-driver provisioning, so implement and test an explicit owner-authorized flow rather than assuming the current endpoint does this.
- Do not query or write the existing independent profile during local fixture setup. The fixture must have no dependency on or mutation path to that profile.
- For the company profile and all new rows, use exact fixture IDs plus narrowly scoped expected marker checks. Re-running the seed produces the same state; conflicting unrelated records cause a safe failure, not silent adoption or mutation.
- Fixture plates are display-only synthetic values containing `DEMO`; ensure exact uniqueness and satisfy the database field length/constraints. The public API must not return plates.

## Privacy and safety

- Static mockups and fixture strings are public-facing. Mark demo state in the name/content, and label synthetic review/rating data explicitly if included.
- The `.invalid` domain prevents accidental delivery; no password, OTP, JWT, auth session, contact phone, real RUT, or identity verification record is generated.
- Never publish owner legal names, emails, phone numbers, RUTs, auth IDs, invitation data, plates, or storage keys. Keep public schemas allowlisted.
- The fixture is local-test-only and must not be deployed or applied to production. Record exact identifiers and natural cleanup keys, but cleanup/deletion is not authorized by this task.
- Preserve the existing public access/RLS boundary; do not grant browser roles direct table privileges.

## Verification and acceptance criteria

1. Both static mockups are Spanish and use a common public layout with profile type as a field, public header/anchor navigation, identity/location/rating/quote CTA, services, and vehicle cards. The existing independent-profile sample has its owner-driver only; the separate company-profile sample has two synthetic company drivers. Any ratings/reviews are explicitly synthetic.
2. Mockups contain no authenticated dashboard navigation, real PII, real plates, unsupported verification badge, private fields, or live API dependency.
3. Fixture tests prove canonical `Rol_Perfil.code` assignment (`company` and `independent_driver`) and that the fixture path neither inserts nor references `[DEMO] proveedor de prueba`. Verify the existing independent owner is returned via the shared `Usuario.ID` join and remains unchanged by the seed. Verify both new company drivers use account role `company_driver`, have `Conductor.employer_profile_id` set to the new company profile, and have no `Perfil` of their own.
4. Re-running the local fixture is idempotent and narrowly scoped. It cannot adopt or overwrite unrelated users/profiles/vehicles sharing only a display name; conflicting exact IDs fail safely.
5. The fixture creates one new company profile, one synthetic company owner, two synthetic `company_driver` users/driver records, and two company-profile vehicles. The existing independent profile remains one owner/one driver and is not changed by the seed. No `auth.users` rows or login credentials are created.
6. Public profile contract returns the intended services, driver names, and vehicle public details while excluding email, phone, RUT, auth ID, and plate. Driver roster representation remains semantically correct for both profile types.
7. The independent-to-company transition is owner-authorized, atomic, preserves the same profile ID/owner, changes the owner capability to `company_owner`, reuses and links the owner’s existing unique `Conductor`, provisions the added account as `company_driver` linked to that profile, and never creates another `Perfil` for the driver. Test rollback, repeated/concurrent requests, authorization failures, and required company data.
8. The public DTO returns the independent owner-driver before transition and the owner plus company-linked drivers after transition, with no private account fields. The local fixture creates the separate company sample only; it must not alter existing independent rows and must not be deployed or applied to Supabase/production. No `auth.users`, forbidden demo profile role, cleanup/deletion, or broad access is permitted. Follow strict TDD using `uv run pytest`; run focused/full applicable tests and `graphify update .` after source changes.

## Implementation sequence

1. Add failing tests for owner-authorized conversion, company-owner capability, owner Conductor reuse/linking, added `company_driver` association, rollback/conflicts, public DTO semantics, fixture identity guards, and privacy.
2. Implement the atomic conversion and standalone company-driver provisioning behavior; keep the same `Perfil.ID` and create no profile for the added driver.
3. Create both static mockups from the shared design: existing independent owner-driver only and separate company with two synthetic drivers; verify offline/responsive Spanish demo content.
4. Add an idempotent local-only fixture for the new company profile and its two company-driver users/driver records and two vehicles. Do not convert/update any independent profile or owner driver; do not add an Alembic migration or apply the fixture remotely.
5. Record exact fixture UUIDs and natural cleanup keys, run all applicable checks, and update the graph. Fixture execution against a database is outside the scope of this implementation; cleanup/deletion remains unauthorized and separate.
