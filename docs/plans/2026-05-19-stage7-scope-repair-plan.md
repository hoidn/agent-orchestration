# Stage 7 Scope Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the iteration-6 Stage 7 implementation to the approved selected-item/drain scope so the implementation review can approve and the stalled run can resume.

**Architecture:** Treat the recorded iteration-6 review decision as authoritative: the failure is scope creep, not a runtime crash. The repair removes Stage 7-only architecture-review-loop behavior from the selected-item/drain smoke surface and from the supporting workflow changes that made those smoke tests depend on unrelated design-gap-architect review logic.

**Tech Stack:** Python 3, workflow YAML, pytest runtime smoke tests, orchestrator resume flow.

---

### Task 1: Reproduce The Scope Violation In A Focused Runtime Smoke

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Tighten the selected-item Stage 7 smoke to the approved scope**

Update the selected-item smoke provider sequences so they do not include architecture-review-loop steps. The fresh-plan and approved-plan-reuse tests should only exercise:

- `SelectNextWork`
- `DraftDesignGapArchitecture`
- `DraftPlan`
- `ReviewPlan`
- `ExecuteImplementation`
- `ReviewImplementation`
- `SelectNextWork`

- [ ] **Step 2: Run the focused selected-item selector and verify it fails**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k 'selected_item_fresh_plan or selected_item_reuses_approved_plan' -q
```

Expected:

- at least one selected-item test fails because the current workflow still requires `ReviewDesignGapArchitecture` before the Stage 7 path can continue.

### Task 2: Remove The Out-Of-Scope Architecture Review Loop From The Stage 7 Surface

**Files:**
- Modify: `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
- Modify: `workflows/examples/lisp_frontend_autonomous_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Restore the design-gap architect workflow to the pre-review-loop contract**

Keep `DraftDesignGapArchitecture` plus validation, but remove the added architecture review / revise loop, review-pointer plumbing, and blocked-on-review terminal route that were not part of the approved Stage 7 plan.

- [ ] **Step 2: Restore the top-level drain workflow to the pre-review-loop routing**

Remove the Stage 7-added `when` gate on `RunDesignGapWorkItem`, the blocked/invalid design-gap recording commands, and the derived `SelectDesignGapDrainStatus` helper so the design-gap path returns to its prior Stage 7-approved behavior.

- [ ] **Step 3: Remove the runtime smoke helpers/tests that only exist for the architecture-review loop**

Delete the architecture-review helper functions and the two architecture-review runtime tests added for the out-of-scope behavior. Keep the approved selected-item/drain smoke coverage intact.

### Task 3: Verify The Approved Stage 7 Surface And Resume The Run

**Files:**
- Modify: `artifacts/work/generic-run-watchdog/repair-report.md`
- Modify: `artifacts/work/generic-run-watchdog/repair-result.json`

- [ ] **Step 1: Re-run the relevant Stage 7 selectors from the recorded check set**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_stage7_translation.py tests/test_workflow_lisp_stage7_metrics.py tests/test_lisp_frontend_autonomous_drain_runtime.py tests/test_neurips_steered_backlog_runtime.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k 'selected_item_fresh_plan or selected_item_reuses_approved_plan' -q
python -m pytest tests/test_neurips_steered_backlog_runtime.py -k 'drain_continues_to_next_iteration or drain_gap_draft or drain_blocked' -q
python -m pytest tests/test_workflow_lisp_stage7_translation.py -k 'neurips_plan_gate_resume or neurips_selected_item or neurips_remaining_drain or run_item_boundary' -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k 'resume_or_start or union_start_workflow_call' -q
python -m pytest tests/test_workflow_lisp_resource_stdlib.py -k 'finalize_selected_item' -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k 'backlog_drain or run_item_contract or providers_rebinding' -q
python -m pytest tests/test_workflow_lisp_stage7_metrics.py -q
```

Expected:

- collect-only succeeds for the Stage 7 modules
- selected-item and drain smoke selectors pass without architecture-review-loop coverage
- Stage 7 translation, stdlib, and metrics selectors remain green

- [ ] **Step 2: Write the repair report and result bundle**

Record:

- root cause from the iteration-6 review evidence
- files changed for the scope repair
- verification commands and observed pass results
- recovery action (`RESUME`)

- [ ] **Step 3: Resume the stalled run**

Run:

```bash
python -m orchestrator resume 916bf262f34e4305ab9e37a3f17262dc
```

Expected:

- the repaired run continues from the persisted state instead of relaunching from scratch.
