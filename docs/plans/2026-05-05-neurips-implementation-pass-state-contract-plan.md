# NeurIPS Implementation Pass State Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a worktree; this repository's AGENTS.md forbids worktrees.

**Goal:** Make the NeurIPS backlog implementation phase route partial but reviewable implementation work into the review/fix loop instead of letting an implementation worker mark the selected item `BLOCKED`.

**Architecture:** Separate execution-pass evidence from item-terminal state. The implementation worker writes either a current-pass execution report or a validated external-blocker report; deterministic workflow steps infer the state from fresh artifacts, and implementation review decides `APPROVE` versus `REVISE`. The top-level drain should continue after a selected item is truly blocked without reading the selected-item call output through a brittle nested string substitution.

**Tech Stack:** Agent-orchestration DSL v2.7, reusable workflow YAML, Python command gates, pytest workflow-structure tests, PtychoPINN downstream workflow copy.

---

## File Structure

- Modify `workflows/library/neurips_backlog_implementation_phase.yaml`
  - Owns implementation execution, state materialization, review/fix loop, and final implementation phase outputs.
  - Add current-pass freshness tracking so stale `implementation_state.json` or stale progress reports cannot override a new execution report.
  - Keep the external workflow output enum as `COMPLETED | BLOCKED` for compatibility, but treat `COMPLETED` as "execution pass is reviewable and review loop reached approval."

- Modify `workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md`
  - Remove the instruction to "choose an implementation state."
  - Tell the worker to write `execution_report_target` for any reviewable in-scope progress, including partial work with remaining current-scope tasks.
  - Permit `progress_report_target` only for true external blockers, with `Blocker Class`.

- Modify `workflows/library/prompts/neurips_backlog_implementation_phase/review_implementation.md`
  - Clarify that unfinished current-scope work is a `REVISE` finding, not a selected-item block.
  - Keep `APPROVE` only for complete current scope and passing required checks.

- Modify `workflows/library/prompts/neurips_backlog_implementation_phase/fix_implementation.md`
  - Clarify that the fix pass continues remaining current-scope work from review findings and updates the same execution report.

- Modify `workflows/examples/neurips_steered_backlog_drain.yaml`
  - Replace `NormalizeSelectedItemDrainStatus` with a simple case-local `set_scalar` step that always emits `CONTINUE` after the selected-item call returns, so a true selected-item block is recorded in run state and the top-level drain proceeds.

- Modify `workflows/README.md`
  - Update the NeurIPS implementation-phase entry so `COMPLETED` is described as a review-approved terminal phase output, while partial execution passes go through review/fix.

- Modify `tests/test_major_project_workflows.py`
  - Add/adjust structure tests for the no-worker-state contract, fresh-state cleanup/freshness gate, review/fix ownership of partial work, and selected-item block continuation.

- Propagate the same workflow/prompt/docs/test changes to `/home/ollie/Documents/PtychoPINN` after the orchestration repo passes tests.

## Task 1: Lock The Desired Contract With Failing Tests

**Files:**
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Replace the stale implementation-state test expectations**

Update `test_neurips_implementation_phase_uses_terminal_implementation_states` so it no longer expects `ExecuteImplementation` to expose or consume an `implementation_state` bundle field. It should assert:

```python
workflow = _load_yaml("workflows/library/neurips_backlog_implementation_phase.yaml")
execute = _step_by_name(workflow, "ExecuteImplementation")
materialize = _step_by_name(workflow, "MaterializeImplementationState")

assert "output_bundle" not in execute
assert execute["prompt_consumes"] == [
    "design",
    "plan",
    "execution_report_target",
    "progress_report_target",
]
materialize_script = "\n".join(str(part) for part in materialize["command"])
assert "implementation_state.json" in materialize_script
assert "phase_started_at_ns" in materialize_script
assert "Blocker Class" in materialize_script
assert workflow["outputs"]["implementation_state"]["allowed"] == ["COMPLETED", "BLOCKED"]
```

- [ ] **Step 2: Add a test for prompt-level pass semantics**

Add:

```python
def test_neurips_execute_prompt_treats_partial_progress_as_reviewable_pass():
    prompt = (
        Path("workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md")
        .read_text(encoding="utf-8")
    )
    assert "Choose exactly one implementation state" not in prompt
    assert "write the execution report" in prompt
    assert "partial" in prompt.lower()
    assert "Remaining Required Plan Tasks" in prompt
    assert "Blocker Class" in prompt
```

Keep this as a broad contract test, not a literal phrasing test beyond stable section labels.

- [ ] **Step 3: Add a selected-item continuation structure test**

Replace the current nested-substitution assertion in `test_neurips_top_level_drain_continues_after_selected_item_blocks` with:

```python
route = _step_by_name(workflow, "RouteItemSelection")
selected_case = route["match"]["cases"]["SELECTED"]
output_ref = selected_case["outputs"]["drain_status"]["from"]["ref"]
assert output_ref == "self.steps.WriteSelectedItemContinue.artifacts.drain_status"
assert any(step["name"] == "RunSelectedItem" for step in selected_case["steps"])
write_continue = next(
    step for step in selected_case["steps"] if step["name"] == "WriteSelectedItemContinue"
)
assert write_continue["set_scalar"] == {"artifact": "drain_status", "value": "CONTINUE"}
```

- [ ] **Step 4: Run the narrow failing tests**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k "neurips_implementation_phase_uses_terminal_implementation_states or execute_prompt_treats_partial_progress or top_level_drain_continues_after_selected_item_blocks"
```

Expected before implementation: failures showing `ExecuteImplementation`/prompt/selected-case semantics still use the old worker-state or brittle normalization shape.

## Task 2: Make Implementation Execution Produce Evidence, Not Worker State

**Files:**
- Modify: `workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md`
- Modify: `workflows/library/prompts/neurips_backlog_implementation_phase/review_implementation.md`
- Modify: `workflows/library/prompts/neurips_backlog_implementation_phase/fix_implementation.md`

- [ ] **Step 1: Edit the execution prompt**

Change the opening state section from worker-selected state to evidence output:

```markdown
For any reviewable in-scope progress, write the execution report at the path recorded in `execution_report_target`.

This includes partial current-scope progress. If required plan tasks remain, record them under `Remaining Required Plan Tasks`; do not write a blocked/progress report merely because work remains.

Write the progress report at the path recorded in `progress_report_target` only for a real blocker outside implementation authority, or after a documented failed recovery attempt. A blocker report must include `Blocker Class` with one of:
...
```

Keep the existing dirty-worktree, queue movement, report sections, parity, and commit instructions.

- [ ] **Step 2: Edit the review prompt**

Add one short instruction near the existing "distinguish" list:

```markdown
Unfinished current-scope work is a `REVISE` finding for the fix loop, not an item-level block.
```

Do not add a `BLOCK` review decision; the current review contract remains `APPROVE | REVISE`.

- [ ] **Step 3: Edit the fix prompt**

Add one short instruction after the prioritization list:

```markdown
If review found unfinished current-scope work, continue that work and update the execution report; do not convert unfinished work into a blocked/progress report.
```

- [ ] **Step 4: Re-run the prompt contract test**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k "execute_prompt_treats_partial_progress"
```

Expected: pass.

## Task 3: Add Fresh Current-Pass State Materialization

**Files:**
- Modify: `workflows/library/neurips_backlog_implementation_phase.yaml`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Write the failing freshness test**

Add a structure test that asserts initialization writes a phase start marker and clears stale internal state:

```python
def test_neurips_implementation_phase_materializer_uses_current_pass_evidence():
    workflow = _load_yaml("workflows/library/neurips_backlog_implementation_phase.yaml")
    init = _step_by_name(workflow, "InitializeImplementationPhasePaths")
    init_script = "\n".join(init["command"])
    assert "phase_started_at_ns.txt" in init_script
    assert "implementation_state.json" in init_script
    assert "final_implementation_state.txt" in init_script

    materialize = _step_by_name(workflow, "MaterializeImplementationState")
    materialize_args = materialize["command"]
    assert "${inputs.state_root}/phase_started_at_ns.txt" in materialize_args
    materialize_script = "\n".join(str(part) for part in materialize_args)
    assert "is_fresh_report" in materialize_script
    assert "Existing implementation state bundle" not in materialize_script
```

- [ ] **Step 2: Update `InitializeImplementationPhasePaths`**

In the shell block:

```bash
python - <<'PY' "${inputs.state_root}/phase_started_at_ns.txt"
import pathlib
import sys
import time

path = pathlib.Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(str(time.time_ns()) + "\n", encoding="utf-8")
PY
rm -f \
  "${inputs.state_root}/implementation_state.json" \
  "${inputs.state_root}/implementation_state.txt" \
  "${inputs.state_root}/loop_review_decision.txt" \
  "${inputs.state_root}/implementation_review_decision.txt" \
  "${inputs.state_root}/final_implementation_state.txt" \
  "${inputs.state_root}/final_execution_report_path.txt" \
  "${inputs.state_root}/final_progress_report_path.txt" \
  "${inputs.state_root}/final_checks_report_path.txt" \
  "${inputs.state_root}/final_implementation_review_report_path.txt" \
  "${inputs.state_root}/final_implementation_review_decision.txt"
```

Do not delete durable report targets under `artifacts/work`; they may be useful historical evidence. Freshness is handled by the marker.

Add an expected output:

```yaml
- name: phase_started_at_ns
  path: ${inputs.state_root}/phase_started_at_ns.txt
  type: integer
```

- [ ] **Step 3: Rewrite `MaterializeImplementationState`**

Remove the branch that trusts an existing `implementation_state.json`.

Add a fourth command argument:

```yaml
- ${inputs.state_root}/phase_started_at_ns.txt
```

Use this Python logic:

```python
phase_started_at_ns = int(pathlib.Path(sys.argv[4]).read_text(encoding="utf-8").strip())

def is_fresh_report(path: pathlib.Path) -> bool:
    return path.is_file() and path.stat().st_mtime_ns >= phase_started_at_ns

has_execution_report = is_fresh_report(execution_report_target)
has_progress_report = is_fresh_report(progress_report_target)
```

State rules:

```python
if has_execution_report and has_progress_report:
    raise SystemExit("Current pass produced both execution and blocker reports")
if has_execution_report:
    payload = {
        "implementation_state": "COMPLETED",
        "execution_report_path": execution_report_target.as_posix(),
    }
elif has_progress_report:
    blocker_class = parse_blocker_class(progress_report_target)
    payload = {
        "implementation_state": "BLOCKED",
        "progress_report_path": progress_report_target.as_posix(),
        "blocker_class": blocker_class,
    }
else:
    raise SystemExit("Current implementation pass produced neither execution report nor blocker report")
```

Implement `parse_blocker_class()` to scan markdown lines for either:

```text
Blocker Class: missing_resource
Blocker Class
missing_resource
```

Reject missing or invalid blocker classes using the existing allowed class set.

- [ ] **Step 4: Update assertions that mention output bundles**

If any tests still call `_bundle_field(execute, "implementation_state")`, update them to inspect `MaterializeImplementationState.output_bundle` instead.

- [ ] **Step 5: Run the implementation-phase structure tests**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k "neurips_implementation_phase"
```

Expected: pass.

## Task 4: Fix Top-Level Selected-Item Block Continuation Without Nested Artifact Substitution

**Files:**
- Modify: `workflows/examples/neurips_steered_backlog_drain.yaml`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Replace `NormalizeSelectedItemDrainStatus`**

In the `RouteItemSelection.SELECTED` case:

Change selected-case output:

```yaml
from:
  ref: self.steps.WriteSelectedItemContinue.artifacts.drain_status
```

Remove the Python `NormalizeSelectedItemDrainStatus` command.

Add after `RunSelectedItem`:

```yaml
- name: WriteSelectedItemContinue
  id: write_selected_item_continue
  set_scalar:
    artifact: drain_status
    value: CONTINUE
```

This step runs only after `RunSelectedItem` returns successfully. If selected-item recorded a true block, the next selector pass skips it via `run_state.blocked_items`; if it completed, the next pass sees it in completed state.

- [ ] **Step 2: Run the selected-item continuation test**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k "top_level_drain_continues_after_selected_item_blocks"
```

Expected: pass.

## Task 5: Remove Selected-Item Blocking For Review `REVISE`

**Files:**
- Modify: `workflows/library/neurips_selected_backlog_item.yaml`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add a structure test**

Add:

```python
def test_neurips_selected_item_does_not_block_on_implementation_review_revise():
    workflow = _load_yaml("workflows/library/neurips_selected_backlog_item.yaml")
    assert "RecordImplementationIncomplete" not in _step_names(workflow)
    assert "Implementation review did not approve" not in yaml.safe_dump(workflow)
```

- [ ] **Step 2: Remove `RecordImplementationIncomplete`**

Delete the `RecordImplementationIncomplete` step. Under the corrected implementation-phase contract, review `REVISE` is handled inside `ImplementationReviewLoop`; it should not cross the phase boundary as a selected-item terminal outcome.

Keep `RecordImplementationBlocked` for true implementation blockers.

- [ ] **Step 3: Run selected-item structure tests**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k "neurips_selected_item"
```

Expected: pass.

## Task 6: Update Workflow README

**Files:**
- Modify: `workflows/README.md`

- [ ] **Step 1: Update the implementation-phase description**

Change the `neurips_backlog_implementation_phase.yaml` row to say:

```text
Executes one reviewable implementation pass, materializes fresh execution or blocker evidence, runs review/fix until approval, and exports `COMPLETED` only after review approval or `BLOCKED` only for a validated external blocker.
```

- [ ] **Step 2: Update the drain wrapper description if needed**

For `neurips_steered_backlog_drain.yaml`, mention that a selected item's validated block is recorded and skipped on the next selector pass rather than stopping the whole drain.

## Task 7: Verify In Agent-Orchestration

**Files:**
- No edits unless failures reveal a missed contract.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k "neurips_implementation_phase or neurips_selected_item or top_level_drain_continues_after_selected_item_blocks"
```

Expected: pass.

- [ ] **Step 2: Run collect-only for the edited test module**

Run:

```bash
pytest --collect-only -q tests/test_major_project_workflows.py
```

Expected: collection succeeds.

- [ ] **Step 3: Run a workflow dry-run**

Run from `/home/ollie/Documents/agent-orchestration`:

```bash
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run \
  --input steering_path=docs/steering.md \
  --input design_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-design.md \
  --input roadmap_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-roadmap.md \
  --input roadmap_gate_path=docs/backlog/roadmap_gate.json \
  --input progress_ledger_path=state/NEURIPS-HYBRID-RESNET-2026/progress_ledger.json
```

If those downstream input files are absent in agent-orchestration, run the same dry-run in PtychoPINN after propagation instead and record why the source-repo dry-run was not applicable.

## Task 8: Propagate To PtychoPINN

**Files:**
- Modify matching files under `/home/ollie/Documents/PtychoPINN`:
  - `workflows/library/neurips_backlog_implementation_phase.yaml`
  - `workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md`
  - `workflows/library/prompts/neurips_backlog_implementation_phase/review_implementation.md`
  - `workflows/library/prompts/neurips_backlog_implementation_phase/fix_implementation.md`
  - `workflows/library/neurips_selected_backlog_item.yaml`
  - `workflows/examples/neurips_steered_backlog_drain.yaml`
  - `workflows/README.md` if present
  - `tests/studies/test_neurips_steered_backlog_workflow.py`

- [ ] **Step 1: Apply the same edits**

Use `apply_patch` or direct copied hunks. Do not stage unrelated PtychoPINN dirty work.

- [ ] **Step 2: Run PtychoPINN targeted tests**

Run from `/home/ollie/Documents/PtychoPINN`:

```bash
pytest -q tests/studies/test_neurips_steered_backlog_workflow.py -k "neurips_implementation_phase or neurips_selected_item or top_level_drain_continues_after_selected_item_blocks"
```

Expected: pass.

- [ ] **Step 3: Run PtychoPINN collect-only**

Run:

```bash
pytest --collect-only -q tests/studies/test_neurips_steered_backlog_workflow.py
```

Expected: collection succeeds.

- [ ] **Step 4: Run PtychoPINN dry-run in `ptycho311`**

Run:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run \
  --input steering_path=docs/steering.md \
  --input design_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-design.md \
  --input roadmap_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-roadmap.md \
  --input roadmap_gate_path=docs/backlog/roadmap_gate.json \
  --input progress_ledger_path=state/NEURIPS-HYBRID-RESNET-2026/progress_ledger.json
```

Expected: workflow validation successful.

## Task 9: Recover The Current Natural-Patch Queue State

**Files:**
- Runtime state only; do not commit `.orchestrate/` or state files unless explicitly requested.

- [ ] **Step 1: Inspect current queue location**

Run:

```bash
ls docs/backlog/active/2026-05-04-cdi-natural-patch-expanded-benchmark.md \
   docs/backlog/in_progress/2026-05-04-cdi-natural-patch-expanded-benchmark.md
```

- [ ] **Step 2: If the item is blocked only by the incorrect partial-pass block, requeue it**

If `run_state.blocked_items` contains `2026-05-04-cdi-natural-patch-expanded-benchmark` and its last execution report shows reviewable progress, remove only that blocked entry and move the item back to `docs/backlog/active/`.

Use a short Python state-edit script that appends a `requeue` event with reason:

```text
Cleared incorrect partial-implementation block after implementation pass state contract fix; remaining current-scope work belongs in review/fix.
```

- [ ] **Step 3: Relaunch or resume appropriately**

If the previous orchestrator run is failed at the normalization step, prefer a fresh run after requeue because the selected-item subworkflow already recorded a stale block. Use the standard tmux launch in `ptycho311`.

## Task 10: Commit

**Files:**
- Commit only scoped workflow/prompt/test/docs changes.
- Do not commit `.orchestrate/`, runtime state, generated benchmark outputs, or unrelated PtychoPINN dirty work.

- [ ] **Step 1: Review staged source-repo diff**

Run:

```bash
git diff --cached --stat
git diff --cached -- workflows/library/neurips_backlog_implementation_phase.yaml workflows/library/neurips_selected_backlog_item.yaml workflows/examples/neurips_steered_backlog_drain.yaml
```

- [ ] **Step 2: Commit agent-orchestration changes**

Run:

```bash
git add \
  workflows/library/neurips_backlog_implementation_phase.yaml \
  workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md \
  workflows/library/prompts/neurips_backlog_implementation_phase/review_implementation.md \
  workflows/library/prompts/neurips_backlog_implementation_phase/fix_implementation.md \
  workflows/library/neurips_selected_backlog_item.yaml \
  workflows/examples/neurips_steered_backlog_drain.yaml \
  workflows/README.md \
  tests/test_major_project_workflows.py \
  docs/plans/2026-05-05-neurips-implementation-pass-state-contract-plan.md
git commit -m "fix: route partial neurips implementation through review"
```

- [ ] **Step 3: Commit PtychoPINN propagated changes if requested**

Stage only matching propagated files and commit:

```bash
git add \
  workflows/library/neurips_backlog_implementation_phase.yaml \
  workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md \
  workflows/library/prompts/neurips_backlog_implementation_phase/review_implementation.md \
  workflows/library/prompts/neurips_backlog_implementation_phase/fix_implementation.md \
  workflows/library/neurips_selected_backlog_item.yaml \
  workflows/examples/neurips_steered_backlog_drain.yaml \
  workflows/README.md \
  tests/studies/test_neurips_steered_backlog_workflow.py
git commit -m "fix: route partial neurips implementation through review"
```

## Acceptance Criteria

- `ExecuteImplementation` no longer asks the worker to choose `COMPLETED` versus `BLOCKED`.
- Any current-pass execution report routes to implementation review.
- Remaining required plan tasks become review `REVISE` findings and enter `FixImplementation`.
- A current-pass blocker report routes to `BLOCKED` only when it includes a valid external `Blocker Class`.
- Stale `implementation_state.json` or stale progress reports from an older run cannot override a fresh execution report.
- The top-level drain does not crash on selected-item `BLOCKED` and does not stop the whole drain because one selected item was blocked.
- Tests and dry-runs pass in agent-orchestration and PtychoPINN.
