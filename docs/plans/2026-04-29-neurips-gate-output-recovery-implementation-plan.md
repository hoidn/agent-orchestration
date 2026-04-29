# NeurIPS Gate Output Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make NeurIPS selected-item recovery skip the plan phase when a recovered in-progress backlog item already has a valid durable plan authority.

**Architecture:** Add deterministic plan-gate recovery before the plan phase. The selected-item workflow branches between recovered plan outputs and fresh plan outputs, then normalizes both branches to one plan output contract consumed by implementation.

**Tech Stack:** Agent-orchestration DSL v2.7 structured control, YAML workflow calls, Python helper scripts, pytest workflow-contract tests, orchestrator dry-run validation.

---

## File Structure

- Modify: `workflows/library/scripts/materialize_neurips_selected_item_inputs.py`
  - Preserve the selected item's existing frontmatter `plan_path` in the materialized bundle as candidate recovery evidence.
  - Do not emit lifecycle states such as `IMPLEMENTATION_READY`.

- Create: `workflows/library/scripts/recover_neurips_plan_gate_outputs.py`
  - Validate whether the current selected item has recoverable plan-gate evidence.
  - Emit a JSON bundle with `plan_gate_status`, `plan_path`, and `plan_review_report_path`.
  - Write a recovery report when recovering without an original plan review report.

- Modify: `workflows/library/neurips_selected_backlog_item.yaml`
  - Add `RecoverPlanGateOutputs` after roadmap sync and current-selection recording.
  - Replace the unconditional `RunFreshPlanPhase` path with a branch that either uses recovered plan outputs or runs fresh planning.
  - Route implementation through the branch output `plan_path`.
  - Keep active newly selected items on the fresh planning path.

- Modify: `tests/test_major_project_workflows.py` or add a focused NeurIPS workflow test module.
  - Add static contract tests for the selected-item branch and normalized plan output.
  - Add unit tests for the plan-gate recovery script.

- No prompt edits are expected.

## Task 1: Lock The Workflow Contract With Static Tests

**Files:**
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add a test that implementation consumes normalized plan output**

Add a test for `workflows/library/neurips_selected_backlog_item.yaml`:

```python
def test_neurips_selected_item_implementation_uses_normalized_plan_gate_output():
    workflow = _load_yaml("workflows/library/neurips_selected_backlog_item.yaml")

    implementation = _step_by_name(workflow, "RunImplementationPhase")
    assert implementation["with"]["plan_path"] == {
        "ref": "root.steps.ResolvePlanGateOutputs.artifacts.plan_path"
    }
```

- [ ] **Step 2: Add a test that fresh planning is conditional**

Assert the selected-item workflow has a deterministic recovery step and that fresh planning is no longer unconditional:

```python
def test_neurips_selected_item_has_plan_gate_recovery_branch():
    workflow = _load_yaml("workflows/library/neurips_selected_backlog_item.yaml")

    recover = _step_by_name(workflow, "RecoverPlanGateOutputs")
    assert recover["output_bundle"]["fields"][0]["name"] == "plan_gate_status"

    fresh = _step_by_name(workflow, "RunFreshPlanPhase")
    assert fresh.get("when") or _step_by_name(workflow, "ResolvePlanGateOutputs").get("if")
```

If the implementation uses a structured `if` wrapper instead of a direct `when` on `RunFreshPlanPhase`, adjust the assertion to check the wrapper outputs:

```python
resolve = _step_by_name(workflow, "ResolvePlanGateOutputs")
assert "outputs" in resolve["then"] or "outputs" in resolve["else"]
assert resolve["then"]["outputs"]["plan_path"] == resolve["else"]["outputs"]["plan_path"]
```

- [ ] **Step 3: Run the focused static tests and verify failure**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k 'neurips and plan'
```

Expected before implementation: fails because implementation still references `RunFreshPlanPhase.artifacts.plan_path` and no recovery branch exists.

## Task 2: Add Script Tests For Plan-Gate Recovery

**Files:**
- Modify or create: focused test module for NeurIPS helper scripts.
- Create later: `workflows/library/scripts/recover_neurips_plan_gate_outputs.py`

- [ ] **Step 1: Add a recovered-plan success test**

Create a temporary workspace with:

- `docs/backlog/in_progress/item.md` containing frontmatter `plan_path: docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/item/execution_plan.md`
- the referenced plan file
- an output path under `state/.../plan-gate-recovery.json`

Run:

```bash
python workflows/library/scripts/recover_neurips_plan_gate_outputs.py \
  --selection-mode RECOVERED_IN_PROGRESS \
  --selected-item-path docs/backlog/in_progress/item.md \
  --recovery-report-target-path artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/item-plan-recovery.md \
  --output state/item/plan-gate-recovery.json
```

Assert the JSON contains:

```json
{
  "plan_gate_status": "RECOVERED",
  "plan_path": "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/item/execution_plan.md",
  "plan_review_decision": "APPROVE"
}
```

- [ ] **Step 2: Add missing-plan fallback tests**

Cover at least:

- selection mode is `ACTIVE_SELECTION`
- recovered item has empty `plan_path`
- recovered item points outside `docs/plans/`
- recovered item points to a missing file

Each case should produce `plan_gate_status: MISSING` and no valid `plan_path`.

- [ ] **Step 3: Run script tests and verify failure**

Run the narrow test selector for the new tests.

Expected before implementation: fails because the script does not exist.

## Task 3: Implement Plan-Gate Recovery Script

**Files:**
- Create: `workflows/library/scripts/recover_neurips_plan_gate_outputs.py`

- [ ] **Step 1: Parse frontmatter safely**

Reuse the small frontmatter parser shape from `materialize_neurips_selected_item_inputs.py`. Validate:

- `--selection-mode` is `ACTIVE_SELECTION` or `RECOVERED_IN_PROGRESS`
- `--selected-item-path` is repo-relative and under `docs/backlog/in_progress/` for recovered items
- `plan_path` is repo-relative, does not contain `..`, is under `docs/plans/`, and exists

- [ ] **Step 2: Emit `MISSING` for non-recoverable cases**

Write JSON like:

```json
{
  "plan_gate_status": "MISSING",
  "plan_path": "",
  "plan_review_decision": "REVISE",
  "plan_review_report_path": ""
}
```

Use an enum value such as `REVISE` only if the YAML contract requires a non-empty decision. Otherwise make `plan_review_decision` optional or omit it from the `MISSING` branch output bundle.

- [ ] **Step 3: Emit `RECOVERED` for valid durable evidence**

Write JSON like:

```json
{
  "plan_gate_status": "RECOVERED",
  "plan_path": "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/item/execution_plan.md",
  "plan_review_decision": "APPROVE",
  "plan_review_report_path": "artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/item-plan-recovery.md"
}
```

Create the recovery report target if no original review report is provided. The report should briefly state:

- item path
- recovered plan path
- validation checks performed
- that this is recovery evidence, not a fresh plan review

- [ ] **Step 4: Run script tests**

Run the narrow test selector.

Expected: new script tests pass.

## Task 4: Preserve Candidate Plan Evidence In Materialization

**Files:**
- Modify: `workflows/library/scripts/materialize_neurips_selected_item_inputs.py`

- [ ] **Step 1: Add bundle fields**

Add:

```json
{
  "candidate_plan_path": "<frontmatter plan_path or manifest plan_path>",
  "plan_gate_recovery_bundle_path": "<state-root>/items/<item>/plan-gate-recovery.json",
  "plan_gate_recovery_report_target_path": "artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/<item>-plan-recovery.md"
}
```

- [ ] **Step 2: Update selected-item YAML output bundle declaration**

Add matching fields to `MaterializeSelectedItemInputs.output_bundle`.

- [ ] **Step 3: Run materialization-related tests**

Run:

```bash
pytest -q tests/test_neurips_backlog_roadmap_gate.py
```

Expected: existing tests still pass or are updated for the new fields.

## Task 5: Route Selected-Item YAML Through Recovered Or Fresh Plan Outputs

**Files:**
- Modify: `workflows/library/neurips_selected_backlog_item.yaml`

- [ ] **Step 1: Add `RecoverPlanGateOutputs`**

Add a command step after `RecordCurrentSelection`:

```yaml
- name: RecoverPlanGateOutputs
  id: recover_plan_gate_outputs
  command:
    - python
    - workflows/library/scripts/recover_neurips_plan_gate_outputs.py
    - --selection-mode
    - ${steps.MaterializeSelectedItemInputs.artifacts.selection_mode}
    - --selected-item-path
    - ${steps.MaterializeSelectedItemInputs.artifacts.selected_item_in_progress_path}
    - --recovery-report-target-path
    - ${steps.MaterializeSelectedItemInputs.artifacts.plan_gate_recovery_report_target_path}
    - --output
    - ${steps.MaterializeSelectedItemInputs.artifacts.plan_gate_recovery_bundle_path}
  output_bundle:
    path: ${steps.MaterializeSelectedItemInputs.artifacts.plan_gate_recovery_bundle_path}
    fields:
      - name: plan_gate_status
        json_pointer: /plan_gate_status
        type: enum
        allowed: ["RECOVERED", "MISSING"]
      - name: recovered_plan_path
        json_pointer: /plan_path
        type: relpath
        under: docs/plans
        must_exist_target: true
        required: false
      - name: recovered_plan_review_report_path
        json_pointer: /plan_review_report_path
        type: relpath
        under: artifacts/review
        must_exist_target: true
        required: false
```

- [ ] **Step 2: Add a normalized plan-output branch**

Use the simplest DSL shape that validates cleanly in this repo. Preferred shape is a structured branch named `ResolvePlanGateOutputs` with outputs:

- `plan_path`
- `plan_review_report_path`
- `plan_review_decision`

The recovered branch should expose recovered artifacts. The fresh branch should run:

- `RunFreshPlanPhase`
- `AssertPlanApproved`
- `RewriteSelectedItemPlanPath`

and expose the fresh artifacts.

- [ ] **Step 3: Update implementation and reconciliation references**

Change all downstream references from:

```yaml
root.steps.RunFreshPlanPhase.artifacts.plan_path
```

to:

```yaml
root.steps.ResolvePlanGateOutputs.artifacts.plan_path
```

Also update any queue reconciliation step that previously depended on `RewriteSelectedItemPlanPath` directly. Recovered-plan runs should still reconcile the in-progress item path safely, but should not require the fresh rewrite step to have executed.

- [ ] **Step 4: Run static workflow tests**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k 'neurips and plan'
```

Expected: selected-item plan recovery contract tests pass.

## Task 6: Validation And Smoke Checks

**Files:**
- No new files unless tests reveal missing docs.

- [ ] **Step 1: Run focused NeurIPS tests**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k 'neurips or terminal or waiting'
pytest -q tests/test_neurips_backlog_roadmap_gate.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run orchestrator dry-run**

Run from the repo root:

```bash
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run
```

Expected: dry-run validates the workflow graph and exits successfully.

- [ ] **Step 3: If propagating to PtychoPINN, run downstream dry-run in `ptycho311`**

From `/home/ollie/Documents/PtychoPINN`:

```bash
source /home/ollie/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
TMPDIR=/home/ollie/Documents/agent-orchestration/tmp \
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run
```

Expected: dry-run succeeds using the downstream copied workflow files.

## Task 7: Commit

**Files:**
- Stage only the files changed for this plan.

- [ ] **Step 1: Review diff**

Run:

```bash
git diff -- workflows/library/neurips_selected_backlog_item.yaml \
  workflows/library/scripts/materialize_neurips_selected_item_inputs.py \
  workflows/library/scripts/recover_neurips_plan_gate_outputs.py \
  tests/test_major_project_workflows.py
```

- [ ] **Step 2: Commit**

Run:

```bash
git add workflows/library/neurips_selected_backlog_item.yaml \
  workflows/library/scripts/materialize_neurips_selected_item_inputs.py \
  workflows/library/scripts/recover_neurips_plan_gate_outputs.py \
  tests/test_major_project_workflows.py
git commit -m "Recover NeurIPS plan gate outputs"
```
