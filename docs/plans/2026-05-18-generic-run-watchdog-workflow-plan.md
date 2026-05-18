# Generic Run Watchdog Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable watchdog workflow that checks any orchestrator run, diagnoses failed/stalled/crashed runs, and invokes a repair provider that must resume, relaunch, restart, or explicitly decline as its final action.

**Architecture:** Keep the watchdog generic by making the first step a deterministic state probe over `.orchestrate/runs/<run_id>/state.json`, with optional policy knobs supplied as typed inputs. Only if the probe says repair is required does the workflow call a provider with the evidence bundle; a final deterministic publisher normalizes either no-action or repair output into one result bundle.

**Tech Stack:** DSL v2.14 workflow YAML, Python helper scripts under `workflows/library/scripts/`, prompt asset under `workflows/library/prompts/generic_run_watchdog/`, pytest runtime tests with mocked providers.

---

## Files

Create:

- `workflows/examples/generic_run_watchdog.yaml`
- `workflows/library/prompts/generic_run_watchdog/repair_run_failure.md`
- `workflows/library/scripts/probe_orchestrator_run.py`
- `workflows/library/scripts/publish_run_watchdog_result.py`
- `tests/test_generic_run_watchdog.py`

Modify:

- `docs/index.md`
- `workflows/README.md`

## Task 1: Probe Script Tests

- [ ] Write tests that create minimal run `state.json` files for `running`, `completed`, `failed`, and stale `running`.
- [ ] Assert the probe emits `RUNNING_OK`, `COMPLETED`, `FAILED`, or `STALLED`, plus an evidence bundle path.
- [ ] Run the tests and confirm they fail because the script does not exist.

## Task 2: Probe Script

- [ ] Implement safe run-id validation and run-state loading from `.orchestrate/runs/<run_id>/state.json`.
- [ ] Classify status generically without knowing the target workflow domain.
- [ ] Write a JSON evidence bundle under the requested evidence root.
- [ ] Write a structured watch bundle consumed by the workflow.
- [ ] Run focused tests until green.

## Task 3: Workflow And Repair Prompt

- [ ] Add a generic v2.14 workflow that runs `ProbeRunState`, conditionally runs `RepairRunFailure`, then runs `PublishWatchdogResult`.
- [ ] Add a workflow-agnostic repair prompt that requires root-cause classification, minimal fix, optional plan for nontrivial fixes, verification, and final resume/relaunch/restart/decline action.
- [ ] Add tests that load the workflow and execute no-repair and repair-required paths with a mocked provider.

## Task 4: Result Publisher And Docs

- [ ] Implement `publish_run_watchdog_result.py` to normalize watch-only and repaired outcomes into one result bundle.
- [ ] Document the workflow in `docs/index.md` and `workflows/README.md`.
- [ ] Run focused tests, a dry-run validation, and `git diff --check`.
