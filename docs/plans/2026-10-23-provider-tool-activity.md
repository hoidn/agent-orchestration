# Provider tool activity implementation plan

> For agentic workers: use superpowers:subagent-driven-development. The owner requested the fix and explicitly prohibited restarting or disturbing the active debate.

**Goal:** show tool progress from Claude and Codex session transports while preserving authoritative provider output and the currently running workflow.

**Architecture:** add a best-effort activity callback beside the existing assistant-text callback in the session codecs. The existing executor sends these short display lines to its console and observation handle, with the same identity eligibility and terminal sanitization. Activity never enters normalized assistant output, typed results, session identity, receipts or resume authority. No new command, provider request, background service or raw-event parser.

**Authorities:** `docs/index.md`, `specs/observability.md` (session-aware display), `docs/workflow_monitoring.md`, `docs/design/workflow_lisp_agent_sessions.md` (observation is non-authoritative).

**Scope:** `orchestrator/providers/session_transport.py`, `session_transport_claude.py`, `executor.py`; their transport/executor observation tests and evaluated agent-view smoke coverage; observability contract and monitoring guide. OMP and non-session providers retain their existing behavior. No provider command/model/prompt changes, partial-token protocol, timing subsystem or run-state schema changes.

**Display contract:** emit bounded one-line tool start/completion/error notices. Claude: assistant `tool_use`, user `tool_result` correlated by tool id. Codex: known tool item lifecycle events (command execution and native tool operations); completion must preserve an explicit failed status/nonzero exit without assuming success from a completed envelope. Display tool name/kind and status only, never raw arguments, command bodies, results, thinking/reasoning payloads or raw JSON. Repeated progress updates need not produce extra lines. Malformed/unknown activity is ignored without changing transport validation; callback exceptions are non-fatal. Existing assistant text stays unchanged.

**Tradeoff:** names/status expose liveness without detailed command arguments. Full investigation still uses retained transport/native records. This fix does not retrofit the already loaded code in a live process.

## Tasks

- [x] Verify clean baseline using narrow Claude transport and observation tests: 39 passed.
- [x] Write failing behavioral tests, then add the smallest separate activity callback through the codec factory and executor. Cover chunked input, tool-only turns, start/result association, explicit error, malformed/unknown events, identity mismatch, callback failure and unchanged normalized result.
- [x] Prove the notices arrive before process exit and reach console (`--stream-output`) and tmux observation independently; preserve existing terminal-control sanitization. Include an existing evaluated agent workflow smoke using fake provider shims; no live provider calls.
- [x] Update the observability contract and monitoring guide to describe the new supported display and omitted payloads.
- [x] Collect added/renamed tests, run narrow selectors, then broader relevant suites in tmux with `pytest -q -n 16 --dist=worksteal`. Independent review checks plan compliance and code correctness. Coordinator inspects diff and fresh evidence.
- [x] Deliver the reviewed change from the isolated worktree without restarting, signaling, resuming or changing files in either debate workspace. Record how the change becomes available to future invocations; do not claim it changes the existing pane.

## Decision ledger

- 2026-10-23: owner said “make the fixes. no need to restart / disturb the currently running run”. Code/test work is authorized; no new paid workflow or provider experiment.
- Worktree: `.worktrees/provider-tool-activity`, branch `fix/provider-tool-activity`, base `9c1a7c3c`. The shared main checkout has unrelated changes; do not modify or reset them.
- Runtime evidence: Claude used `--output-format stream-json --verbose`; native transcript showed 13 Bash tool calls and no assistant text. The existing decoder emits only text blocks, which explains the blank pane. No evidence of a pipe-buffering fault was found.
- Reuse the existing codec, identity checks, observation handle and terminal projector. Avoid duplicating JSON parsing in a separate watcher or mixing tool notices into normalized assistant stdout.
- The documentation trace also reaches `specs/io.md`'s console-only-text statement; update that statement while preserving the normalized step-output contract.
- Codex lifecycle kinds are restricted to command execution, MCP calls, collaboration calls and web search, as declared by [the official event protocol](https://github.com/openai/codex/blob/970111f6cb62cc02fe36a82ea7d71b37a2889c97/codex-rs/exec/src/exec_events.rs). A completed envelope without an explicit success signal displays a neutral `finished` notice.

## Verification evidence

- Baseline: 39 Claude transport and observation tests passed before changes.
- Red checks reproduced missing codec callbacks, missing executor display before child exit, and absent tool activity in an evaluated workflow's agent views.
- Collection: 172 tests collected from the four changed test modules.
- Narrow green: 38 tests passed, including malformed transport and identity regressions, OMP factory compatibility, pre-exit streaming, independent display sinks, terminal sanitization and the evaluated fake-provider workflow smoke.
- Independent plan review approved the scope. Coordinator review caught and corrected malformed-event and conflicting-identity tuple returns before the narrow green run.
- Final independent code/spec review approved the stable diff without outstanding findings.
- Broader regression suite: `pytest -q -n 16 --dist=worksteal` over 18 provider transport/observation/control, OMP and evaluated agent modules: **735 passed in 69.77s**, exit 0. Includes the public CLI workflow smoke with simulated Claude/Codex providers. Logs and module list: `/tmp/provider-tool-activity-verification/`.

- Integrated the exact reviewed patch into the main checkout after checking every destination against the worktree base; unrelated dirty files were preserved. All integrated files matched byte for byte.
- Post-integration check in the main checkout: pre-exit activity, terminal-safe Claude activity and public evaluated workflow smoke: **3 passed in 3.39s**. No live provider calls, debate workspace edits, workflow restarts/resumes or process signals. Existing loaded processes retain their display behavior; newly started processes use the fix.
