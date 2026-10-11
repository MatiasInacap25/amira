# GitHub Preparation and Review

## Objective
Prepare a safe, reviewable local GitHub candidate for the development demo while excluding email fallback behavior.

## Problem and Why
The staged candidate mixed marketplace/profile work with an incomplete email fallback flow, and the worktree contains local tooling state that should not be published. Supabase reports Alembic revision `20260928_0004` as applied, so migration history must remain represented even while the email runtime feature is excluded.

## Scope and Constraints
- Keep the provider/marketplace work and deployment configuration intended for the demo.
- Exclude email fallback runtime code and its behavior tests from the GitHub candidate.
- Preserve the already-applied migration revision and a valid local migration lineage; do not execute migrations against Supabase.
- Ignore local caches, assistant tooling, dependencies, and Supabase temporary state; never stage with `git add .`.
- User authorized committing and pushing this curated candidate to `codex/github-upload`; do not force-push or modify remote `main`.
- User confirmed public rating comments are intentional.

## TDD and Checks
- TDD: not applicable to candidate curation and ignore/config preparation; no application behavior is being authored in this task.
- `git diff --cached --check`: required.
- Backend tests and Alembic graph validation: `python`/`uv` were unavailable in the current environment; retry only if an interpreter becomes available.
- Frontend checks already observed: lint/build pass; Playwright is blocked by missing Chromium.
- Native review remains unavailable because `gentle-ai` is not installed. The user explicitly waived the native review for this candidate; do not claim a native approval or receipt.
- Graphify update remains unavailable because `graphify` is not installed.

## Tasks
- [x] GHP-1 Remove email fallback runtime and behavior-test changes from the staged candidate while preserving applied migration history.
- [x] GHP-2 Add root ignore rules and stage only intended project/deployment files; exclude local artifacts and secrets.
- [x] GHP-3 Re-review the corrected staged candidate and record all passed, blocked, and pending checks.
- [x] GHP-4 Commit the curated candidate and publish it to the authorized GitHub branch without including excluded email runtime or unrelated working-tree changes.

## Progress and Evidence
- Current candidate contains 16 staged files; see the staged diff for its current line totals. Email fallback runtime files are left unstaged.
- Supabase SQL Editor reported Alembic revision `20260928_0004`.
- Preserved revision `20260928_0004` and added merge revision `20261005_0001` to join it with `20261003_0002`; Alembic CLI validation is blocked because Python/uv are unavailable.
- Updated `render.yaml` build-filter paths to the documented list form and removed email fallback environment guidance from the deploy guide.
- Left `test_email_fallback_migration.py` unstaged because its assertions depend on the excluded runtime ORM fields.
- `git diff --cached --check` passes after normalizing root `.gitignore` line endings.
- Final manual review found no actionable defect in the staged candidate. Native review remains unavailable because `gentle-ai` is not installed; this is not a native approval.
- Frontend lint/build passed; E2E was partially blocked by missing Chromium; backend/Alembic checks were blocked by missing Python/uv.
- User authorization received to publish the curated candidate to `MatiasInacap25/amira` on `codex/github-upload`; no remote database migration is authorized.
- The remote `main` currently contains only its initial README commit and has unrelated history from the local project. The upload branch will include that initial commit without changing `main`.
- Candidate work-unit commit: `5ea228b` (`feat: prepare provider demo for cloud deployment`).
- Published branch: `codex/github-upload`; verified remote ref at `b1bfb1454a3e308e83c439b9f0448e7e59d1cfc6`. `main` was not modified.
- Engram mirror: pending; Engram tools are unavailable in this session.

## Next Step
Share the branch with collaborators for preview. Do not modify `main`, merge a PR, or run Supabase migrations without separate authorization.

## Relevant Files
- `backend/alembic/versions/20260928_0004_email_fallback_proofs.py` — revision already applied in Supabase; preserve as history.
- `backend/alembic/versions/20261005_0001_merge_email_fallback_heads.py` — joins applied email revision to the tracked demo-profile branch.
- `.gitignore` — root ignore rules for local artifacts and caches.
- `render.yaml` and `docs/dev-cloud-demo-deployment.md` — deployment configuration and guide.
