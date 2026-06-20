# Workflow Step-Back Non-Progress Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a general workflow-control mechanism that detects repeated non-progress and routes to a deliberate step-back/replanning phase before the workflow keeps selecting more local work.

**Architecture:** Deterministic scripts collect generic progress signals, evaluate non-progress thresholds, and route the workflow to either normal selection or a step-back diagnosis branch. A provider may diagnose strategy only after deterministic triggers fire; the workflow owns counters, stale-artifact checks, routing, and state recording. The first integration is the Lisp frontend drain, but the data model and scripts are workflow-agnostic.

**Tech Stack:** Python command adapters, YAML v2.14 workflows, provider `output_bundle` contracts, pytest, Markdown docs.

---

## Design Summary

The workflow should not continue normal iteration when it is plainly not making progress. Add a generic "step back" control loop:

```text
iteration result / run state / artifact provenance
-> generic progress signal summary
-> deterministic non-progress evaluator
-> NORMAL_CONTINUE | STEP_BACK_REQUIRED | TERMINAL_HUMAN_DECISION
-> bounded step-back diagnosis
-> structured recovery action
-> run-state event
-> normal selector resumes only after recovery action is recorded
```

This is intentionally not tied to YAML, Workflow Lisp, old writers, or any project-specific target. It triggers on patterns such as repeated blocker fingerprints, repeated no-commit/no-accepted-artifact iterations, repeated prerequisite generation, stale artifact provenance, plan churn without outcome change, or review findings that do not converge.

## File Structure

- Create `workflows/library/scripts/evaluate_workflow_non_progress.py`
  - Pure deterministic evaluator over a generic JSON signal document.
  - Emits a structured decision bundle.
- Create `workflows/library/scripts/project_lisp_frontend_progress_signals.py`
  - Thin adapter from the existing Lisp drain run state and iteration artifacts into the generic signal schema.
  - This is the only Lisp-specific projection in the first integration.
- Create `workflows/library/scripts/record_workflow_step_back_outcome.py`
  - Records a generic step-back outcome in a run-state JSON file.
- Create `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`
  - Provider prompt for bounded strategic diagnosis after deterministic trigger.
- Modify `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Insert signal projection and non-progress evaluation before normal selection/recovery.
  - Add a `STEP_BACK_REQUIRED` branch that runs the diagnosis and records the action.
- Modify `workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py`
  - Recognize a step-back route as `CONTINUE` after recording the outcome, unless the outcome asks for terminal human review.
- Modify `workflows/library/scripts/update_lisp_frontend_run_state.py`
  - Preserve generic `step_back_events` in the existing run state.
- Add `tests/test_workflow_non_progress_recovery.py`
  - Unit tests for generic evaluator and recorder.
- Modify `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Workflow integration tests proving the Lisp drain routes through step-back after repeated non-progress.
- Modify `docs/workflow_drafting_guide.md`
  - Add a general authoring rule for non-progress step-back loops.

## Generic Signal Schema

Use this initial schema, deliberately small:

```json
{
  "schema": "workflow_progress_signals/v1",
  "run_id": "20260619T194555Z-a3l5kf",
  "current_iteration": 12,
  "events": [
    {
      "iteration": 10,
      "work_item_id": "some-item",
      "phase": "implementation",
      "outcome": "blocked",
      "accepted_change": false,
      "commit_hash": "",
      "blocker_fingerprint": "implementation_blocked:contract_gap:abc123",
      "review_finding_fingerprints": ["high:missing-contract:abc123"],
      "prerequisite_generated": true,
      "plan_revised": true,
      "stale_artifact_detected": false
    }
  ]
}
```

Use this decision schema:

```json
{
  "schema": "workflow_non_progress_decision/v1",
  "route": "NORMAL_CONTINUE",
  "trigger_codes": [],
  "failure_fingerprint": "",
  "evidence": {},
  "recommended_step_back_focus": ""
}
```

Routes:

- `NORMAL_CONTINUE`
- `STEP_BACK_REQUIRED`
- `TERMINAL_HUMAN_DECISION`

Trigger codes:

- `same_blocker_repeated`
- `same_work_item_repeatedly_blocked`
- `no_accepted_change_streak`
- `prerequisite_chain_growth`
- `plan_churn_without_outcome_change`
- `review_findings_not_converging`
- `stale_artifact_provenance`
- `selector_reselected_non_progress_item`

## Task 1: Add Generic Non-Progress Evaluator Tests

**Files:**
- Create: `tests/test_workflow_non_progress_recovery.py`

- [ ] **Step 1: Write failing tests for repeated blockers**

Add tests:

```python
def test_evaluator_requires_step_back_for_repeated_blocker(tmp_path):
    signals = {
        "schema": "workflow_progress_signals/v1",
        "run_id": "run-1",
        "current_iteration": 3,
        "events": [
            {
                "iteration": 1,
                "work_item_id": "item-a",
                "phase": "implementation",
                "outcome": "blocked",
                "accepted_change": False,
                "commit_hash": "",
                "blocker_fingerprint": "same-blocker",
                "review_finding_fingerprints": [],
                "prerequisite_generated": False,
                "plan_revised": False,
                "stale_artifact_detected": False,
            },
            {
                "iteration": 2,
                "work_item_id": "item-a",
                "phase": "implementation",
                "outcome": "blocked",
                "accepted_change": False,
                "commit_hash": "",
                "blocker_fingerprint": "same-blocker",
                "review_finding_fingerprints": [],
                "prerequisite_generated": False,
                "plan_revised": False,
                "stale_artifact_detected": False,
            },
        ],
    }
    decision = evaluate_non_progress(signals, repeated_blocker_threshold=2)
    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "same_blocker_repeated" in decision["trigger_codes"]
```

Also test `no_accepted_change_streak`, `prerequisite_chain_growth`, and `stale_artifact_provenance`.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_workflow_non_progress_recovery.py -q
```

Expected: FAIL because `workflows.library.scripts.evaluate_workflow_non_progress` does not exist.

## Task 2: Implement Generic Non-Progress Evaluator

**Files:**
- Create: `workflows/library/scripts/evaluate_workflow_non_progress.py`
- Test: `tests/test_workflow_non_progress_recovery.py`

- [ ] **Step 1: Implement pure evaluator function**

Implement:

```python
def evaluate_non_progress(
    signals: Mapping[str, Any],
    *,
    repeated_blocker_threshold: int = 2,
    no_accepted_change_threshold: int = 3,
    prerequisite_chain_threshold: int = 2,
    plan_churn_threshold: int = 2,
    finding_repeat_threshold: int = 2,
) -> dict[str, Any]:
    ...
```

Rules:

- Ignore events with a different or missing `run_id`.
- Trigger `same_blocker_repeated` when the same non-empty blocker fingerprint occurs at least threshold times.
- Trigger `same_work_item_repeatedly_blocked` when the same work item blocks at least threshold times.
- Trigger `no_accepted_change_streak` when the latest N events have no accepted change and no commit hash.
- Trigger `prerequisite_chain_growth` when latest N events generated prerequisites.
- Trigger `plan_churn_without_outcome_change` when latest N events revise plans and still block.
- Trigger `review_findings_not_converging` when the same finding fingerprint recurs at least threshold times.
- Trigger `stale_artifact_provenance` immediately when any latest event reports stale artifact provenance.

- [ ] **Step 2: Implement CLI**

CLI:

```bash
python workflows/library/scripts/evaluate_workflow_non_progress.py \
  --signals path/to/signals.json \
  --output path/to/non-progress-decision.json \
  --repeated-blocker-threshold 2 \
  --no-accepted-change-threshold 3
```

Output bundle must include:

- `route`
- `trigger_codes`
- `failure_fingerprint`
- `recommended_step_back_focus`

- [ ] **Step 3: Run unit tests**

Run:

```bash
pytest tests/test_workflow_non_progress_recovery.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Commit only the evaluator and tests:

```bash
git add workflows/library/scripts/evaluate_workflow_non_progress.py tests/test_workflow_non_progress_recovery.py
git commit -m "Add generic workflow non-progress evaluator"
```

## Task 3: Add Step-Back Outcome Recorder

**Files:**
- Modify: `tests/test_workflow_non_progress_recovery.py`
- Create: `workflows/library/scripts/record_workflow_step_back_outcome.py`

- [ ] **Step 1: Write failing recorder tests**

Test that the recorder appends a `step_back` event to a generic state file and writes a summary bundle.

Expected fields:

- `event: "step_back"`
- `run_id`
- `iteration`
- `trigger_codes`
- `failure_fingerprint`
- `decision`
- `action`
- `timestamp_utc`

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_workflow_non_progress_recovery.py -k record_step_back -q
```

Expected: FAIL because recorder does not exist.

- [ ] **Step 3: Implement recorder**

CLI:

```bash
python workflows/library/scripts/record_workflow_step_back_outcome.py \
  --state-path state/run_state.json \
  --decision-path state/iterations/12/non-progress-decision.json \
  --diagnosis-path state/iterations/12/step-back-diagnosis.json \
  --summary-path artifacts/work/iterations/12/step-back-summary.json \
  --drain-status-path state/iterations/12/step-back-drain-status.txt
```

Accepted diagnosis actions:

- `REDRAFT_PLAN`
- `REVISE_REQUIREMENTS`
- `SPLIT_WORK_ITEM`
- `DROP_OR_DEMOTE_WORK_ITEM`
- `FIX_WORKFLOW_MECHANICS`
- `CONTINUE_WITH_CURRENT_PLAN`
- `NEEDS_HUMAN_DECISION`

Drain status:

- `NEEDS_HUMAN_DECISION` -> `BLOCKED`
- all other actions -> `CONTINUE`

- [ ] **Step 4: Run recorder tests**

Run:

```bash
pytest tests/test_workflow_non_progress_recovery.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/record_workflow_step_back_outcome.py tests/test_workflow_non_progress_recovery.py
git commit -m "Record workflow step-back recovery outcomes"
```

## Task 4: Project Lisp Drain State Into Generic Signals

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Create: `workflows/library/scripts/project_lisp_frontend_progress_signals.py`

- [ ] **Step 1: Write failing projection tests**

Test with a minimal Lisp drain run state:

```json
{
  "run_id": "run-1",
  "history": [
    {
      "event": "blocked",
      "item_id": "gap-a",
      "source": "DESIGN_GAP",
      "reason": "implementation_blocked",
      "recovery_reason": "target_design_contract_gap"
    },
    {
      "event": "blocked",
      "item_id": "gap-a",
      "source": "DESIGN_GAP",
      "reason": "implementation_blocked",
      "recovery_reason": "target_design_contract_gap"
    }
  ]
}
```

Expected generic signals:

- two events;
- same `work_item_id`;
- same deterministic `blocker_fingerprint`;
- no accepted change unless a completion event or commit hash is present.

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k progress_signals -q
```

Expected: FAIL because projector does not exist.

- [ ] **Step 3: Implement projection script**

CLI:

```bash
python workflows/library/scripts/project_lisp_frontend_progress_signals.py \
  --run-id "${run.id}" \
  --run-state-path state/.../run_state.json \
  --current-iteration 12 \
  --artifact-work-root artifacts/work/... \
  --output state/.../iterations/12/progress-signals.json
```

Projection rules:

- Only use the supplied run state and current run id.
- Do not glob shared artifact iteration directories as authority.
- Mark stale artifact provenance only when an event or consumed artifact explicitly declares a different run id or impossible iteration.
- Use stable fingerprints based on normalized item id, source, reason, recovery route, recovery reason, and blocker class.

- [ ] **Step 4: Run projection tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k progress_signals -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/project_lisp_frontend_progress_signals.py tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Project Lisp drain history into generic progress signals"
```

## Task 5: Add Generic Step-Back Diagnosis Prompt

**Files:**
- Create: `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add prompt contract test**

Add a lightweight test that verifies the prompt file exists and that the workflow output bundle is responsible for the structured action, not prompt prose parsing.

Do not assert exact wording.

- [ ] **Step 2: Write prompt**

Prompt responsibilities:

- Read `progress_signals` and `non_progress_decision`.
- Diagnose why recent work is not converging.
- Choose exactly one action from:
  - `REDRAFT_PLAN`
  - `REVISE_REQUIREMENTS`
  - `SPLIT_WORK_ITEM`
  - `DROP_OR_DEMOTE_WORK_ITEM`
  - `FIX_WORKFLOW_MECHANICS`
  - `CONTINUE_WITH_CURRENT_PLAN`
  - `NEEDS_HUMAN_DECISION`
- Write a JSON bundle to the output contract.

The prompt must not:

- count iterations itself;
- scan shared artifact roots;
- decide whether the step-back phase should run;
- mutate run state;
- instruct normal selector routing.

- [ ] **Step 3: Run prompt tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k step_back_prompt -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add workflows/library/prompts/workflow_step_back/diagnose_non_progress.md tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Add generic workflow step-back diagnosis prompt"
```

## Task 6: Integrate Step-Back Branch Into The Lisp Drain

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write failing workflow structure test**

Assert the drain loop contains, in this order:

1. `ProjectProgressSignals`
2. `EvaluateNonProgress`
3. `RouteNonProgress`
4. normal recovery/selector branch only when route is `NORMAL_CONTINUE`
5. `DiagnoseNonProgress` branch when route is `STEP_BACK_REQUIRED`
6. `RecordStepBackOutcome`
7. final status resolution understands step-back status.

- [ ] **Step 2: Run structure test and verify failure**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k step_back_branch -q
```

Expected: FAIL because branch is not present.

- [ ] **Step 3: Add projection and evaluator steps before blocked recovery detection**

In `DrainLispFrontendWork.repeat_until.steps`, add:

- `ProjectProgressSignals`
- `EvaluateNonProgress`
- `RouteNonProgress`

The non-progress evaluator output bundle fields:

- `route`: enum `NORMAL_CONTINUE | STEP_BACK_REQUIRED | TERMINAL_HUMAN_DECISION`
- `trigger_codes`: array
- `failure_fingerprint`: string
- `recommended_step_back_focus`: string

- [ ] **Step 4: Gate existing normal path**

Run existing `DetectBlockedDesignGapRecovery` and `SelectNextWork` only when `EvaluateNonProgress.route == NORMAL_CONTINUE`.

For `TERMINAL_HUMAN_DECISION`, write `BLOCKED`.

- [ ] **Step 5: Add step-back provider branch**

When route is `STEP_BACK_REQUIRED`, run `DiagnoseNonProgress` with:

- `progress_signals.json`
- `non-progress-decision.json`
- target design path, if the workflow already has one;
- no broad shared artifact directory injection.

Output bundle:

```yaml
fields:
  - name: step_back_action
    json_pointer: /action
    type: enum
    allowed:
      - REDRAFT_PLAN
      - REVISE_REQUIREMENTS
      - SPLIT_WORK_ITEM
      - DROP_OR_DEMOTE_WORK_ITEM
      - FIX_WORKFLOW_MECHANICS
      - CONTINUE_WITH_CURRENT_PLAN
      - NEEDS_HUMAN_DECISION
  - name: rationale
    json_pointer: /rationale
    type: string
```

- [ ] **Step 6: Record step-back outcome**

Call `record_workflow_step_back_outcome.py` and produce:

- `step-back-summary.json`
- `step-back-drain-status.txt`

- [ ] **Step 7: Update status resolver**

Add `--step-back-status-path` and route behavior:

- `STEP_BACK_REQUIRED` -> read step-back status
- `TERMINAL_HUMAN_DECISION` -> `BLOCKED`
- missing step-back status for step-back route -> fail closed

- [ ] **Step 8: Run structure tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k step_back_branch -q
```

Expected: PASS.

- [ ] **Step 9: Run workflow dry-run**

Run:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md
```

Expected: dry-run validates.

- [ ] **Step 10: Commit**

```bash
git add workflows/examples/lisp_frontend_design_delta_drain.yaml workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Add step-back non-progress route to Lisp drain"
```

## Task 7: Add End-To-End Mini Workflow Test

**Files:**
- Create: `workflows/examples/non_progress_step_back_demo.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py` or create `tests/test_workflow_non_progress_step_back_demo.py`

- [ ] **Step 1: Write failing smoke test**

Create a tiny demo workflow that:

- writes a synthetic signal file with two repeated blockers;
- evaluates non-progress;
- routes to a local command step that writes a deterministic diagnosis bundle;
- records step-back outcome;
- exits `CONTINUE`.

- [ ] **Step 2: Run dry-run and smoke test**

Run:

```bash
python -m orchestrator run workflows/examples/non_progress_step_back_demo.yaml --dry-run
pytest tests/test_workflow_non_progress_step_back_demo.py -q
```

Expected before implementation: FAIL because demo workflow is missing.

- [ ] **Step 3: Add demo workflow**

Use local command steps only. Do not use a provider in this smoke workflow.

- [ ] **Step 4: Run smoke**

Run:

```bash
python -m orchestrator run workflows/examples/non_progress_step_back_demo.yaml --dry-run
pytest tests/test_workflow_non_progress_step_back_demo.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workflows/examples/non_progress_step_back_demo.yaml tests/test_workflow_non_progress_step_back_demo.py
git commit -m "Add non-progress step-back demo workflow"
```

## Task 8: Document The General Workflow Authoring Pattern

**Files:**
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `workflows/README.md`

- [ ] **Step 1: Add drafting-guide section**

Add a section:

```text
Non-progress step-back loops

When a workflow can repeatedly select, plan, revise, or recover work, add a deterministic non-progress detector before normal selection. Triggers should be based on current-run evidence: repeated blocker fingerprints, repeated item blocks, no accepted change streaks, prerequisite chain growth, plan churn, non-converging findings, and stale artifact provenance. The workflow owns trigger counting and routing; a provider may only diagnose strategy after the trigger fires.
```

- [ ] **Step 2: Add workflow README entry**

Document `workflows/examples/non_progress_step_back_demo.yaml` as the copy-safe example for this pattern.

- [ ] **Step 3: Run doc checks**

Run:

```bash
rg -n "Non-progress step-back|non_progress_step_back_demo" docs/workflow_drafting_guide.md workflows/README.md
git diff --check -- docs/workflow_drafting_guide.md workflows/README.md
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/workflow_drafting_guide.md workflows/README.md
git commit -m "Document workflow non-progress step-back pattern"
```

## Task 9: Final Verification

**Files:**
- Verify all files changed above.

- [ ] **Step 1: Run focused unit tests**

```bash
pytest tests/test_workflow_non_progress_recovery.py -q
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "step_back or progress_signals" -q
pytest tests/test_workflow_non_progress_step_back_demo.py -q
```

- [ ] **Step 2: Run workflow validation**

```bash
python -m orchestrator run workflows/examples/non_progress_step_back_demo.yaml --dry-run
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md
```

- [ ] **Step 3: Run syntax checks**

```bash
python -m compileall \
  workflows/library/scripts/evaluate_workflow_non_progress.py \
  workflows/library/scripts/project_lisp_frontend_progress_signals.py \
  workflows/library/scripts/record_workflow_step_back_outcome.py
git diff --check
```

- [ ] **Step 4: Commit final integration fixes if needed**

Only commit fixes produced by verification.

## Non-Goals

- Do not encode project-specific concepts such as YAML, Workflow Lisp, old writers, or any target-design vocabulary into the generic evaluator.
- Do not let the provider decide whether step-back is required.
- Do not parse markdown as semantic evidence.
- Do not scan shared artifact roots as authority.
- Do not block every repeated failure terminally; the goal is to force strategy reassessment before continued work.

## Success Criteria

- Generic evaluator routes repeated non-progress to `STEP_BACK_REQUIRED`.
- Lisp drain uses current-run state to trigger step-back before normal selection.
- Step-back diagnosis emits a structured action and is recorded in run state.
- Normal selector cannot run again after a trigger until the step-back action is recorded.
- Stale/cross-run artifacts cannot drive step-back or recovery decisions.
- The implementation is covered by unit tests and at least one workflow dry-run.
