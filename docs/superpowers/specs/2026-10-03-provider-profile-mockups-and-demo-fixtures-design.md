# Provider Profile Mockups and Demo Fixtures — Design

**Date:** 2026-10-03
**Status:** Direction agreed in conversation; written spec pending user review; implementation not started.
**Scope:** Two Spanish static public provider-profile mockups and narrowly scoped synthetic records for the current independent-driver profile plus one new company profile. This document-writing stage is docs-only; implementation and the specified production fixture write are authorized, pending design-spec review, local tests, and narrow target verification.

## Goal

Show the same public profile page design for a company and an independent driver. Profile type is a displayed field, not a different page template. Provide credible demo content for both profiles while keeping every account synthetic, clearly marked, non-login, and safe to remove later by exact identifiers.

## Approved product constraints

- Create two standalone static HTML mockups in Spanish: one for the existing independent-driver profile and one for a new company profile. Use `C:\Users\matia\Downloads\stitch_amira_logistics_marketplace\code.html` as the visual/content starting reference, adapting its company-oriented dashboard into a public profile rather than copying its authenticated navigation or private/admin affordances.
- Both mockups share one public structure and visual system. Each shows profile name, a visible profile-type field (`Empresa` or `Conductor independiente`), location, rating, and a quote CTA, followed by services, drivers, and vehicles.
- A reviews section is optional. Any rating/review content in either static mockup is mock-only, visibly labeled as sample/demo content, and must not imply real customer feedback or verified identity. The current live public DTO does not provide ratings or reviews; do not present these mock values as live data.
- Header and anchor navigation are public-facing. Do not display internal dashboard navigation, login credentials, owner controls, verification claims, or private identifiers.
- Fixtures consist of the existing independent-driver profile and one new company profile; each must have two synthetic driver users and two synthetic vehicles (four drivers and four vehicles total). Use visibly fake `[DEMO]` names, `.invalid` email addresses, and `DEMO`-only plate values. Do not create any `auth.users` rows or login credentials.
- Never create, reference, or assign `Rol_Perfil` `[DEMO] proveedor de prueba`. Both profiles must use the canonical profile role selected by `Rol_Perfil.code`: `independent_driver` for the existing independent profile and `company` for the new company. The user reports that the existing profile role was manually corrected and plans to delete the demo-role row; preserve that state and do not rebuild the deleted role.
- Fixture inserts must be idempotent and narrowly identified. Resolve canonical roles by stable `code`, never by label or assumed IDs. Do not overwrite a non-fixture row merely because a name or email resembles demo data.
- This documentation stage performs no application/source edits, Supabase/remote queries or writes, or production cleanup/deletion. The design spec and its ODD task document were committed as documentation in `2408c5c` before implementation. Implementation and production seed application remain gated on the user reviewing the written spec, passing local tests, and narrow verification of the exact target records.

## Findings and data-flow implications

The public profile endpoint already returns an allowlisted provider DTO with `kind`, owner name, services, drivers, and vehicles, and it rejects profiles whose role code is not `company` or `independent_driver` or whose activation timestamp is null. It does not return rating or review fields; ratings/reviews in static mockups must remain mock-only and are not part of the live contract. Profile type should therefore be rendered from that canonical public type and must not create another role or permission category. `Perfil.kind` is also constrained to the two canonical values.

The existing public endpoint obtains company drivers through `Conductor.employer_profile_id = Perfil.id`. Independent-driver provisioning instead creates a `Conductor` with `employer_profile_id = NULL`, and the public profile DTO currently returns an empty `drivers` array for such profiles. The approved fixture request requires two visible drivers on each profile. Do not falsify the relationship by assigning independent drivers to a company role or overloading the employer foreign key. During implementation, add the smallest explicit profile-to-driver roster association needed for both profile kinds, and update the public DTO/query/tests only if no existing canonical relationship supports the requirement. Keep the independent profile's owner/type semantics intact.

`Conductor.driver_type_id` is required, and independent-driver account provisioning fails closed unless a configured canonical type is supplied. Implementation must inspect existing `Tipo_Conductor` values for a suitable canonical type. If none is appropriate, create/reuse one deterministic synthetic fixture type with an exact fixture identity; do not use a profile role as a driver type and do not silently choose a label-based row.

Public production test records are visible to anyone who can reach the public profile endpoint. Keep all public names/content unmistakably demo-only; avoid real personal data, real contact details, real RUTs, authentic photos, and real plates. Do not create ratings/reviews in production as if they were real. The fixture implementation must record every inserted fixture UUID and its natural cleanup key (name/email/plate/type marker) in the task document for a future separately authorized cleanup. This work only documents identifiers; it must not delete anything.

## Recommended approach and alternatives

**Recommendation:** build two dependency-free static HTML files from one shared markup/CSS pattern, then add one additive, idempotent fixture migration or equivalent repository-managed seed with exact deterministic IDs and narrow conflict guards. Static HTML is fast to open/review and keeps mockup presentation decoupled from live APIs; a shared page structure prevents company and independent profiles from drifting. Use database role lookups by canonical `code` and an explicit roster relation for driver visibility.

**Alternative — wire mockups to live API data:** closer to eventual production behavior, but it makes a design review depend on API availability and risks exposing real/production content. Rejected for this mockup task; API integration remains a separate implementation decision.

**Alternative — duplicate company and independent page templates:** allows profile-specific sections to diverge, but conflicts with the approved shared page design and duplicates maintenance. Rejected; type remains a field in the shared design.

**Alternative — attach independent drivers through `employer_profile_id`:** avoids a schema change but misstates company employment and conflicts with the independent-driver model. Rejected; use an explicit roster association if needed.

## Architecture and boundaries

1. **Presentation prototype:** two static HTML documents, Spanish public header and in-page navigation, shared profile summary and section layout. Any remote image, icon, font, or script dependency must be avoided or clearly disclosed; prefer local/CSS-only assets so the mockup works offline and has no tracking/network side effects.
2. **Fixture persistence:** repository-managed additive seed/migration only. Resolve `Rol_Perfil.code` using canonical values. Seed company/driver/vehicle rows and any narrowly scoped fixture lookup/association records atomically where the current migration approach permits. Use deterministic UUIDs, `[DEMO]` identifying fields, `.invalid` emails, and DEMO-only plates. Use narrow uniqueness/conflict checks, not broad `ON CONFLICT DO NOTHING` if it can mask an unrelated row with the same key.
3. **Public data contract:** continue to use explicit response schemas/allowlists. Expose only approved public profile fields, demo driver display names, services, and vehicle brand/model/year/capacity. Never include account email, phone, personal/company RUT, auth UUID, plate, storage key, or private owner data in the public response.
4. **Production boundary:** the documentation stage performs no remote operation. After design-spec review, passing local tests, and narrow target verification, production seed application is approved only for the exact synthetic fixture rows, the current independent-driver profile, and two synthetic drivers plus two vehicles per profile. Do not create `auth.users` rows or credentials, create/insert/reference the `Rol_Perfil` `[DEMO] proveedor de prueba` row, delete/clean up existing records, or broaden access beyond this fixture scope. Public visibility is a known consequence and is not a reason to broaden data access.

## Fixture identity and idempotency contract

- Establish a dedicated deterministic UUID set for the new company profile, its owner user, four driver users, four vehicle rows, and any required synthetic driver-type/roster rows. Keep each primary key documented in the implementation task and tests.
- Give all fixture users visibly fake `[DEMO]` first/last names and unique `@example.invalid` emails. Set `auth_user_id` only to a synthetic deterministic UUID if required by the existing `Usuario` schema; never create that UUID in Supabase Auth.
- Use canonical account roles appropriate to the relationship (`company_owner` for company owner, `company_driver` for company staff, `independent_driver` for synthetic independent drivers, subject to the explicit roster design). Do not create a demo account role to bypass the existing constraints.
- For the existing independent profile, locate it by its known fixture identity/UUID and verify expected `[DEMO]` marker and `Rol_Perfil.code = 'independent_driver'`; do not create a duplicate or repair/overwrite a mismatched row in production. If that guard fails, stop and report instead of broadening the seed.
- For the company profile and all new rows, use exact fixture IDs plus narrowly scoped expected marker checks. Re-running the seed produces the same state; conflicting unrelated records cause a safe failure, not silent adoption or mutation.
- Fixture plates are display-only synthetic values containing `DEMO`; ensure exact uniqueness and satisfy the database field length/constraints. The public API must not return plates.

## Privacy and safety

- Static mockups and fixture strings are public-facing. Mark demo state in the name/content, and label synthetic review/rating data explicitly if included.
- The `.invalid` domain prevents accidental delivery; no password, OTP, JWT, auth session, contact phone, real RUT, or identity verification record is generated.
- Never publish owner legal names, emails, phone numbers, RUTs, auth IDs, invitation data, plates, or storage keys. Keep public schemas allowlisted.
- Production fixture rows become publicly visible after the approved seed is applied. Record exact identifiers and natural cleanup keys for possible future cleanup, but cleanup/deletion is not authorized by this task and activation policy must not be broadened.
- Preserve the existing public access/RLS boundary; do not grant browser roles direct table privileges.

## Verification and acceptance criteria

1. Both static mockups exist, are Spanish, use a common public layout, show profile type only as a field, and include public header/anchor navigation, identity/location/rating/quote CTA, services, two drivers, and two vehicles per profile. Any ratings/reviews included are explicitly synthetic.
2. Mockups contain no authenticated dashboard navigation, real PII, real plates, unsupported verification badge, private fields, or live API dependency.
3. Fixture tests prove canonical `Rol_Perfil.code` assignment (`company` and `independent_driver`) and specifically prove the fixture path neither inserts nor references `[DEMO] proveedor de prueba`.
4. Re-running the fixture migration/seed is idempotent and narrowly scoped. It cannot adopt or overwrite unrelated users/profiles/vehicles sharing only a display name; it fails safely when the existing independent-profile identity/role guard does not match.
5. The resulting fixture data has one new company profile and exactly two synthetic driver users plus two vehicles per target profile (4 total driver users and 4 total vehicles); no `auth.users` or login credentials are created.
6. Public profile contract returns the intended services, driver names, and vehicle public details while excluding email, phone, RUT, auth ID, and plate. Driver roster representation remains semantically correct for both profile types.
7. Existing profile activation and public endpoint behavior remain unchanged apart from the approved fixture records and the minimal roster representation required by the approved count. Production writes, after design review, local test success, and narrow exact-target verification, are limited to the synthetic fixtures, the current profile, and two drivers/two vehicles per profile; no `auth.users`, legacy demo profile role row, cleanup/deletion, or broad access is permitted.
8. Add regression coverage for migration/seed idempotency, exact fixture scoping, canonical role mapping, roster visibility, and privacy. Follow configured strict TDD using the backend runner `uv run pytest`; run focused and full applicable tests, plus `graphify update .` after source changes.

## Implementation sequence

1. Add failing tests for canonical role usage, no demo profile role, fixture identity guards, counts, idempotency, roster visibility, and public response privacy.
2. Implement the minimum safe fixture/roster changes and bring those tests green; refactor without changing the contract.
3. Create both static mockups from the shared approved design and verify the rendered HTML is offline, responsive, Spanish, and clearly demo-only.
4. Record exact fixture UUIDs and natural cleanup keys, run all applicable checks, and update the graph. The narrowly scoped production seed application is authorized only after design-spec review, local tests, and exact-target verification; cleanup/deletion remains unauthorized and separate.
