# Non-Progress Revision Reblock Handling Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generic non-progress detection treat a revision followed by the same work blocking again as unresolved churn, not as successful progress.

**Architecture:** Keep routing deterministic in `evaluate_workflow_non_progress.py`. A revision event remains progress only if it is not later contradicted by another blocked event for the same work item. This avoids target-specific intervention while preserving genuine revision progress.

**Tech Stack:** Python workflow helper scripts and pytest.

---

### Task 1: Add generic revision-reblock detection

**Files:**
- Modify: `workflows/library/scripts/evaluate_workflow_non_progress.py`
- Modify: `tests/test_workflow_non_progress_recovery.py`

- [ ] Add tests where blocked -> plan revised -> same work blocked triggers `STEP_BACK_REQUIRED`.
- [ ] Add a control test where a revision followed by different work does not trigger the same-work reblock.
- [ ] Implement revision reset logic so revisions do not truncate unresolved history when later contradicted by a same-work block.
- [ ] Run the focused test module.

### Task 2: Wire generic non-progress into drain pre-selection

**Files:**
- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Let blocked-gap recovery detection consume an optional non-progress decision.
- [ ] When that decision is `STEP_BACK_REQUIRED`, emit a generic `BLOCKED` pre-selection bundle instead of retrying a blocked work item.
- [ ] Project/evaluate progress signals before blocked recovery detection in the drain loop.
- [ ] Record step-back outcome for generic non-progress blocks and let iteration status prefer the step-back drain status.
- [ ] Run focused unit tests and workflow dry-run validation.
