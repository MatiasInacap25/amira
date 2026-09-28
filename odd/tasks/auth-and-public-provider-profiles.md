# Real Authentication and Public Provider Profiles

## Objective
Replace authentication placeholders and dead marketplace links with a real, secure account and provider-profile flow.

## Problem and motivation
Login, registration, auth onboarding, and public provider profile routes do not exist. Service rows have a profile ID but shared-route rows do not. Public browsing does not filter unpublished provider profiles. The user requested working auth and company/provider profile links, not placeholder destinations.

## Why
Users need verified accounts and provider profiles that can be found from service and shared-route listings, while access control and private profile fields remain server-enforced.

## Scope
- Supabase Auth email/password registration and login with email confirmation.
- Mandatory SMS phone factor after password; when SMS is unavailable, the user may request an email code. Supabase email OTP does not produce AAL2; implement a distinct server-side, short-lived, single-use, session-bound fallback proof and enforce it on protected FastAPI APIs. Do not present it as equivalent to SMS MFA.
- Registration data is entered after email confirmation and sign-in; never trust user-editable auth metadata for authorization.
- Self-registration roles: client, company owner, independent driver. Company-linked drivers can only join through an owner-generated invitation and may create an account from its link.
- Driver invitations sent automatically using Resend; approved expiry is 7 days. Resend sender/API credentials and live provider operations are not authorized or configured yet.
- Owner-managed, activation-gated profiles. Activation requires public display name and >=1 offered service; company profiles additionally require company RUT. Public DTOs must exclude private account, legal, invite, auth, and verification data.
- Public profile route plus login/register links in home and marketplace navigation and profile links on services and shared routes.
- Didit is explicitly excluded.

## Constraints
- FastAPI is the application data-access and authorization boundary. No browser access to application tables or service-role secrets.
- Verify Supabase JWT signature, issuer, audience, expiry, subject, and MFA/fallback assurance server-side.
- Keep migration/backfill fail-closed and explicit; do not infer auth permissions from lookup labels or user metadata.
- Hash invitation tokens and email codes at rest; expire and consume tokens atomically; rate limit issuance and failed attempts; don't log credentials, codes, raw tokens, or PII.
- Do not connect to Supabase/Resend, inspect real `.env`, change remote settings, or send live email. Use fake/test transport in checks until the user separately authorizes a destination, operation, and credential/session.
- User explicitly authorized an audited initial Git baseline, followed by a feature branch and per-task commits. Stage only the parent-reviewed exact project-file allowlist; never use `git add .`. Exclude `.env` and secrets, generated output, caches, agent-private/tool state, and embedded Git repositories.
- Configured TDD mode: strict TDD not established in available project notes; ordinary tests/functional checks are required. Runners: backend `uv run pytest`; frontend `npm run test:e2e`, `npm run lint`, `npm run build`.
- Implementation route: delegated direct. Trigger evidence: this change spans substantially more than four files and requires coordinated frontend, backend, schema, API, auth/security, and test work. Parent maps the repository; one bounded writer owns each coordinated source batch.
- Delivery strategy: `ask-on-risk` default; forecast exceeds the ~400-line delivery heuristic, so ask for chain strategy before any feature work-unit commit. Root is an unborn `master`; parent is auditing a minimal exact baseline allowlist under user authorization before branching.

## Acceptance criteria
1. Password login and signup work through Supabase Auth; unconfirmed email cannot provision/enter protected app flows.
2. SMS enrollment/challenge/verification is mandatory. A short-lived email fallback works only after signed-in password authentication, is bound to the same verified Supabase session, rate-limited, one-use, and never fabricated as AAL2; API checks reject AAL1 without valid fallback proof.
3. Registration for each self-service role provisions exactly the allowed server-owned application records idempotently; company owners are not drivers, independent drivers have no employer, and linked drivers require valid invitation acceptance.
4. Invitations are hashed, single-use, company-scoped, target-email-bound, expire after 7 days, automatically sent by a Resend adapter, and support a recipient who must sign up, confirm email, pass SMS/email step, then accept. Tests use a fake mailer only.
5. Profile edit/activate/deactivate is owner-scoped. Activation requires the approved completeness fields. Private/inactive profiles never appear in public profile, service, or shared-route lookup.
6. Public profile output is an explicit allowlist; tests prove no email, phone, legal name, company RUT, auth ID, invite token, or private storage metadata escapes.
7. Home and desktop/mobile marketplace links navigate to existing login/register/profile routes. Service and shared-route contact actions navigate to the correct public profile; shared-route API includes `profileId`.
8. Tests cover authorization, migration/RLS inventory, idempotence, replay/expiry/wrong-email/concurrent invite acceptance, rate/expiry/consumption of email fallback, error handling, and browser auth/profile flows.
9. No Didit code, config, dependency, API, or verification requirement is introduced.

## Tasks
- [ ] T1 — Schema and migration: role codes, profile kind/activation, independent-driver employer semantics, invitation and email-fallback challenge persistence, RLS/table inventory, and structural tests. Route: delegated. Acceptance: reversible/forward migration and structural/RLS tests pass without connecting to hosted services.
- [ ] T2 — FastAPI auth boundary and account provisioning: JWT validation, AAL2-or-valid-fallback policy, role-derived idempotent provisioning, typed account endpoints, and negative security tests. Route: delegated. Acceptance: forged/expired/wrong-issuer/wrong-audience/insufficient-assurance tokens fail closed.
- [ ] T3 — Owner profiles and public discovery: scoped profile API, approved activation validation, public allowlisted profile endpoint, active-only services/routes, and backend privacy tests. Route: delegated. Acceptance: ownership/activation/privacy cases pass.
- [ ] T4 — Company invitations and Resend: create/list/revoke/reissue, email adapter/config, 7-day expiry, signup-from-invite and atomic acceptance. Route: delegated. Acceptance: fake transport and negative/replay/concurrency tests pass; no live network.
- [ ] T5 — Frontend auth and onboarding: login/register, confirmation callback, phone SMS enrollment/challenge, server-verified email fallback, invite continuation, and post-confirmation profile data entry. Route: delegated. Acceptance: accessible/error/loading states and mocked browser flows pass.
- [ ] T6 — Private profile editor and public provider profile: shared adaptable company/independent layout and owner controls. Route: delegated. Acceptance: owners see controls; public view exposes only approved active profile data.
- [ ] T7 — Navigation and integration verification: wire home/desktop/mobile auth links, service/shared-route provider links including API `profileId`; run focused/full functional checks, lint/build, security review and document config requirements. Route: delegated. Acceptance: all target routes resolve and all checks report observed results.

## Progress and verification evidence
- Architecture approved by user; email fallback accepted with the explicit understanding it is not Supabase AAL2.
- User-approved decisions: profile activation completeness; 7-day invitation expiry; Resend invitation email delivery; post-confirmation account/profile data entry; invitee may register via invite; no TOTP backup; email code may replace SMS when phone unavailable; company owners can list/revoke pending invites and resend with a new 7-day link that invalidates the previous one.
- Exploration confirmed no source changes so far; detailed findings are in current session context.
- Checks run: none yet.

## Next step
Finish the parent-reviewed explicit baseline file allowlist, create the feature branch, then implement delegated work units. Keep live email/auth and delivery operations out of scope until separately authorized/configured.


