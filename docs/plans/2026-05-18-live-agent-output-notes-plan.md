# Live Agent Output Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a short, periodically refreshed current-step note from bounded provider transport output and show it in the observability summary GUI.

**Architecture:** Add a runtime-side `LiveAgentNoteObserver` that watches a session provider transport spool, calls a configured cheap summary provider on a throttled interval, and writes `RUN_ROOT/summaries/live-current-step.md/json`. The dashboard remains read-only: it polls `live.json`, reads those artifacts when present, and updates the live panel.

**Tech Stack:** Python stdlib threads/filesystem, existing provider executor, existing dashboard server, pytest.

---

## Files

- Create `orchestrator/observability/live_notes.py`
  - Runtime observer for bounded transport-tail summarization.
  - Atomic writes for live note Markdown and metadata JSON.
- Modify `orchestrator/workflow/executor.py`
  - Create observer from `observability.step_summaries.live_agent_notes`.
  - Start observer while a session-enabled provider invocation is running.
- Modify `orchestrator/cli/main.py`
  - Add `run` and `resume` flags for live notes.
- Modify `orchestrator/cli/commands/run.py`
  - Persist live-note runtime config.
- Modify `orchestrator/cli/commands/resume.py`
  - Merge resume-time live-note overrides into persisted config.
- Modify `orchestrator/dashboard/server.py`
  - Include live note metadata/text in `/summaries/live.json`.
  - Render live note text in the current-step panel.
- Modify docs/specs
  - `docs/design/dashboard_observability_summary_gui.md`
  - `specs/observability.md`
  - `specs/cli.md`
- Tests
  - `tests/test_observability_live_notes.py`
  - `tests/test_observability_summary_runtime.py`
  - `tests/test_cli_observability_config.py`
  - `tests/test_dashboard_server.py`

## Task 1: Observer Unit

- [ ] Add failing tests for one-shot live-note generation from a transport spool.
- [ ] Implement `LiveAgentNoteObserver.emit_once`.
- [ ] Assert generated files contain provider stdout and metadata without absolute source paths.

## Task 2: Runtime Integration

- [ ] Add a failing runtime smoke test with a slow session provider and a fake cheap summary provider.
- [ ] Implement observer construction from runtime observability config.
- [ ] Wrap provider invocation execution in the live-note observer when session transport exists.
- [ ] Ensure failures are best-effort and do not change workflow status.

## Task 3: CLI Config

- [ ] Add parser/config tests for run and resume live-note flags.
- [ ] Implement CLI flags and persisted config merge.
- [ ] Validate interval, timeout, and tail-size values are positive.

## Task 4: Dashboard Display

- [ ] Add failing dashboard test for `live.json` including note text and safe note links.
- [ ] Add live note fields to the JSON endpoint.
- [ ] Update the current-step panel JavaScript to display the generated note.

## Task 5: Verification

- [ ] Run focused tests:
  - `python -m pytest tests/test_observability_live_notes.py -q`
  - `python -m pytest tests/test_observability_summary_runtime.py -q`
  - `python -m pytest tests/test_cli_observability_config.py -q`
  - `python -m pytest tests/test_dashboard_server.py -q`
- [ ] Run relevant broader dashboard/summary tests.
- [ ] Run `git diff --check` on touched files.
