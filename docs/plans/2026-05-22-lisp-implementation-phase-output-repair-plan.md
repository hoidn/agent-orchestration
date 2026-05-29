# Lisp Implementation Phase Output Repair Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent `lisp_frontend_implementation_phase.v214.yaml` from failing when the implementation step writes the canonical execution report but redundantly echoes a malformed completed-path value in its variant bundle.

**Architecture:** Keep the provider-owned `implementation_state` discriminant, but make the workflow use runtime-owned authoritative target paths for completed and blocked report publication. The provider should still decide whether work is `COMPLETED` or `BLOCKED`, while the workflow validates the discriminant and publishes report-path artifacts from known targets instead of trusting provider-authored path echoes.

**Tech Stack:** DSL v2.14 workflow YAML, pytest runtime smoke tests, provider contract validation.

---

### Task 1: Add the regression test

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write the failing test**

Add a focused runtime smoke that simulates `ExecuteImplementation` writing only the canonical execution report target plus `implementation_state: COMPLETED`, without an `execution_report_path` field, and assert the drain completes successfully.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k canonical_execution_report_target_without_completed_path -q`
Expected: FAIL because the current `variant_output` contract still requires `/execution_report_path` for the `COMPLETED` variant.

### Task 2: Repair the workflow contract

**Files:**
- Modify: `workflows/library/lisp_frontend_implementation_phase.v214.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Narrow the provider-owned completed variant**

Change `ExecuteImplementation.variant_output` so the `COMPLETED` variant no longer requires `execution_report_path`. Keep the discriminant authoritative and preserve `BLOCKED` metadata needed for routing and reporting.

- [ ] **Step 2: Publish completed output from the authoritative target**

Update `PublishCompletedExecutionReport` to validate and publish from `${inputs.execution_report_target_path}` instead of a provider-authored completed-path artifact. Keep the target-exists check so the workflow still fails if the report was written to the wrong location.

- [ ] **Step 3: Publish blocked output from the authoritative target**

Update `PublishBlockedProgressReport` to use `${inputs.progress_report_target_path}` instead of a provider-authored blocked-path artifact so both variant paths follow the same authority rule.

### Task 3: Verify and recover the failed run

**Files:**
- Modify: `artifacts/work/generic-run-watchdog/repair-report.md`
- Modify: `artifacts/work/generic-run-watchdog/repair-result.json`

- [ ] **Step 1: Re-run targeted tests**

Run:
- `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k canonical_execution_report_target_without_completed_path -q`
- `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k 'selected_item_reuses_approved_plan or implementation_review_revise_then_approve' -q`

Expected: PASS with no regressions in the affected Lisp implementation-phase flows.

- [ ] **Step 2: Resume the failed run**

Run: `python -m orchestrator resume 20260523T015051Z-bo9619`
Expected: the repaired workflow re-enters at the failed implementation path and completes or advances beyond the prior contract violation.

- [ ] **Step 3: Record repair evidence**

Write `artifacts/work/generic-run-watchdog/repair-report.md` with the root cause, fix, verification commands, and recovery outcome. Then write `artifacts/work/generic-run-watchdog/repair-result.json` using the required output contract.
