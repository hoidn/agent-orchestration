# Priority Backlog Phase Stack Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a new workflow that processes included backlog items in explicit priority order and, for each item, runs design -> plan -> implementation phases while treating any phase failure as a per-item skip rather than a whole-workflow failure.

**Architecture:** Reuse the existing tracked design, tracked plan, and implementation-phase library workflows. Add a new per-item stack subworkflow that sequences those three phase calls and converts any `call` failure into a successful terminal item outcome like `SKIPPED_AFTER_DESIGN`, `SKIPPED_AFTER_PLAN`, or `SKIPPED_AFTER_IMPLEMENTATION`. Add a new top-level manifest-driver workflow that iterates an ordered backlog manifest with `for_each`, derives per-item write roots and target paths, and calls the per-item stack once per backlog entry.

**Tech Stack:** Workflow DSL `2.7`, reusable `call`, `for_each`, `output_bundle`, scalar artifacts, existing Codex provider prompt trees, pytest runtime example coverage, orchestrator dry-run validation.

---

## Design Summary

The key design choice is to avoid making the outer workflow understand inner loop failure subtypes like `repeat_until_iterations_exhausted`. Instead:

1. The existing phase workflows stay unchanged.
2. A new per-item subworkflow owns phase sequencing.
3. Each phase `call` step uses `on.failure.goto` to jump to a per-item finalization step.
4. That finalization step writes an item summary and an item outcome scalar, then the subworkflow completes successfully.
5. The outer backlog workflow simply iterates the ordered manifest and calls the per-item subworkflow once per item.

This keeps the outer loop simple and satisfies the requirement exactly as stated: any phase failure causes the workflow to move to the next backlog item, not fail the whole run.

## Manifest Contract

Use an explicit ordered JSON array as the source of truth for priority. Each item should minimally contain:

```json
[
  {
    "item_id": "provider-session-resume",
    "brief_path": "docs/backlog/active/2026-03-09-provider-prompt-source-surface-clarity.md"
  }
]
```

The driver workflow should preserve manifest order exactly. Do not infer priority from glob order or directory listing order.

The driver should derive per-item paths instead of requiring them all in the manifest. For each item, derive:

- `state_root`: `state/backlog-priority-stack/<item_id>`
- `design_target_path`: `docs/plans/<item_id>-design.md`
- `design_review_report_target_path`: `artifacts/review/<item_id>-design-review.json`
- `plan_target_path`: `docs/plans/<item_id>-execution-plan.md`
- `plan_review_report_target_path`: `artifacts/review/<item_id>-plan-review.json`
- `execution_report_target_path`: `artifacts/work/<item_id>-execution-report.md`
- `implementation_review_report_target_path`: `artifacts/review/<item_id>-implementation-review.md`
- `item_summary_path`: `artifacts/work/<item_id>-summary.json`

## Workflow Shape

Create two new workflows:

- `workflows/library/backlog_item_design_plan_impl_stack.yaml`
- `workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml`

The library workflow should:

- accept typed inputs for `item_id`, `brief_path`, `state_root`, and all derived target paths
- call `tracked_design_phase.yaml`
- on design failure, jump to `FinalizeSkippedAfterDesign`
- on design success, call `tracked_plan_phase.yaml`
- on plan failure, jump to `FinalizeSkippedAfterPlan`
- on plan success, call `design_plan_impl_implementation_phase.yaml`
- on implementation failure, jump to `FinalizeSkippedAfterImplementation`
- on full success, jump to `FinalizeApprovedItem`
- always complete successfully with an exported scalar `item_outcome`

Recommended `item_outcome` enum:

- `APPROVED`
- `SKIPPED_AFTER_DESIGN`
- `SKIPPED_AFTER_PLAN`
- `SKIPPED_AFTER_IMPLEMENTATION`

The top-level workflow should:

- bind one input `backlog_manifest_path`
- read the manifest
- iterate ordered items with `for_each`
- prepare one per-item JSON input bundle inside each iteration
- call the per-item stack once
- optionally write one final manifest-level summary after the loop

No prompt changes should be required. Reuse the existing prompt tree:

- `prompts/workflows/design_plan_impl_stack_v2_call/`

### Task 1: Add characterization coverage for the skip-on-phase-failure behavior

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`
- Reference: `tests/test_workflow_examples_v0.py:1152` (current stack call example runtime test)

**Step 1: Add a failing runtime test scaffold for the new example**

Add a new test shaped like the existing call-stack runtime examples, but drive two backlog items through the new manifest-driver workflow:

- item 1: design phase review/fix loop never reaches approval and the design phase call fails
- item 2: design, plan, and implementation all reach approval

The assertions should verify:

- the overall workflow run completes successfully
- item 1 records `SKIPPED_AFTER_DESIGN`
- item 2 records `APPROVED`
- item 2 still reaches the implementation phase even though item 1 failed earlier

**Step 2: Run the narrow selector and verify the new test fails**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k backlog_priority_design_plan_impl_stack_v2_call -v
```

Expected: FAIL because the workflow/example files do not exist yet.

**Step 3: Commit the failing test scaffold**

```bash
git add tests/test_workflow_examples_v0.py
git commit -m "test: add backlog priority stack workflow coverage"
```

### Task 2: Create the per-item stack subworkflow

**Files:**
- Create: `workflows/library/backlog_item_design_plan_impl_stack.yaml`
- Reference: `workflows/library/tracked_design_phase.yaml`
- Reference: `workflows/library/tracked_plan_phase.yaml`
- Reference: `workflows/library/design_plan_impl_implementation_phase.yaml`

**Step 1: Declare typed inputs and outputs**

Inputs should include:

- `item_id`
- `brief_path`
- `state_root`
- `design_target_path`
- `design_review_report_target_path`
- `plan_target_path`
- `plan_review_report_target_path`
- `execution_report_target_path`
- `implementation_review_report_target_path`
- `item_summary_target_path`

Outputs should include at least:

- `item_outcome` (enum)
- `item_summary_path` (relpath)

Optionally also export successful `design_path`, `plan_path`, and `execution_report_path` through final adapter files, but only if they can be made total for every terminal path.

**Step 2: Implement phase sequencing with failure routing**

Use three top-level `call` steps:

- `RunDesignPhase`
- `RunPlanPhase`
- `RunImplementationPhase`

For each phase step, use `on.failure.goto` to route to a terminal item-finalization step instead of failing the whole subworkflow.

**Step 3: Implement terminal finalization steps**

Add four terminal paths:

- `FinalizeApprovedItem`
- `FinalizeSkippedAfterDesign`
- `FinalizeSkippedAfterPlan`
- `FinalizeSkippedAfterImplementation`

Each path should write:

- a scalar `item_outcome`
- a summary JSON file at the exact path named by `item_summary_target_path`

The summary JSON should contain:

- `item_id`
- `item_outcome`
- `failed_phase` or `null`
- any successful phase outputs known so far

Use one stable final exporter step if needed so workflow `outputs` always point to one concrete producer.

**Step 4: Validate the library workflow**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/library/backlog_item_design_plan_impl_stack.yaml --dry-run
```

Expected: validation succeeds once the workflow is complete.

**Step 5: Commit**

```bash
git add workflows/library/backlog_item_design_plan_impl_stack.yaml
git commit -m "feat: add per-item backlog phase stack workflow"
```

### Task 3: Create the top-level backlog manifest driver workflow

**Files:**
- Create: `workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml`
- Create: `workflows/examples/inputs/backlog_priority_items.json`
- Reference: `workflows/examples/design_plan_impl_review_stack_v2_call.yaml`
- Reference: `workflows/examples/for_each_demo.yaml`

**Step 1: Add the manifest input and manifest-read step**

The top-level workflow should declare:

- `backlog_manifest_path` as a typed `relpath` input under `workflows/examples/inputs`

Add a step that reads the manifest JSON array so `for_each.items_from` can iterate it.

**Step 2: Add ordered `for_each` over the manifest items**

Inside the loop:

- derive per-item target paths from `item.item_id`
- write them into one per-item JSON file
- parse that file with `output_bundle`
- call `backlog_item_design_plan_impl_stack.yaml` with those derived values

Prefer a per-item input-preparation step similar to `workflows/examples/repeat_until_demo.yaml` so the `call` step bindings stay typed and readable.

**Step 3: Make the outer loop insensitive to inner item failure**

The outer loop should not need its own failure-routing logic if the item subworkflow always completes successfully with an `item_outcome`.

The `for_each` should therefore be a simple ordered item driver, not a second error-handling layer.

**Step 4: Add optional final aggregate summary**

If useful, add one post-loop step that aggregates all item summaries under `artifacts/work/backlog-priority-stack/summary.json`.

Keep this additive; do not block the basic workflow on aggregation complexity.

**Step 5: Validate the top-level workflow**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml \
  --dry-run \
  --input backlog_manifest_path=workflows/examples/inputs/backlog_priority_items.json \
  --stream-output
```

Expected: validation succeeds.

**Step 6: Commit**

```bash
git add workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml \
        workflows/examples/inputs/backlog_priority_items.json
git commit -m "feat: add priority backlog phase stack driver workflow"
```

### Task 4: Make the runtime test pass

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`
- Reference: `workflows/library/backlog_item_design_plan_impl_stack.yaml`
- Reference: `workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml`

**Step 1: Copy the new workflow and library files into the test workspace**

Extend the runtime test helper usage so it copies:

- the new example workflow
- the new library workflow
- the reused existing library phase workflows
- the reused prompt tree
- the sample manifest input

**Step 2: Stub provider outputs for two backlog items**

Use the same current testing style as the existing v2 call-stack runtime tests:

- write artifact target files directly in the temp workspace
- simulate a failed design phase on item 1 by never producing approval
- simulate full approval on item 2

The test should assert:

- ordered processing
- per-item summary outputs exist
- the outer workflow status is `completed`

**Step 3: Run the focused test**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k backlog_priority_design_plan_impl_stack_v2_call -v
```

Expected: PASS

**Step 4: Run collect-only on the module**

Run:

```bash
pytest --collect-only tests/test_workflow_examples_v0.py -q
```

Expected: the new test is collected successfully.

**Step 5: Commit**

```bash
git add tests/test_workflow_examples_v0.py
git commit -m "test: verify backlog priority stack skips failed items"
```

### Task 5: Update workflow catalog and final verification

**Files:**
- Modify: `workflows/README.md`

**Step 1: Add the new example and library workflow entries**

Document:

- the top-level backlog-priority driver workflow
- the per-item library workflow

Call out the important behavior explicitly:

- items are processed in manifest order
- any design/plan/implementation phase failure skips only the current item
- the overall run continues

**Step 2: Run narrow verification**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k "backlog_priority_design_plan_impl_stack_v2_call or workflow_examples_v0_load" -v
```

Expected: PASS

**Step 3: Run the orchestrator dry-run smoke check**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml \
  --dry-run \
  --input backlog_manifest_path=workflows/examples/inputs/backlog_priority_items.json \
  --stream-output
```

Expected: validation successful

**Step 4: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no whitespace or patch-format errors

**Step 5: Commit**

```bash
git add workflows/README.md
git commit -m "docs: catalog priority backlog phase stack workflow"
```

## Notes and Non-Goals

- Do not modify the existing phase workflows just to surface loop-exhaustion subtype details. This design intentionally treats all phase failures the same.
- Do not add prompt-literal assertions.
- Do not redesign the current prompt trees.
- Do not add a new runtime feature to distinguish `repeat_until_iterations_exhausted` from other nested call failures. That is unnecessary for the stated requirement.
- Keep the new workflow additive. Leave existing examples and libraries in place.
