# Lisp Implementation Report Target Repair Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the Lisp frontend implementation-phase review loop so revise flows do not fail when the implementation provider emits an execution report path that differs from the canonical target path.

**Architecture:** Keep the repair inside `lisp_frontend_implementation_phase.v214.yaml` and its runtime regression coverage. Expose the canonical execution-report target to implementation providers, and make the revise republish step prefer that target while falling back to the latest published execution-report artifact so existing persisted runs can resume safely.

**Tech Stack:** Workflow DSL v2.14 YAML, Python-based runtime tests with patched providers, pytest

---

### Task 1: Capture The Failing Runtime Behavior

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Reference: `workflows/library/lisp_frontend_implementation_phase.v214.yaml`

- [ ] **Step 1: Add a helper that writes an implementation-state bundle whose `execution_report_path` is not the canonical target path**

- [ ] **Step 2: Add a focused runtime test for implementation review `REVISE -> APPROVE` using that mismatched report path**

- [ ] **Step 3: Run the new test alone to verify it fails for the expected reason before changing workflow behavior**
Run: `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_implementation_review_revise_then_approve_with_noncanonical_execution_report_path -q`
Expected: FAIL because `PublishUpdatedExecutionReport` requires the canonical target file, which does not exist.

### Task 2: Repair The Workflow Contract

**Files:**
- Modify: `workflows/library/lisp_frontend_implementation_phase.v214.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Publish the implementation-phase execution report target as a first-class artifact during materialization**

- [ ] **Step 2: Feed that target artifact into `ExecuteImplementation` prompt inputs so providers receive the canonical destination**

- [ ] **Step 3: Feed that same target artifact into `FixImplementation` prompt inputs so revise passes can update the canonical destination explicitly**

- [ ] **Step 4: Update `PublishUpdatedExecutionReport` to write the canonical target when it exists, otherwise fall back to the latest published execution-report artifact path**

- [ ] **Step 5: Keep the change minimal; do not widen unrelated implementation-phase behavior**

### Task 3: Verify And Recover The Run

**Files:**
- Modify: `artifacts/work/generic-run-watchdog/repair-report.md`
- Modify: `artifacts/work/generic-run-watchdog/repair-result.json`

- [ ] **Step 1: Re-run the new focused regression and the existing narrow smoke for the Lisp revise loop**
Run: `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_implementation_review_revise_then_approve_with_noncanonical_execution_report_path tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_implementation_review_revise_then_approve -q`
Expected: PASS

- [ ] **Step 2: Run the broader drain smoke required by repo policy for workflow behavior changes**
Run: `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q`
Expected: PASS

- [ ] **Step 3: Write the repair report and repair-result bundle with the root cause, complexity, verification, and recovery action**

- [ ] **Step 4: Resume run `916bf262f34e4305ab9e37a3f17262dc` from repo root and capture the fresh result**
Run: `python -m orchestrator resume 916bf262f34e4305ab9e37a3f17262dc`
Expected: the persisted run advances past the failed `PublishUpdatedExecutionReport` boundary instead of failing immediately on the missing canonical target file.
