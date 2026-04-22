# Approved-Design Plan/Implementation Entry Path Plan

## Goal

Add a narrow workflow path for major-project tranche work that starts from an already-approved design and continues with plan plus implementation, without rerunning the big-design phase.

## Why

The current `major_project_tranche_design_plan_impl_stack.yaml` always redrafts and rereviews big design. That is correct for fresh tranche work, but it prevents clean recovery when:

- big design has already been approved or manually recovered
- the next required work is plan plus implementation only
- the manifest should still be updated through the normal tranche outcome path

## Architecture

Keep the fix small and explicit:

1. Add a reusable library workflow that:
   - accepts tranche metadata plus an existing approved `design_path`
   - reuses `tracked_plan_phase.yaml`
   - reuses `design_plan_impl_implementation_phase.yaml`
   - preserves the existing item-summary and item-outcome finalization shape

2. Add a one-tranche continuation example that:
   - selects the next ready tranche from an existing manifest
   - calls the new approved-design stack
   - updates the manifest with the standard `update_major_project_tranche_manifest.py` script

3. Do not modify the main drain workflow to infer approval state from ambient files.
   - That would blur phase boundaries and create hidden behavior.
   - Recovery should be explicit at the workflow boundary.

## Files

- Create: `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
- Create: `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml`
- Modify: `tests/test_major_project_workflows.py`
- Modify: `workflows/README.md`

## Implementation Tasks

### Task 1: Add the reusable approved-design tranche stack

Create a new library workflow that:

- initializes the item, plan-phase, and implementation-phase state roots
- calls `tracked_plan_phase.yaml` with the supplied `design_path`
- calls `design_plan_impl_implementation_phase.yaml` with the same `design_path` plus the approved plan
- finalizes `APPROVED`, `SKIPPED_AFTER_PLAN`, or `SKIPPED_AFTER_IMPLEMENTATION`
- exports:
  - `item_outcome`
  - `execution_report_path`
  - `item_summary_path`

Keep the finalization payload aligned with the existing major-project tranche stack so manifest updates and downstream readers do not need a second summary format.

### Task 2: Add the continuation example

Create a top-level example workflow that:

- consumes an existing project brief, project roadmap, tranche manifest, and approved design path
- selects the next ready tranche using `select_major_project_tranche.py`
- calls the new approved-design tranche stack
- updates the manifest using `update_major_project_tranche_manifest.py`
- exports:
  - `drain_status`
  - `tranche_manifest_path`
  - `execution_report_path`
  - `item_summary_path`

The workflow should be intentionally one-tranche. Continuing with the normal drain workflow after this recovery step is fine.

### Task 3: Add tests

Add focused coverage that checks:

- the new library stack reuses the existing plan and implementation phases
- the continuation example starts at manifest selection and never imports/calls big design
- a mocked runtime smoke can:
  - select a tranche from manifest
  - consume a preexisting approved design
  - draft/review plan
  - implement/review implementation
  - update the manifest to `completed`

### Task 4: Index and verify

Update `workflows/README.md` to document both new workflows.

Run:

```bash
pytest --collect-only tests/test_major_project_workflows.py -q
pytest tests/test_major_project_workflows.py -q
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml --dry-run --stream-output
```

Then propagate the new workflows to the EasySpin copy and run a dry-run there in `ptycho311`.
