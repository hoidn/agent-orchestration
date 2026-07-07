# Design Gap Architect Invalid Output Repair Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the design-gap architect and its drain callers so reviewed `INVALID` or `BLOCKED` architecture results stop crashing workflow-output export and instead route through durable blocked handling.

**Architecture:** Keep `architecture-validation.json` as the canonical handoff bundle for all validation outcomes, then teach the autonomous drain, design-delta drain, and done-review design-gap path to branch on `architecture_validation_status` before invoking the work-item workflow. Use durable run-state recording for blocked design-gap drafting so drain-level `BLOCKED` status remains honest and resumable.

**Tech Stack:** YAML workflows, Python helper scripts, pytest workflow runtime tests

---

### Task 1: Lock the Regression With Tests

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write a failing architect-workflow regression test**

Add a runtime test that executes `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml` with provider stubs returning a drafted architecture plus a `REVISE` review bundle, and assert the workflow completes with `architecture_validation_status == "INVALID"` instead of failing with a workflow-output contract violation.

- [ ] **Step 2: Run the narrow architect regression**

Run: `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_gap_architect and invalid"`

Expected: FAIL because the workflow currently raises `Workflow output export failed` when `work_item_bundle_path` is absent.

- [ ] **Step 3: Write a failing drain-path regression**

Add a runtime smoke test for `workflows/examples/lisp_frontend_design_delta_drain.yaml` where the selector chooses a design gap, the architect review returns `REVISE`, and the workflow is expected to finish with a blocked summary instead of crashing before summary publication.

- [ ] **Step 4: Run the narrow drain regression**

Run: `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_delta and design_gap and blocked"`

Expected: FAIL because the drain currently tries to consume an unconditional design-gap work-item bundle path.

### Task 2: Make Invalid Architecture Results Exportable

**Files:**
- Modify: `workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py`
- Modify: `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
- Modify: `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Update the validator bundle contract**

Ensure the validator always writes `work_item_bundle_path` pointing at its own output bundle path, including `INVALID` and `BLOCKED` results. Preserve the current status-specific reason handling.

- [ ] **Step 2: Keep architect workflow outputs aligned**

Confirm both architect workflows still export `architecture_validation_status` and `work_item_bundle_path` from `ValidateDesignGapArchitecture`, with no new runtime-only assumptions.

- [ ] **Step 3: Re-run the architect regression**

Run: `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_gap_architect and invalid"`

Expected: PASS, with the workflow completing and exposing the invalid validation bundle instead of failing export.

### Task 3: Add Explicit Blocked Routing For Non-VALID Design Gap Drafts

**Files:**
- Modify: `workflows/examples/lisp_frontend_autonomous_drain.yaml`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml`
- Possibly create: `workflows/library/scripts/record_lisp_frontend_design_gap_architecture_blocked.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Record blocked design-gap drafting durably**

Add a deterministic helper path that reads the selector/validation bundles and records a blocked design-gap entry in run state with the drafted gap id and a stable reason when `architecture_validation_status != "VALID"`.

- [ ] **Step 2: Gate normal design-gap work-item execution**

In both drain workflows and the done-review design-gap path, run the work-item workflow only when the architect returned `VALID`. Add the alternate blocked-status path for non-`VALID` results.

- [ ] **Step 3: Keep drain-status resolution honest**

For the design-delta drain, make sure the blocked-design-gap record exists before `ResolveIterationDrainStatus` reads a `BLOCKED` normal status. For the autonomous drain, make sure the final summary sees the blocked design gap instead of an empty blocker set.

- [ ] **Step 4: Re-run the drain regression**

Run: `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_delta and design_gap and blocked"`

Expected: PASS, with a blocked drain summary and no workflow-output contract failure.

### Task 4: Verify The Narrow Surface

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Run targeted workflow runtime coverage**

Run: `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_gap_architect or design_delta"`

Expected: PASS for the architect invalid-path regression, the design-delta blocked regression, and adjacent design-delta runtime checks.

- [ ] **Step 2: Run workflow collection if any tests were added or renamed**

Run: `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py --collect-only -q`

Expected: collection succeeds for the edited module.

- [ ] **Step 3: Dry-run the repaired workflow surface**

Run: `python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run`

Expected: workflow validates successfully after the routing changes.
