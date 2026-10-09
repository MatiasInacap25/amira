# Dev Cloud Demo Deployment

## Objective
Prepare the existing Next.js frontend and FastAPI backend for a dev-stage demo using Vercel and Render, with deployment-on-push behavior documented for the linked Git branch.

## Problem and Why
The repository has runnable frontend/backend apps but no deployment blueprint or setup guide. The demo needs both runtime tiers, external Supabase configuration, explicit migration steps, and a repeatable path from linked Git pushes to deployments.

## Scope and Constraints
- Add a Render Blueprint for the existing backend Dockerfile.
- Document Vercel project setup with `frontend` as the monorepo root, Render service setup, required env vars/secrets, Supabase migration/auth caveats, and push-triggered deployments.
- Do not provision services, inspect remotes/credentials, push, or perform remote operations.
- Do not alter unrelated application code or existing working-tree changes.
- Keep Vercel setup in its project settings rather than inventing unsupported repository config.
- Engram recovery mirror: pending; Engram tools are unavailable in this runtime.

## Authorized Scope
- `/mnt/c/dev/amira/odd/tasks/dev-cloud-demo-deployment.md`
- `/mnt/c/dev/amira/render.yaml`
- `/mnt/c/dev/amira/docs/dev-cloud-demo-deployment.md`

## Route
- Route: delegated.
- Trigger evidence: this change adds two non-trivial repository artifacts (deployment config and operating guide); reading the app's runtime/env/migration setup prepared the write.
- TDD: not applicable to static configuration/documentation; no repository-wide TDD mode or runner was verified for this task.

## Checklist
- [x] T1: Add minimal Render Blueprint using the backend Dockerfile, health endpoint, and commit-triggered deployments.
- [x] T2: Write the Vercel + Render dev-demo guide, including environment setup, Supabase/migration caveats, linked Git provider, and push-based updates.
- [x] T3: Validate YAML syntax, paths, links/commands, and final diff without provisioning or remote access.

## Acceptance Criteria
- Render blueprint points at `/backend` and its existing Dockerfile, serves the FastAPI health endpoint, and enables deploys on linked-branch commits.
- Guide tells the operator to configure Vercel root directory `frontend`, connect the Git provider/branch, provide frontend public env vars and backend secrets, set exact CORS/frontend API origins, configure Supabase callback/MFA, apply migrations, and expect deployments after pushes (not each local save).
- No credentials, remote service changes, unrelated edits, or claims of actual deployment are introduced.

## Checks
- Parse `render.yaml` using an already-installed YAML parser if available; otherwise validate structure with a read-only local check and state the limitation.
- Check referenced paths, Dockerfile, health route, and documented env keys against repository files.
- Inspect only this task's final diff; do not run installs, builds, application tests, or remote commands.

## Progress and Evidence
- T1: `render.yaml` points at `backend` and its Dockerfile, uses `.` build context, checks `/health`, auto-deploys commits, and limits builds to `backend/**` changes.
- T2: Added `docs/dev-cloud-demo-deployment.md` with Git linking, Vercel `frontend` root, Render Blueprint setup, env vars, Supabase Auth/MFA, explicit Alembic migration step, and push-vs-local-save behavior.
- T3: PyYAML parsed `render.yaml`; checked Dockerfile, health endpoint, env keys, documented paths, and whitespace. Ruby unavailable; no Render CLI validation, app tests, builds, installs, remote actions, or provisioning performed.

## Next Step
Complete; parent to inspect the scoped files and decide on any commit/review action.

## Relevant Files
- `render.yaml` — planned Render backend blueprint.
- `docs/dev-cloud-demo-deployment.md` — planned operator guide.
- `backend/Dockerfile` — existing Render Docker build target.
- `backend/src/amira_api/main.py` — `/health` endpoint and CORS setup.
- `backend/src/amira_api/settings.py` — supported backend configuration.
- `frontend/.env.example` — supported frontend public configuration.
