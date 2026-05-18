# Lisp Frontend Review/Fix Loops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real plan-review/revise and implementation-review/fix loops to the Lisp frontend autonomous drain so `REVISE` routes to corrective work instead of being recorded as accidental completion.

**Architecture:** Follow the existing NeurIPS v2.14 loop patterns: wrap plan review in a `repeat_until` loop with an approve/revise `match`, wrap completed implementation review in a `repeat_until` loop with fix and republish steps, and make the work-item workflow record completion only after approved terminal phase outputs. Keep prompts local and keep deterministic routing in YAML.

**Tech Stack:** YAML workflow DSL v2.14, existing provider prompts, existing run-state helper scripts, pytest runtime smoke tests with fake provider outputs.

---

## Reference Files

- Design: `docs/design/lisp_frontend_review_fix_loops.md`
- Plan phase to modify: `workflows/library/lisp_frontend_plan_phase.v214.yaml`
- Implementation phase to modify: `workflows/library/lisp_frontend_implementation_phase.v214.yaml`
- Work-item workflow to modify: `workflows/library/lisp_frontend_work_item.v214.yaml`
- Runtime tests to modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Existing loop references:
  - `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
  - `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
  - `workflows/library/tracked_plan_phase.yaml`
  - `workflows/library/design_plan_impl_implementation_phase.yaml`
- Existing prompts:
  - `workflows/library/prompts/lisp_frontend_plan_phase/revise_plan.md`
  - `workflows/library/prompts/lisp_frontend_implementation_phase/fix_implementation.md`

## File Structure

- `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  Owns behavioral coverage for approve, revise-then-approve, and exhausted-review paths using fake providers. Keep assertions on workflow outcomes and artifact state, not literal prompt text.

- `workflows/library/lisp_frontend_plan_phase.v214.yaml`
  Owns the plan draft/review/revise phase. It should expose final plan outputs through a finalization step after a review loop.

- `workflows/library/lisp_frontend_implementation_phase.v214.yaml`
  Owns execute/check/review/fix for implementation. It should review/fix only completed implementation attempts and emit `NOT_APPLICABLE` for blocked implementation attempts.

- `workflows/library/lisp_frontend_work_item.v214.yaml`
  Owns terminal item routing. It decides whether to record completed or blocked state based on final phase outputs.

- `workflows/library/prompts/lisp_frontend_plan_phase/revise_plan.md`
  Modify only if fake/live provider evidence shows ambiguity. The first pass should not need prompt edits.

- `workflows/library/prompts/lisp_frontend_implementation_phase/fix_implementation.md`
  Modify only if fake/live provider evidence shows ambiguity. The first pass should not need prompt edits.

## Task 1: Add Failing Runtime Tests For Plan Revision

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add fake provider helpers for plan revise paths**

Add helper writers near `_write_plan_review`:

```python
def _write_plan_review_revise_once(workspace: Path) -> None:
    root = _pending_plan_review_root(workspace)
    target = workspace / (root / "plan_review_report_path.txt").read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"decision": "REVISE", "findings": [{"id": "P1"}]}) + "\n", encoding="utf-8")
    (root / "plan_review_decision.txt").write_text("REVISE\n", encoding="utf-8")


def _revise_plan(workspace: Path) -> None:
    for pointer in sorted(workspace.glob("state/**/plan-phase/plan_path.txt")):
        target = workspace / pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Lisp Work Plan\n\nRevised after review.\n", encoding="utf-8")
        return
    raise AssertionError("No plan pointer found")
```

If `_pending_plan_review_root` does not exist, factor the existing search logic
from `_write_plan_review` into a helper that returns the first plan-phase root
whose `plan_review_decision.txt` is absent.

- [ ] **Step 2: Add a revise-then-approve plan test**

Add:

```python
def test_lisp_frontend_plan_review_revise_then_approve(tmp_path):
    ...
```

Use provider sequence:

```python
[
    ("SelectNextWork", _write_selector_design_gap),
    ("DraftDesignGapArchitecture", _write_design_gap_architecture),
    ("DraftPlan", _write_plan),
    ("ReviewPlan", _write_plan_review_revise_once),
    ("RevisePlan", _revise_plan),
    ("ReviewPlan", _write_plan_review),
    ("ExecuteImplementation", _write_execution_state),
    ("ReviewImplementation", _write_implementation_review),
    ("SelectNextWork", _write_selector_done),
]
```

Assert:

- provider calls include `RevisePlan`;
- final drain summary is `DONE`;
- completed design gaps contain `parser-syntax`.

- [ ] **Step 3: Run the failing test**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_plan_review_revise_then_approve -q
```

Expected before implementation: failure because `RevisePlan` is never called
or because completion happens despite the first `REVISE`.

## Task 2: Add Plan Review Loop

**Files:**
- Modify: `workflows/library/lisp_frontend_plan_phase.v214.yaml`

- [ ] **Step 1: Wrap plan review in `PlanReviewLoop`**

Replace the single `ReviewPlan` step with:

```yaml
- name: PlanReviewLoop
  id: plan_review_loop
  repeat_until:
    id: plan_review_iteration
    max_iterations: 12
    outputs:
      review_decision:
        kind: scalar
        type: enum
        allowed: ["APPROVE", "REVISE"]
        from:
          ref: self.steps.RoutePlanDecision.artifacts.review_decision
    condition:
      compare:
        left:
          ref: self.outputs.review_decision
        op: eq
        right: APPROVE
    steps:
      - name: ReviewPlan
        id: review_plan
        ...
      - name: RoutePlanDecision
        id: route_plan_decision
        match:
          ref: self.steps.ReviewPlan.artifacts.plan_review_decision
          cases:
            APPROVE: ...
            REVISE: ...
```

Use `neurips_backlog_seeded_plan_phase.v214.yaml` as the exact structural
reference.

- [ ] **Step 2: Publish review outputs from `ReviewPlan`**

Inside loop `ReviewPlan`, keep existing expected outputs and add:

```yaml
publishes:
  - artifact: plan_review_report
    from: plan_review_report_path
  - artifact: plan_review_decision
    from: plan_review_decision
```

- [ ] **Step 3: Add `RevisePlan` under the `REVISE` case**

Add:

```yaml
- name: RevisePlan
  id: revise_plan
  provider: codex
  asset_file: prompts/lisp_frontend_plan_phase/revise_plan.md
  timeout_sec: 3600
  consumes:
    - artifact: full_design
      policy: latest_successful
      freshness: any
    - artifact: mvp_design
      policy: latest_successful
      freshness: any
    - artifact: work_item_context
      policy: latest_successful
      freshness: any
    - artifact: plan
      policy: latest_successful
      freshness: any
    - artifact: plan_review_report
      policy: latest_successful
      freshness: since_last_consume
  prompt_consumes: ["full_design", "mvp_design", "work_item_context", "plan", "plan_review_report"]
  expected_outputs:
    - name: plan_path
      path: ${inputs.state_root}/plan_path.txt
      type: relpath
      under: docs/plans
      must_exist_target: true
  publishes:
    - artifact: plan
      from: plan_path
```

- [ ] **Step 4: Route loop decisions**

Under `APPROVE`, write scalar `review_decision=APPROVE`.

Under `REVISE`, run `RevisePlan`, then write scalar
`review_decision=REVISE`.

- [ ] **Step 5: Add `FinalizePlanPhaseOutputs`**

Add a finalization command that copies:

- `${inputs.state_root}/plan_path.txt` to
  `${inputs.state_root}/final_plan_path.txt`
- `${inputs.state_root}/plan_review_report_path.txt` to
  `${inputs.state_root}/final_plan_review_report_path.txt`
- `${inputs.state_root}/plan_review_decision.txt` to
  `${inputs.state_root}/final_plan_review_decision.txt`

Expose expected outputs:

- `plan_path`
- `plan_review_report_path`
- `plan_review_decision`

- [ ] **Step 6: Point phase outputs to finalizer**

Change top-level `outputs` refs to:

```yaml
root.steps.FinalizePlanPhaseOutputs.artifacts.plan_path
root.steps.FinalizePlanPhaseOutputs.artifacts.plan_review_report_path
root.steps.FinalizePlanPhaseOutputs.artifacts.plan_review_decision
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_plan_review_revise_then_approve -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q
```

Expected: both pass.

## Task 3: Add Failing Runtime Tests For Implementation Fix

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add fake provider helpers for implementation fix paths**

Add helpers:

```python
def _write_implementation_review_revise_once(workspace: Path) -> None:
    root = _pending_implementation_review_root(workspace)
    target = workspace / (root / "implementation_review_report_path.txt").read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Implementation Review\n\nRevise required.\n", encoding="utf-8")
    (root / "implementation_review_decision.txt").write_text("REVISE\n", encoding="utf-8")


def _fix_implementation(workspace: Path) -> None:
    for pointer in sorted(workspace.glob("state/**/implementation-phase/execution_report_target_path.txt")):
        target = workspace / pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Execution Report\n\nFixed after review.\n", encoding="utf-8")
        return
    raise AssertionError("No execution report target pointer found")
```

Factor `_pending_implementation_review_root` from `_write_implementation_review`.

- [ ] **Step 2: Add a revise-then-approve implementation test**

Add:

```python
def test_lisp_frontend_implementation_review_revise_then_approve(tmp_path):
    ...
```

Use provider sequence:

```python
[
    ("SelectNextWork", _write_selector_design_gap),
    ("DraftDesignGapArchitecture", _write_design_gap_architecture),
    ("DraftPlan", _write_plan),
    ("ReviewPlan", _write_plan_review),
    ("ExecuteImplementation", _write_execution_state),
    ("ReviewImplementation", _write_implementation_review_revise_once),
    ("FixImplementation", _fix_implementation),
    ("ReviewImplementation", _write_implementation_review),
    ("SelectNextWork", _write_selector_done),
]
```

Assert:

- provider calls include `FixImplementation`;
- final drain summary is `DONE`;
- completed design gaps contain `parser-syntax`;
- final execution report contains `Fixed after review`.

- [ ] **Step 3: Run the failing test**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_implementation_review_revise_then_approve -q
```

Expected before implementation: failure because `FixImplementation` is never
called or the stale first-pass report is final.

## Task 4: Add Implementation Review/Fix Loop

**Files:**
- Modify: `workflows/library/lisp_frontend_implementation_phase.v214.yaml`

- [ ] **Step 1: Publish `execution_report` from completed implementation**

After `ExecuteImplementation`, add a `match` over
`implementation_state` or a completed-only publish step with
`requires_variant` so `execution_report` is available for checks/review.

Use the NeurIPS v2.14 `PublishExecutionReport` pattern if possible.

- [ ] **Step 2: Replace one-pass `RunChecks` and `ReviewImplementation` with `ImplementationReviewLoop`**

Add:

```yaml
- name: ImplementationReviewLoop
  id: implementation_review_loop
  repeat_until:
    id: implementation_review_iteration
    max_iterations: 40
    outputs:
      review_decision:
        kind: scalar
        type: enum
        allowed: ["APPROVE", "REVISE"]
        from:
          ref: self.steps.RouteIterationWork.artifacts.review_decision
    condition:
      compare:
        left:
          ref: self.outputs.review_decision
        op: eq
        right: APPROVE
    steps:
      - name: RouteIterationWork
        id: route_iteration_work
        match:
          ref: parent.steps.ExecuteImplementation.artifacts.implementation_state
          cases:
            COMPLETED: ...
            BLOCKED: ...
```

- [ ] **Step 3: In the `COMPLETED` case, run checks and review**

Use the existing `RunChecks` command, but publish:

```yaml
publishes:
  - artifact: checks_report
    from: checks_report_path
```

Then run `ReviewImplementation` with prompt consumes:

```yaml
["full_design", "mvp_design", "plan", "execution_report", "checks_report"]
```

If the prompt currently does not consume `execution_report` and
`checks_report`, add these consumes so the review sees concrete evidence.

- [ ] **Step 4: Add `FixImplementation` under `REVISE`**

Add a provider step:

```yaml
- name: FixImplementation
  id: fix_implementation
  when:
    compare:
      left:
        ref: self.steps.ReviewImplementation.artifacts.implementation_review_decision
      op: eq
      right: REVISE
  provider: ${inputs.implementation_execute_provider}
  asset_file: prompts/lisp_frontend_implementation_phase/fix_implementation.md
  timeout_sec: 7200
  consumes:
    - artifact: full_design
      policy: latest_successful
      freshness: any
    - artifact: mvp_design
      policy: latest_successful
      freshness: any
    - artifact: plan
      policy: latest_successful
      freshness: any
    - artifact: execution_report
      policy: latest_successful
      freshness: any
    - artifact: checks_report
      policy: latest_successful
      freshness: any
    - artifact: implementation_review_report
      policy: latest_successful
      freshness: since_last_consume
  prompt_consumes: ["full_design", "mvp_design", "plan", "execution_report", "checks_report", "implementation_review_report"]
```

- [ ] **Step 5: Republish updated execution report under `REVISE`**

After `FixImplementation`, add `PublishUpdatedExecutionReport` when decision is
`REVISE`. It should write `${inputs.execution_report_target_path}` to
`${inputs.state_root}/execution_report_path.txt` and publish `execution_report`.

- [ ] **Step 6: Route loop decisions**

Add `WriteLoopReviewDecision` to copy `implementation_review_decision.txt` to
`loop_review_decision.txt` with expected output `review_decision`.

For the `BLOCKED` implementation-state case, write scalar
`review_decision=APPROVE` so the loop terminates without review.

- [ ] **Step 7: Add or update `FinalizeImplementationPhaseOutputs`**

Ensure finalizer validates:

- `implementation_state == COMPLETED` requires final execution report, checks
  report, implementation review report, and decision `APPROVE` or `REVISE`;
- `implementation_state == BLOCKED` writes `NOT_APPLICABLE` for review
  decision and exposes progress report.

Expose top-level outputs from the finalizer.

- [ ] **Step 8: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_implementation_review_revise_then_approve -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q
```

Expected: both pass.

## Task 5: Add Work-Item Terminal Routing Tests

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add plan-exhaustion test with low max-iteration fixture**

If changing `max_iterations` only for tests is awkward, use a small fixture copy
of the workflow in the temp workspace and rewrite `max_iterations: 12` to
`max_iterations: 2` before loading.

Add:

```python
def test_lisp_frontend_plan_review_exhaustion_records_blocked(tmp_path):
    ...
```

Provider sequence should make plan review write `REVISE` every time and revise
the plan each time.

Assert:

- drain summary is `BLOCKED` or run state has the item under
  `blocked_design_gaps`;
- completed design gaps does not contain `parser-syntax`.

- [ ] **Step 2: Add implementation-exhaustion test**

Add:

```python
def test_lisp_frontend_implementation_review_exhaustion_records_blocked(tmp_path):
    ...
```

Use low max iteration fixture and make implementation review write `REVISE`
every time.

Assert:

- blocked design gaps contains `parser-syntax`;
- completed design gaps does not contain `parser-syntax`.

- [ ] **Step 3: Run tests and verify they fail before work-item routing**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "exhaustion" -q
```

Expected before work-item routing changes: failure because work items still
record completion or because phase outputs do not expose terminal revise state
cleanly.

## Task 6: Fix Work-Item Terminal Routing

**Files:**
- Modify: `workflows/library/lisp_frontend_work_item.v214.yaml`

- [ ] **Step 1: Route after `RunPlanPhase`**

Wrap implementation and terminal recording in a `match` over:

```yaml
root.steps.RunPlanPhase.artifacts.plan_review_decision
```

`APPROVE` runs implementation. `REVISE` records blocked with reason
`plan_review_exhausted`.

- [ ] **Step 2: Route after `RunImplementationPhase`**

Inside the plan-approved branch, route on
`implementation_state`.

For `BLOCKED`, record blocked with reason `implementation_blocked`.

For `COMPLETED`, route on `implementation_review_decision`.

`APPROVE` records completed. `REVISE` records blocked with reason
`implementation_review_exhausted`.

- [ ] **Step 3: Use existing run-state script for blocked records**

Add command steps that invoke:

```bash
python workflows/library/scripts/update_lisp_frontend_run_state.py \
  --state-path ${inputs.run_state_path} \
  blocked \
  --item-id ${steps.ResolveWorkItemInputs.artifacts.work_item_id} \
  --source ${steps.ResolveWorkItemInputs.artifacts.work_item_source} \
  --reason plan_review_exhausted \
  --summary-path ${steps.ResolveWorkItemInputs.artifacts.item_summary_target_path} \
  --summary-pointer-path ${inputs.state_root}/item_summary_path.txt \
  --drain-status-path ${inputs.state_root}/drain_status.txt
```

Use the corresponding reason for implementation states.

- [ ] **Step 4: Make workflow outputs point at the routed terminal step**

If output refs cannot point to a branch-local step directly, add a final
`FinalizeWorkItemOutcome` command that validates and republishes:

- `${inputs.state_root}/drain_status.txt`
- `${inputs.state_root}/item_summary_path.txt`

Then point `outputs.drain_status` and `outputs.item_summary_path` at that
finalizer.

- [ ] **Step 5: Run exhaustion tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "exhaustion" -q
```

Expected: pass.

## Task 7: Full Focused Verification

**Files:**
- All files modified in prior tasks.

- [ ] **Step 1: Run collect-only for changed test module**

Run:

```bash
python -m pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: collection succeeds and includes the new revise/exhaustion tests.

- [ ] **Step 2: Run full Lisp autonomous drain runtime tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run workflow load/dry-run smoke if available**

Run:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_autonomous_drain.yaml \
  --input steering_path=docs/steering.md \
  --dry-run
```

Expected: workflow validates without executing providers.

If `--dry-run` is unavailable for this command, run the existing loader test
instead and record that limitation.

- [ ] **Step 4: Run diff check**

Run:

```bash
git diff --check -- \
  workflows/library/lisp_frontend_plan_phase.v214.yaml \
  workflows/library/lisp_frontend_implementation_phase.v214.yaml \
  workflows/library/lisp_frontend_work_item.v214.yaml \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
```

Expected: no output.

- [ ] **Step 5: Commit**

Stage only the loop/routing implementation and tests:

```bash
git add \
  workflows/library/lisp_frontend_plan_phase.v214.yaml \
  workflows/library/lisp_frontend_implementation_phase.v214.yaml \
  workflows/library/lisp_frontend_work_item.v214.yaml \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Add Lisp frontend review fix loops"
```

Do not stage unrelated backlog, dashboard, v2.14, or generated workflow-output
changes.

## Acceptance Checklist

- [ ] Plan review `REVISE` triggers `RevisePlan`.
- [ ] Implementation review `REVISE` triggers `FixImplementation`.
- [ ] Updated plan is reviewed again after revision.
- [ ] Updated execution report is republished and reviewed again after fix.
- [ ] Work item completion requires final implementation approval.
- [ ] Plan loop exhaustion records blocked state.
- [ ] Implementation loop exhaustion records blocked state.
- [ ] Existing approve-path smoke tests still pass.
