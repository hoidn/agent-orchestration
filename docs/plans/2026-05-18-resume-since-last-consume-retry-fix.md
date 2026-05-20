# Resume Since-Last-Consume Retry Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow failed or interrupted steps that use `freshness: since_last_consume` to resume against the same published artifact version when the prior attempt never completed.

**Architecture:** Keep consume resolution available for prompt injection and consume bundles before execution, but stop treating a failed attempt as a committed consume. Move `since_last_consume` bookkeeping to a success-only finalization path, add a resume regression that reproduces the stale-artifact failure, then re-run the blocked lisp frontend run after the runtime fix.

**Tech Stack:** Python runtime (`orchestrator/workflow`), pytest, persisted run state, `python -m orchestrator resume`

---

### Task 1: Add The Resume Regression First

**Files:**
- Modify: `tests/test_resume_command.py`

- [ ] **Step 1: Add a minimal workflow builder for a `since_last_consume` step that fails after consume preflight**

Create a small workflow fixture with:
- one publisher step that publishes a scalar artifact
- one consumer step using `freshness: since_last_consume`
- a command that fails on the first run and succeeds after `state/resume_ready.txt` exists

- [ ] **Step 2: Add a resume regression test**

Initial run should fail after consume preflight.
Resume should succeed without requiring a new artifact publication.

- [ ] **Step 3: Run the narrow test and confirm RED**

Run: `pytest tests/test_resume_command.py -k since_last_consume -v`
Expected: the new test fails with a stale-artifact resume failure before the runtime fix.

### Task 2: Commit Consume Bookkeeping Only On Successful Completion

**Files:**
- Modify: `orchestrator/workflow/dataflow.py`
- Modify: `orchestrator/workflow/executor.py`

- [ ] **Step 1: Introduce pending consume bookkeeping in `DataflowManager`**

Keep resolved consume values available during step execution, but do not advance persisted `artifact_consumes` during preflight.

- [ ] **Step 2: Finalize or discard pending consumes at the step-result boundary**

Successful steps commit pending consumes.
Failed or skipped steps discard pending consumes for that runtime step id.

- [ ] **Step 3: Wire the finalization into both top-level and nested-loop execution paths**

Ensure loop runtime step ids and top-level step ids both use the same success-only consume commit path.

### Task 3: Verify And Repair The Target Run

**Files:**
- Modify: `.orchestrate/runs/916bf262f34e4305ab9e37a3f17262dc/state.json`
- Create: `artifacts/work/generic-run-watchdog/repair-report.md`
- Create: `artifacts/work/generic-run-watchdog/repair-result.json`

- [ ] **Step 1: Re-run the narrow regression and the lisp frontend runtime selector**

Run:
- `pytest tests/test_resume_command.py -k since_last_consume -v`
- `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k implementation_review_revise_then_approve -v`

Expected: both pass.

- [ ] **Step 2: Repair the persisted run state for the consumed step retry**

Remove the stale committed consume entry for runtime step `root.implementation_review_loop#2.implementation_review_iteration.route_iteration_work.completed_iteration_path.fix_implementation` from the nested implementation-phase call-frame state so the repaired runtime can retry the step once.

- [ ] **Step 3: Resume the original run**

Run: `python -m orchestrator resume 916bf262f34e4305ab9e37a3f17262dc`

Expected: the run advances past the stale-artifact failure and either continues running or surfaces a new concrete downstream issue.
