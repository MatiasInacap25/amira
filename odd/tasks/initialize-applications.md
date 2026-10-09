# Initialize Applications

## Objective and scope
Bootstrap the approved Next.js frontend and FastAPI backend without marketplace features or live external-service provisioning. Each delegated worker owns only its application directory. Do not initialize nested Git repositories.

## Constraints
- Approved dependencies: PROJECT_OVERVIEW.md.
- No direct Zod dependency, custom password storage, or frontend Docker requirement.
- No credentials; provide environment examples only.
- No existing TDD configuration was found; bootstrap smoke tests are required, without claiming strict TDD is configured.
- The workspace is not a Git repository; commits and native Git-based review are unavailable until repository initialization is authorized.

## Tasks
- [ ] T1: Scaffold frontend and install approved dependencies. Route: delegated; multi-file implementation and installations. Checks: lint, typecheck, production build, Playwright smoke test.
- [ ] T2: Scaffold backend and install approved dependencies. Route: delegated; multi-file implementation and installations. Checks: pytest, import/startup smoke test; Docker build if runtime available.
- [ ] T3: Read back both handoffs, perform independent verification, update project status and graph when available.

## Delivery
Strategy: ask-on-risk. Scaffold-generated files excluded from authored-line forecast; approximately 250 authored lines anticipated. No push or PR authorized.

## Progress
Task tracking created before application writes. Verification and commits pending.
