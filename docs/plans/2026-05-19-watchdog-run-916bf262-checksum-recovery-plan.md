# Watchdog Run 916bf262 Checksum Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover run `916bf262f34e4305ab9e37a3f17262dc` without replaying earlier approved stages by repairing the iteration-8 review pointer state and updating only the persisted top-level workflow checksum needed for `resume` to accept the current top-level workflow file.

**Architecture:** Treat the persisted run state and watch evidence as authority. First repair the concrete iteration-8 pointer contract violation from authoritative per-item inputs. Then back up `state.json`, verify that the only live checksum blocker is the top-level workflow file, and update only `workflow_checksum` to the current checksum so `resume` can test whether the persisted restart point is still valid. If resume exposes any deeper checksum mismatch or semantic failure, stop and record the blocker rather than forcing a fresh relaunch.

**Tech Stack:** JSON run state, workflow YAML, `python -m orchestrator resume`, tmux, targeted shell verification.

---

### Task 1: Repair The Concrete Iteration-8 Review Pointer Violation

**Files:**
- Modify: `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/design-gap-work-item/implementation-phase/implementation_review_report_path.txt`
- Create: `artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface-implementation-review.md`
- Read: `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/design-gap-work-item/work-item-inputs.json`

- [ ] **Step 1: Back up the mutated pointer file**

Copy `implementation_review_report_path.txt` to a timestamped sibling backup before changing it.

- [ ] **Step 2: Restore the authoritative report target**

Read `implementation_review_report_target_path` from `work-item-inputs.json`, copy the generated review content to that target path, and rewrite `implementation_review_report_path.txt` to the exact repo-relative target path.

- [ ] **Step 3: Verify the repaired pointer contract**

Check that the pointer value starts with `artifacts/review/` and that the target file exists.

### Task 2: Repair Only The Top-Level Checksum Gate

**Files:**
- Modify: `.orchestrate/runs/916bf262f34e4305ab9e37a3f17262dc/state.json`
- Create: `.orchestrate/runs/916bf262f34e4305ab9e37a3f17262dc/state.json.pre-watchdog-checksum-repair-*.bak`
- Read: `workflows/examples/lisp_frontend_autonomous_drain.yaml`

- [ ] **Step 1: Back up the persisted run state**

Copy the current run `state.json` to a timestamped backup beside the run.

- [ ] **Step 2: Confirm the current checksum blocker is the top-level workflow**

Print the recorded `workflow_checksum` from `state.json`, compute the current checksum for `workflows/examples/lisp_frontend_autonomous_drain.yaml`, and confirm they differ.

- [ ] **Step 3: Update only `workflow_checksum`**

Set the top-level `workflow_checksum` field in `state.json` to the current file checksum. Do not modify restart position, step status, call-frame state, or recorded outputs.

### Task 3: Retry Resume And Record The Outcome

**Files:**
- Modify: `artifacts/work/generic-run-watchdog/repair-report.md`
- Modify: `artifacts/work/generic-run-watchdog/repair-result.json`

- [ ] **Step 1: Resume the persisted run in tmux**

Run:

```bash
python -m orchestrator resume 916bf262f34e4305ab9e37a3f17262dc
```

Expected:

- either the run resumes past the checksum gate and continues from persisted state
- or resume fails with a deeper, concrete error that can be documented exactly

- [ ] **Step 2: Capture fresh verification evidence**

Record the repaired pointer value, the updated top-level checksum, and the resume stdout/stderr result.

- [ ] **Step 3: Write the repair report and repair-result bundle**

If resume succeeds, write `FIXED_AND_RESUMED`. If resume fails on a deeper checksum or semantic blocker, write `BLOCKED` and `DECLINED` with the plan path recorded.
