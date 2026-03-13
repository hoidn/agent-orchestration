# Item 0 Finish Implementation One-Off Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a one-off workflow that reuses the approved typed-pipeline design and plan for backlog item `typed-workflow-ast-ir-pipeline` and runs only the implementation review/fix phase until approval or the bounded iteration cap.

**Architecture:** Keep this small and explicit. Add a top-level example workflow that `call`s the existing reusable implementation-phase library with fixed item-0 paths and dedicated one-off state/report targets so it does not collide with the old backlog-stack run artifacts. Cover it with the existing example-workflow smoke harness and catalog it in the workflow index.

**Tech Stack:** Workflow DSL `2.7`, existing `design_plan_impl_implementation_phase.yaml` library, pytest example-workflow smoke tests, orchestrator dry-run validation.

---

### Task 1: Add failing example-workflow coverage

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add the new example filename to `EXAMPLE_FILES`**

Add `typed_workflow_ast_ir_pipeline_finish_item0.yaml` to the load-test catalog.

**Step 2: Add a runtime smoke test for the new one-off workflow**

Use the existing mocked-provider pattern:
- copy the new example workflow into the temp workspace
- copy `workflows/library/design_plan_impl_implementation_phase.yaml`
- copy the shared implementation prompt assets under `workflows/library/prompts/design_plan_impl_stack_v2_call/`
- mock `ExecuteImplementation` to write the execution report
- mock `ReviewImplementation` to write an `APPROVE` review decision and review report

Assert:
- run `status == "completed"`
- workflow outputs point at the dedicated one-off report/review paths
- `RunImplementationPhase` exports the expected three artifacts

**Step 3: Run the new targeted tests and confirm they fail**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k "typed_workflow_ast_ir_pipeline_finish_item0 or workflow_examples_v0_load" -v
```

Expected: failure because the new example workflow file does not exist yet.

### Task 2: Add the one-off workflow

**Files:**
- Create: `workflows/examples/typed_workflow_ast_ir_pipeline_finish_item0.yaml`

**Step 1: Add the top-level workflow**

Create a small `2.7` workflow that:
- imports `../library/design_plan_impl_implementation_phase.yaml`
- has no design/plan loop
- calls the implementation-phase library exactly once
- hard-codes item-0 paths:
  - design: `docs/plans/typed-workflow-ast-ir-pipeline-design.md`
  - plan: `docs/plans/typed-workflow-ast-ir-pipeline-execution-plan.md`
  - state root: a dedicated one-off root under `state/`
  - execution/review targets: dedicated one-off files under `artifacts/work` and `artifacts/review`
- exports final `execution_report_path`, `implementation_review_report_path`, and `implementation_review_decision` from the call step

**Step 2: Keep the workflow intentionally narrow**

Do not add:
- new prompts
- new library workflows
- new brief/design/plan generation stages
- dynamic inputs unless they materially simplify the one-off use case

### Task 3: Index and verify the new example

**Files:**
- Modify: `workflows/README.md`

**Step 1: Add the example to the workflow catalog**

Document it as a one-off workflow for finishing backlog item `typed-workflow-ast-ir-pipeline` by reusing the approved design and plan and running only the implementation phase.

**Step 2: Run the focused verification set**

Run:

```bash
pytest --collect-only tests/test_workflow_examples_v0.py -q
pytest tests/test_workflow_examples_v0.py -k "typed_workflow_ast_ir_pipeline_finish_item0 or workflow_examples_v0_load" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/typed_workflow_ast_ir_pipeline_finish_item0.yaml --dry-run --stream-output
```

Expected:
- test collection succeeds
- the focused example tests pass
- workflow dry-run validation succeeds

### Task 4: Summarize the result

**Files:**
- No file changes required

**Step 1: Record what changed**

Summarize:
- the new one-off workflow path
- whether it reuses the generic implementation-phase library
- what isolated state/report paths it writes to

**Step 2: Record verification evidence**

List the exact pytest selectors and dry-run command used, with their outcomes.
