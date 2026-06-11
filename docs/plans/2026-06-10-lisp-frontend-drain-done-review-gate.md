# Lisp Frontend Drain DONE Review Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the Lisp frontend design-delta drain from ending solely because the selector returns `DONE`; require a separate structured completion review and convert rejected DONE decisions into normal design-gap work.

**Architecture:** Keep selector `DONE` as a candidate terminal state, not as final authority. Add a terminal-review provider step only in the `DONE` route of `workflows/examples/lisp_frontend_design_delta_drain.yaml`. The reviewer emits `APPROVE_DONE` or `REJECT_DONE`; a deterministic adapter projects that decision into either a `DONE` selector bundle or a `DRAFT_DESIGN_GAP` selector bundle. The workflow then accepts DONE or reuses the existing design-gap architect/work-item path with the projected bundle. Do not add brittle keyword/coverage-matrix checks in this patch; the review step owns the bounded semantic judgment.

**Tech Stack:** Agent-orchestration DSL v2.14 YAML, provider output bundles, Python command adapters, pytest, orchestrator dry-run.

---

### Task 1: Add deterministic done-review projection adapter

**Files:**
- Create: `workflows/library/scripts/project_lisp_frontend_done_review.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Add tests for `APPROVE_DONE` projection to a selector bundle with `selection_status=DONE`.
- [ ] Add tests for `REJECT_DONE` projection to a selector bundle with `selection_status=DRAFT_DESIGN_GAP` and required gap fields.
- [ ] Add tests rejecting `REJECT_DONE` without required gap fields and unsafe output paths.
- [ ] Implement the adapter.
- [ ] Run the focused tests.

### Task 2: Add terminal-review prompt

**Files:**
- Create: `workflows/library/prompts/lisp_frontend_selector/review_done_design_delta.md`

- [ ] Write a prompt that asks a reviewer to verify selector `DONE` against target design, baseline, run state, manifest, and latest selection.
- [ ] Require structured JSON with `done_decision`, `review_rationale`, and gap fields when rejected.
- [ ] Ask the reviewer to identify one next bounded missing target design gap when rejecting DONE.
- [ ] Keep the prompt local to the review task; do not ask it to manage loop mechanics.

### Task 3: Wire review gate into the design-delta drain DONE route

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Add the new script and prompt to `_copy_runtime_files`.
- [ ] Add structural test asserting the `DONE` case contains `ReviewDoneDecision`, `ProjectDoneReview`, and a nested match with `DONE` and `DRAFT_DESIGN_GAP` cases.
- [ ] In the `DONE` route, replace direct `WriteDone` with:
  - provider `ReviewDoneDecision` writing `${drain_state_root}/iterations/${loop.index}/done-review.json`;
  - command `ProjectDoneReview` writing a selector bundle and output path bundle;
  - nested match on projected `selection_status`.
- [ ] In nested `DONE`, write `DONE` as before.
- [ ] In nested `DRAFT_DESIGN_GAP`, call the existing design-gap architect and work-item using the projected selection bundle.
- [ ] Run workflow structural tests.

### Task 4: Verification

**Files:**
- All changed files.

- [ ] Run `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "done_review" -q`.
- [ ] Run `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q`.
- [ ] Run `python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run` with minimal required inputs if the workflow accepts dry-run without providers; otherwise run loader/validation equivalent used by existing tests.
- [ ] Run `git diff --check`.
