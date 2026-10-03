# Provider demo profile public activation

## Objective
Make the synthetic seeded provider profile publicly viewable so the demo profile link does not return API 404.

## Problem and rationale
The public provider endpoint intentionally hides profiles unless `public_activated_at` is set. The seeded `[DEMO]` profile has no activation timestamp, so its known UUID is found but excluded from the public endpoint.

## Scope and constraints
- Add a new additive Alembic migration after `20260928_0004` that activates only the exact synthetic fixture, guarded by its ID and `[DEMO]` marker and only when currently inactive.
- Add a regression test for the migration's narrow, null-guarded update.
- Do not modify production data in this task or query Supabase.
- Do not backfill other profiles or weaken the API's public activation filter.
- Preserve unrelated pre-existing workspace changes.

## TDD and route
- TDD: RED → GREEN → REFACTOR, based on the user's established preference.
- Test runner: `uv run pytest` (backend).
- Route: delegated direct; implementation spans a migration and a regression test, and preparation involved mapping migration/test patterns.

## Tasks
- [x] T1: Add a failing migration regression test proving only the demo fixture is activated idempotently. RED observed: `uv run pytest tests/test_email_fallback_migration.py -k demo_profile_activation -q` failed because the expected migration file does not exist yet.
- [x] T2: Add the narrowly scoped additive migration and make the test pass.
- [x] T3: Commit the implementation work unit and record its commit identity.

## Acceptance criteria
- The new migration sets `public_activated_at` for only the seeded demo profile if it still matches the expected marker and is not already activated.
- A test fails before implementation and passes afterward, proving update scope and null guard.
- Existing public API behavior for unactivated profiles remains unchanged.
- No Supabase/production query or migration execution occurs.

## Progress
- Investigation verified the exact UUID is the synthetic fixture inserted by `20260927_0002`; migration `20260928_0003` adds the nullable activation field without backfilling it.
- RED: `uv run pytest tests/test_email_fallback_migration.py -k demo_profile_activation -q` failed as expected because the new migration file was absent (1 failed, 2 deselected).
- GREEN: `uv run pytest tests/test_provider_demo_public_activation_migration.py tests/test_email_fallback_migration.py -q` passed (3 passed).
- Regression coverage: recorder test verifies one `Perfil` update constrained by the exact fixture ID, exact `[DEMO]` name, and `public_activated_at IS NULL`.
- Backend verification: `uv run pytest tests/test_public_db.py tests/test_public_provider_routes.py tests/test_public_routes.py tests/test_provider_request_routes.py -q` passed (35 passed); `uv run alembic heads` reports `20261003_0001 (head)`.
- Both pytest runs emitted a non-failing `PytestCacheWarning` because the runner could not write to `backend/.pytest_cache`.
- Work-unit commit: `6fcccd4 fix: publish seeded demo provider profile`.
- RDD: enabled by default; candidate assessment was unassessable due unrelated untracked files, then native STATUS stopped safely because the RAR authority path is owned by a different SID. No review receipt was produced.
- No Supabase query or migration execution was performed. The production database still needs this migration applied separately.

## Relevant files
- `backend/alembic/versions/20260927_0002_public_browse_rls_and_demo_seed.py` — creates the synthetic provider fixture.
- `backend/alembic/versions/20260928_0003_auth_profile_and_challenge_schema.py` — introduces nullable public activation timestamp.
- `backend/tests/test_provider_demo_public_activation_migration.py` — regression test for the narrow activation migration.
