# Stalled Run Checksum Drift Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover run `20260518T230341Z-6uwqxs` safely without resuming it against workflow files that no longer match the recorded run checksums.

**Architecture:** Treat the persisted run state as authoritative, restore the exact workflow revisions that match its recorded checksums, and resume only after the restored files and call-frame checksums agree with state. If the exact revisions cannot be reconstructed without overwriting active user work, stop and require an operator decision before any fresh relaunch.

**Tech Stack:** `python -m orchestrator`, git object history, orchestrator state/checksum utilities, JSON state inspection

---

### Task 1: Reconstruct The Recorded Workflow Revisions

**Files:**
- Read: `.orchestrate/runs/20260518T230341Z-6uwqxs/state.json`
- Read: `workflows/examples/lisp_frontend_autonomous_drain.yaml`
- Read: `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
- Read: `specs/state.md`

- [ ] **Step 1: Capture the recorded checksums from the stalled run state**

Run: `python - <<'PY' ...` to print `workflow_checksum` for the top-level workflow and each relevant call frame from `.orchestrate/runs/20260518T230341Z-6uwqxs/state.json`.
Expected: Recorded checksums are available for the top-level workflow plus the `design_gap_architect` and `work_item` call frames.

- [ ] **Step 2: Locate matching git revisions for the drifted workflow files**

Run: `git log -- workflows/examples/lisp_frontend_autonomous_drain.yaml workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
Expected: Candidate commits exist that predate the current checksum drift.

- [ ] **Step 3: Verify exact file content matches before restoring anything**

Run: `git show <commit>:workflows/examples/lisp_frontend_autonomous_drain.yaml | sha256sum` and the equivalent command for `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`.
Expected: A candidate commit reproduces the recorded `sha256:` values from state.

- [ ] **Step 4: Materialize the matched files in a safe recovery location without overwriting active user edits**

Create recovery copies outside the tracked workflow paths first, or use an operator-approved temporary clone/snapshot that preserves the current dirty workspace.
Expected: Exact-match workflow files exist in a recovery location and active user edits remain untouched.

### Task 2: Resume Only After Checksum Agreement

**Files:**
- Read: `.orchestrate/runs/20260518T230341Z-6uwqxs/state.json`
- Read: `specs/cli.md`
- Read: `docs/runtime_execution_lifecycle.md`

- [ ] **Step 1: Re-run checksum verification against the recovery location**

Run the same checksum helper used by `StateManager.calculate_checksum(...)` against the restored workflow files.
Expected: Restored checksums exactly match the recorded values for the top-level workflow and the affected call frame.

- [ ] **Step 2: Confirm resume still selects the persisted repeat-until frame**

Run a short Python snippet that loads the run with `StateManager` and prints `WorkflowExecutor._determine_resume_restart_node_id(...)`.
Expected: Restart node is still `root.drain_lisp_frontend_work` and no new integrity error is raised.

- [ ] **Step 3: Resume the run from the exact recovered workflow revision**

Run: `python -m orchestrator resume 20260518T230341Z-6uwqxs`
Expected: The run either completes or fails with a concrete, current error instead of remaining stalled.

### Task 3: Fallback If Exact Recovery Is Impossible

**Files:**
- Create: `artifacts/work/generic-run-watchdog/repair-report.md`
- Modify: `artifacts/work/generic-run-watchdog/repair-result.json`

- [ ] **Step 1: Record why exact recovery is impossible**

Document which workflow files could not be restored to their recorded checksums and whether active user edits blocked safe restoration.
Expected: The repair report states a concrete recovery blocker.

- [ ] **Step 2: Require an explicit operator decision before relaunching**

Do not relaunch automatically if exact-resume safety cannot be re-established. Record whether the operator wants a fresh run using the current workflow files.
Expected: Relaunch happens only after an explicit decision to redo earlier gated stages.
