# Codex Agent Dashboard

## Objective and authorization
Build a small independent localhost page monitoring existing Codex agents working in C:/dev/amira, including subagents grouped under their parent. User approved the design and explicitly requested subagents. This is read-only monitoring, not a launcher or controller.

## Design and scope
Use a standalone Node.js standard-library server and dependency-free browser UI in tools/agent-dashboard. A read-only JSON-RPC bridge runs codex app-server proxy against the existing local daemon. Poll thread/list and read only scoped current-task metadata when supported. Include project descendants and documented subagent lineage; preserve orphan subagents visibly rather than dropping them. No new Codex daemon or turn may be started. Do not use SQLite timestamps as running-state evidence.
Display a project header, connection freshness, agent counts, nested agent cards, task summaries, state, and last observed activity. Accessible responsive UI, readable light neutral palette, no remote assets or fake live data. Existing Amira UI/backend remain untouched.

## Tasks and routes
- [x] T1: Implement read-only telemetry bridge, standalone dashboard, focused tests, and start instructions.
  - Route: delegated direct; new logic across server, browser UI and tests requires a writer.
  - Acceptance: localhost-only; strict project filter; parents and subagents rendered; connection failure and stale state honest; no sensitive transcript/command/diff content exposed.
  - Checks: node --test tools/agent-dashboard/*.test.mjs; node --check for each authored .mjs; HTTP smoke checks. Test fixtures must stay test-only.
- [x] T2: Independently verify project isolation, hierarchy, unknown/error/stale rendering, and browser behavior; open the running page.
  - Route: delegated verification for unassessable risk; parent runtime/browser readback.
  - Acceptance: real page loads; own refresh/filter behavior works; no unrelated agents leak; actual live source success or explicit unavailable proof recorded.
  - Checks: repeat unit tests, focused negative tests, local HTTP/browser inspection.

## Safety and constraints
Bind only 127.0.0.1. Read-only API allowlist. Validate Host/Origin to resist DNS rebinding; no CORS wildcard. Browser gets only allowlisted bounded fields. Use textContent for untrusted titles. Do not inspect secrets, raw reasoning, full prompts, stdout or diffs. No installs, remote operations, mutations to Codex sessions, database access, or changes to Amira app code. No automatic daemon start/restart. Gracefully disclose unsupported experimental lineage capability.

## TDD, verification and delivery
Strict TDD is not established (existing odd/tasks/search-and-shared-routes.md and Engram observation 139); ordinary observed functional checks are required. Exact runner for this standalone tool: node --test tools/agent-dashboard/*.test.mjs. Tests-first is welcome but do not claim strict-TDD authority.
RDD effective mode: on by default, read-only mode check 2026-09-27. Later elevated checks found a Git repository on unborn master with all project paths untracked, superseding the initial no-repository result. No staging, branch switching, or commits were performed in this shared checkout; commit delivery remains pending rather than risking unrelated work. Native assessment was unassessable; selectorless STATUS failed with "validate negotiated review failure: invalid negotiated review failure message" before opening a transaction. No review approval is claimed. Delivery strategy ask-on-risk; original forecast approximately 500-750 authored lines including tests, one coherent local tool, no PR created. Size does not justify dropping tests.
One independent verifier is required if native assessment is unavailable. Record observed checks, not assumed success.

## Evidence and current limitations
- Installed codex-cli: 0.158.0-alpha.2.1.
- Official protocol: https://developers.openai.com/codex/app-server/
- codex app-server proxy attaches to a running daemon via stdio; thread/list supplies runtime status and subagent source kinds.
- Default daemon socket currently fails even outside sandbox with Windows error 10050. Existing desktop live visibility is UNVERIFIED. Dashboard must show disconnected, not successful live monitoring.
- graphify update . completed after implementation: 3,737 nodes, 4,753 edges, 258 communities; generated graph outputs refreshed.

## Progress and next step
Connection follow-up (user explicitly requested connection): T3 is BLOCKED, not completed. Read-only process and installed desktop-source inspection identified a transport mismatch: the Windows desktop owns a codex app-server child over stdio, whereas this dashboard targets the separate shared daemon control socket. The inspected daemon selection is gated off on Windows. The discovered codex-ipc named pipe is private thread-stream/follower IPC, not a proven endpoint for thread/list or thread/read; no speculative requests were sent. The default home selector uses CODEX_HOME or the user's .codex directory. Normalized exact-root plus descendant queries in that default state's database returned zero Amira sessions. A process-specific home override is unverified. No attachable live source has been established, and no new daemon, agent, or replacement session was started. No application code was changed during this diagnosis. The earlier idea that supplying another socket path alone would solve this remains unproven and must not be presented as the confirmed next step. Next step requires a verified read-only bridge to this desktop instance or a newly established, explicitly scoped real event source.

T1 and T2 implementation/verification work complete; LIVE MONITORING ACCEPTANCE REMAINS PENDING. Added the standard-library Node server/proxy, strict path-scope and hierarchy model, stale/error handling, bounded RPC and pagination, loopback-only HTTP UI, and tests/start instructions in `tools/agent-dashboard/`. One correction pass fixed object-form `SessionSource.subAgent`, incomplete-pagination notice visibility, and proxy teardown/reconnection races. Writer, independent verifier and parent observed all 18 tests passing; all five JS module/test syntax checks passed. Independent targeted validation confirmed all three defects fixed.

The parent started the real page at http://127.0.0.1:4312 (exec session 7769) and requested opening it in Codex. Installed Edge headless verified desktop 1440x1000 and mobile 390x844 with no page errors or horizontal overflow. Isolated browser-only fixtures verified parent/subagent rendering, refresh, incomplete warning, and stale status; those fixtures were removed before closing the test browser and were never supplied by the real server. The actual /api/snapshot returns state unavailable with zero agents because the Codex socket remains unreachable (known Windows error 10050). No fake activity is shown. CUA initialization and default shell failed sandbox setup; approved elevated commands and installed Edge provided fallback checks. No browser or package installation was performed.

Next step: connect the dashboard to a reachable existing Codex desktop app-server control socket, using the documented --sock option only with a known valid local path, then validate real Amira parent/subagent telemetry. Do not start replacement agents or a new daemon to manufacture success. Commit delivery and native review remain pending/unavailable as described above.
