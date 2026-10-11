# Install UI/UX Pro Max Skill

## Objective
Install the official UI/UX Pro Max skill into this project's Codex skill directory and index it without changing application code or global settings.

## Problem / Why
The project needs reusable UI/UX design intelligence available to Codex; the request authorizes project-scoped skill/tool files only.

## Scope and constraints
- Install official Codex skill assets project-scoped under `.agents/skills/`; the documented CLI adds six bundled companion skills alongside `ui-ux-pro-max`.
- Update `.atl/skill-registry.md` proportionately; preserve existing skills/configuration.
- Do not modify frontend/backend source, global settings, or initialize Git.
- No UI design implementation is authorized.
- Engram mirror pending because Engram project/session tools were unavailable in this runtime.

## Authorized scope
- `.agents/skills/` (files written by the official Codex CLI installer)
- `.atl/skill-registry.md`
- `odd/tasks/install-ui-ux-pro-max.md`

## Acceptance criteria
- Official Codex install path and source/package safety inspected before executing installer.
- Skill files install project-scoped and include required scripts/data.
- Registry includes the new project skills without unrelated changes.
- Python search smoke query succeeds, or limitation is recorded.
- No application code or global settings changed; no Git repository created.

## Checks
- Inspect installed file inventory and skill frontmatter.
- Run backend `.venv/Scripts/python.exe` against a focused search query.
- Read back registry and task document.

## Plan / Progress
- [x] Explore repository, existing project skill location, registry, and official installation documentation.
- [x] Run official pinned UI/UX Pro Max CLI v2.15.0 without `--global`; it generated the Codex skill and six bundled companion skills under `.agents/skills/`.
- [x] Run `gentle-ai skill-registry refresh --force`; it indexed 53 skills and added `.agents\skills` as a source.
- [x] Run backend Python 3.12.14 smoke query `modern SaaS dashboard accessible --domain ux`; returned three UX/accessibility results.

## Route and rationale
- Delegated direct installation work: the skill comprises multiple non-trivial files, and its assets must be inspected before install.
- Trigger: multi-file skill install; installer/source safety check required.

## Verification evidence
- Official README documents `uipro init --ai codex`; pinned CLI 2.15.0 output confirmed project-local `.agents/skills/` installation. No `--global` flag was passed.
- Inspected official tagged v2.15.0 installer implementation and Codex template: default install writes the generated skill plus local data/scripts under `.agents/skills/ui-ux-pro-max/`, and copies six bundled sibling skills; installation logic uses local file operations. No frontend/backend source was changed.
- The initially guessed npm package version `2.5.0` is not published; the failed pinned-version lookup made no project changes. Corrected the command to published CLI v2.15.0.
- Smoke check passed with `backend/.venv/Scripts/python.exe`: the `ux` query returned three results.
- Registry readback reports 53 skills and includes UUPM at its project path. `.gitignore` already excludes `.atl/`.
- Repository is not a Git worktree; user explicitly requested no Git initialization, so no commit can be created.

## Next step
Installation is complete; Codex may need a restart to refresh the project skill index.
