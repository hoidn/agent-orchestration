# Idempotent Prerequisite Block Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make blocked design-gap recovery the default behavior by ensuring `PREREQUISITE_GAP_REQUIRED` enters a durable recovery path that can revise the target design and draft/select the prerequisite gap instead of terminating the drain because of one classifier enum.

**Architecture:** Keep recovery-before-selection as the drain invariant, but split the prerequisite route into explicit recovery states. A prerequisite blocker first becomes a target-design-revision problem when the prerequisite gap is outside the current target design scope; after the target design is revised and approved, the original blocked gap remains visible while a prerequisite-selection branch calls the existing selector prompt to draft/select prerequisite work. Only `TERMINAL_BLOCKED` may end the drain.

**Tech Stack:** Workflow YAML v2.14, Python command adapters under `workflows/library/scripts/`, provider prompts, pytest contract tests, orchestrator dry-run validation.

---

## Contract

- A blocked design gap remains in `blocked_design_gaps` until a successful retry clears it or a true terminal blocker is recorded.
- `PREREQUISITE_GAP_REQUIRED` is recoverable. It is not equivalent to terminal `BLOCKED`.
- If the prerequisite gap does not already exist in the target design scope, recovery must route through target-design revision so the target design can add or decompose the missing prerequisite gap.
- After approved target-design revision, the original blocked gap remains durable, but its recovery state changes to prerequisite work pending. The next drain action uses a recovery-specific selector branch that calls the existing selector prompt with that run-state context so it may draft/select the prerequisite gap as recovery work rather than selecting unrelated normal work.
- `SELECT_PREREQUISITE_WORK` is a first-class pre-selection route. It calls the existing selector prompt with prerequisite recovery context; it is not equivalent to ordinary `SELECT_NORMAL_WORK`.
- `SELECT_PREREQUISITE_WORK` may pass through `CONTINUE` from actually selected prerequisite work, but selector `DONE` or `BLOCKED` must fail closed to drain `BLOCKED` until prerequisite satisfaction recording exists.
- Unknown, malformed, or unsupported recovery metadata fails closed with visible blocked state. Only `TERMINAL_BLOCKED` may intentionally terminate the drain.
- This slice intentionally does not add a deterministic prerequisite scheduler. It must prevent premature terminal block and provide a durable state transition that lets the existing selector/design-gap drafting path pursue the prerequisite as recovery work.
- Retrying the original gap after prerequisite completion requires a later structured satisfaction contract unless the implementation also records and validates which selected prerequisite satisfied the waiting gap.

## State Model

Extend each recoverable `blocked_design_gaps[gap_id]` record with optional fields:

- `recovery_route`: existing classifier route.
- `recovery_reason`: existing classifier reason.
- `recovery_status`:
  - `CLASSIFIED`: the block has been classified but no recovery action has completed.
  - `TARGET_DESIGN_REVISION_REQUIRED`: prerequisite recovery needs target-design scope update.
  - `PREREQUISITE_WORK_PENDING`: target design is updated or already sufficient; a prerequisite gap should be drafted/selected before retrying the original gap.
  - `RETRY_READY`: prerequisite has completed or the gap design was revised; retry the original blocked gap.
  - `TERMINAL_BLOCKED`: true terminal block.
- `recovery_event_id`: stable event id for idempotence.
- `prerequisite_gap_hint`: optional short text or id from the classifier/revision report; advisory, not a required scheduler contract.
- `prerequisite_selection_bundle_path`: optional path to the selector bundle that chose prerequisite work.
- `waiting_on_prerequisite_gap_id`: optional selected prerequisite id when a selector bundle identifies one.
- `prerequisite_recovery_status`: optional status for the selected prerequisite work, such as `SELECTED`, `RUNNING`, `COMPLETED`, `BLOCKED`, or `DECLINED`.
- `original_blocked_gap_id`: optional explicit self-link for prerequisite work that is run on behalf of a different blocked gap.

The detector must use this durable state before normal selection. For `PREREQUISITE_WORK_PENDING`, it should emit a prerequisite-selection route that calls the existing selector prompt with recovery context in run state, not terminal block.

## Task 1: Add Failing Script-Level Regression Coverage

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Use: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Use: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`

- [ ] Add a test that records `PREREQUISITE_GAP_REQUIRED` through `record_lisp_frontend_blocked_recovery_outcome.py` with `--terminal-action continue`.
- [ ] Assert the recorder writes drain status `CONTINUE`, not `BLOCKED`.
- [ ] Assert `run_state.json` still contains the original blocked design gap with `reason: implementation_blocked`, `recovery_route: PREREQUISITE_GAP_REQUIRED`, and nonterminal `recovery_status`.
- [ ] Immediately run `detect_lisp_frontend_blocked_design_gap_recovery.py` against that state and assert it emits a recovery route rather than `SELECT_NORMAL_WORK` or terminal `BLOCKED`.
- [ ] Run the new test and confirm it fails before implementation.

## Task 2: Route Prerequisite Blocks Through Target-Design Revision When Scope Is Missing

**Files:**

- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_prior_blocked_design_gap.md`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Update `ReviseBlockedDesignGap` routing so `PREREQUISITE_GAP_REQUIRED` can use the target-design revision path when the missing prerequisite is outside current target-design scope.
- [ ] Update the revision prompt so `PREREQUISITE_GAP_REQUIRED` means: update the target design only enough to add/decompose the missing prerequisite gap, while keeping the baseline unchanged.
- [ ] Keep `GAP_DESIGN_REVISION_REQUIRED` scoped to the selected gap architecture/plan.
- [ ] Keep `TARGET_DESIGN_REVISION_REQUIRED` scoped to the target design.
- [ ] Add a structure test that `ReviseBlockedDesignGap` accepts `PREREQUISITE_GAP_REQUIRED` as a revision route, not only `TARGET_DESIGN_REVISION_REQUIRED` and `GAP_DESIGN_REVISION_REQUIRED`.

## Task 3: Change Recorder Semantics For Prerequisite Recovery

**Files:**

- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Modify if needed: `workflows/library/scripts/update_lisp_frontend_run_state.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Add or preserve a durable blocked-state update for `PREREQUISITE_GAP_REQUIRED`.
- [ ] When no revision report exists yet, write nonterminal `CONTINUE` and set `recovery_status: TARGET_DESIGN_REVISION_REQUIRED` or equivalent durable state.
- [ ] When target-design revision is approved, keep the original blocked gap and write nonterminal `CONTINUE` with `recovery_status: PREREQUISITE_WORK_PENDING`.
- [ ] Do not write `RUN_RECOVERED_GAP` for prerequisite recovery until the prerequisite work has actually completed or the original gap is retry-ready.
- [ ] Preserve terminal `BLOCKED` for `TERMINAL_BLOCKED` and explicit `--terminal-action block`.
- [ ] Keep summary/run-state semantics stable: `reason` in blocked state remains `implementation_blocked`; the classifier cause belongs in `recovery_reason`.

## Task 4: Let The Drain Draft Or Select The Prerequisite As Recovery Work

**Files:**

- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `workflows/library/scripts/prepare_lisp_frontend_iteration_paths.py`
- Modify if needed: `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
- Modify if needed: `workflows/library/lisp_frontend_design_delta_selector.v214.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Teach the detector to distinguish the original blocked gap from prerequisite work pending.
- [ ] For `PREREQUISITE_WORK_PENDING`, preserve the blocked obligation in run state, but route through a prerequisite-selection branch that lets the selector/design-gap drafting path choose the prerequisite gap as recovery work.
- [ ] Make `SELECT_PREREQUISITE_WORK` an explicit detector output, workflow match case, resolver route, and acceptance-test route.
- [ ] In the resolver, map `SELECT_PREREQUISITE_WORK` selected-work `CONTINUE` to `CONTINUE`, and selector `DONE`/`BLOCKED` to `BLOCKED`.
- [ ] Ensure selector context includes the blocked gap and prerequisite hint through existing run-state inputs; do not create a second selector contract in Python.
- [ ] Add a test that a prerequisite-pending blocked gap does not produce terminal `BLOCKED`.
- [ ] Add a prompt/structure assertion that the selector treats prerequisite recovery as related work and should not pick unrelated work while a prerequisite is pending.

## Task 5: Preserve Retry Of The Original Gap

**Files:**

- Modify if needed: `workflows/library/scripts/update_lisp_frontend_run_state.py`
- Modify if needed: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] If this slice implements prerequisite satisfaction, record the selector bundle or selected prerequisite id/path under the original blocked gap.
- [ ] If this slice implements prerequisite satisfaction, when the selected prerequisite completes, update the original blocked gap to `RETRY_READY` rather than clearing it.
- [ ] If this slice implements prerequisite satisfaction, ensure the next recovery iteration retries the original blocked gap through the existing recovered-gap work-item path.
- [ ] Clear the original blocked state only after the original gap retry completes successfully.
- [ ] If the prerequisite itself blocks, keep both the prerequisite block and the original blocked obligation visible.

If the implementation does not add structured prerequisite satisfaction and
retry mechanics, leave the original gap in `PREREQUISITE_WORK_PENDING` and record
that retry-after-prerequisite remains follow-up work. Do not silently mark the
original gap retry-ready from selector prose alone.

The follow-up satisfaction recorder/validator should consume the prerequisite
selection bundle, selected work status, original blocked gap id, and run state.
It is the owner for changing `PREREQUISITE_WORK_PENDING` to `RETRY_READY`.

## Task 6: Validate Workflow

**Files:**

- Validate: `workflows/examples/lisp_frontend_design_delta_drain.yaml`

- [ ] Run `python -m pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q` if tests were added or renamed.
- [ ] Run `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q`.
- [ ] Run the closest `python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run ...` command with the required inputs used by the existing drain smoke.
- [ ] Run `git diff --check` on modified files.

## Follow-Up Work

This plan intentionally does not implement a deterministic prerequisite scheduler. If prompt-only prerequisite selection proves insufficient, add a follow-up design for improving selector context or typed prerequisite metadata. Do not fall back to terminal `BLOCKED` merely because the prerequisite gap was not already present.
