# Follow-On Workflow V2 Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new `v2.7` rewrite of the follow-on DSL workflow that keeps the current `1.4` workflow in place while demonstrating stable step identity, typed workflow boundaries, and structured review/fix loops without shell gate diamonds or temp counter files.

**Architecture:** Keep the current user-facing behavior: wait for an upstream ADR workflow to finish, draft a plan from the ADR, run a bounded plan review/revise loop, execute implementation work, then run a bounded implementation review/fix loop. Rewrite only the new workflow around `v2.0`/`v2.1`/`v2.6`/`v2.7` features: add stable `id`s, promote external knobs to typed `inputs`/`outputs`, keep internal relpath artifacts for prompt/dataflow handoff, and replace the hand-written `goto` + shell gate loops with `repeat_until` + `match`.

**Tech Stack:** Workflow YAML (`v2.7`), existing Codex provider prompts copied into an isolated prompt tree, workflow signature inputs/outputs, structured `match`, structured `repeat_until`, pytest workflow smoke tests, orchestrator dry-run validation.

---

## Design Summary

### Recommended Approach

Create a new example workflow:

- `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml`

Keep the existing workflow unchanged:

- `workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml`

Create a new prompt tree for the rewrite instead of sharing the old prompt files:

- `prompts/workflows/dsl_follow_on_plan_impl_loop_v2/`

This keeps the old workflow stable, makes the new example a clean migration target, and avoids hidden coupling when prompts evolve later.

### Non-Goals

- Do not replace or rename the existing `1.4` workflow.
- Do not introduce `call`/`imports`; that would mix reusable-subworkflow concerns into a migration whose main value is structured control and typed boundaries.
- Do not force cycle-specific report filenames unless the implementation can do so cleanly without reintroducing shell-managed counters. Fixed report paths plus artifact lineage are acceptable for this rewrite.

### New Workflow Shape

The new workflow should target `version: "2.7"` and use this high-level structure:

1. `WaitForUpstreamStateFile`
2. `WaitForUpstreamCompletion`
3. `InitializeArtifactPaths`
4. `PublishDesignInput`
5. `DraftPlan`
6. `PlanReviewLoop` (`repeat_until`)
7. `ExecuteImplementation`
8. `ImplementationReviewLoop` (`repeat_until`)
9. `PublishFinalOutputs`

`PlanReviewLoop` should contain:

- `ReviewPlan`
- `RoutePlanDecision` (`match` on `APPROVE|REVISE`)
- `RevisePlan` only in the `REVISE` case
- loop-frame output `review_decision`

`ImplementationReviewLoop` should contain:

- `ReviewImplementation`
- `RouteImplementationDecision` (`match` on `APPROVE|REVISE`)
- `FixImplementation` only in the `REVISE` case
- loop-frame output `review_decision`

### External Boundary

Use typed workflow `inputs` for the values that are currently implicit or hard-coded:

- `upstream_state_path` (`relpath`, required, `must_exist_target: true`)
- `design_path` (`relpath`, default `docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md`, `under: docs/plans`, `must_exist_target: true`)

Keep the review/fix budgets as literal workflow constants for the first rewrite.
Current loader/runtime behavior requires `repeat_until.max_iterations` to be an integer literal, so do not model those budgets as workflow inputs in this tranche.

Use typed workflow `outputs` for the final exported results:

- `plan_path`
- `execution_report_path`
- `implementation_review_report_path`
- `implementation_review_decision`

Because the internal `plan` and `execution_report` artifacts have multiple producers, add one small terminal publication step that republishes the final selected values under stable single-producer artifact names, then export workflow outputs from that step.

### Rejected Alternatives

1. **Thin `2.1` uplift only**
   - Pros: smaller diff
   - Cons: keeps the shell gates, file counters, and raw `goto` diamonds, which is where most of the current workflow complexity lives

2. **Factor the loops into reusable library workflows with `call`**
   - Pros: reuse
   - Cons: much larger scope, requires `v2.5`, and changes the migration from “show modern authoring” to “design reusable subworkflow APIs”

The recommended approach is the smallest rewrite that actually captures the benefits the migration is supposed to demonstrate.

### Runtime Constraints To Respect

- Do not rely on `wait_for.glob` for the input-backed upstream state path in this rewrite. The runtime path exercised during implementation did not safely substitute the input there. Use a small command-based poll step for the upstream state file instead.
- Do not attempt to parameterize `repeat_until.max_iterations` via `${inputs.*}`. The loader currently requires a literal integer there.

---

### Task 1: Add Failing Smoke Coverage For The New Workflow

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add the new example filename to the load test**

Add:

```python
"dsl_follow_on_plan_impl_review_loop_v2.yaml",
```

to `EXAMPLE_FILES`.

**Step 2: Add a new runtime smoke test**

Create:

```python
def test_dsl_follow_on_plan_impl_review_loop_v2_runtime(tmp_path: Path):
    ...
```

Cover this exact behavior:

- upstream state input is bound through `bound_inputs`
- `DraftPlan` runs once
- `ReviewPlan` returns `REVISE` then `APPROVE`
- `RevisePlan` runs once inside `PlanReviewLoop`
- `ExecuteImplementation` runs once
- `ReviewImplementation` returns `REVISE` then `APPROVE`
- `FixImplementation` runs once inside `ImplementationReviewLoop`
- the workflow completes
- `workflow_outputs` exports the final relpaths/decision
- the state does not depend on `PlanReviewGate`, `PlanCycleGate`, `ImplementationReviewGate`, or `ImplementationCycleGate`

Use the same mocked-provider pattern already used by:

- `test_dsl_follow_on_plan_impl_review_loop_runtime`
- `test_repeat_until_demo_runtime`
- `test_match_demo_runtime`
- `test_workflow_signature_demo_runtime`

**Step 3: Run the new test before the workflow exists**

Run:

```bash
pytest tests/test_workflow_examples_v0.py::test_dsl_follow_on_plan_impl_review_loop_v2_runtime -v
```

Expected: fail because the new workflow file does not exist yet.

### Task 2: Add A Stable Input Fixture For Dry-Run And Tests

**Files:**
- Create: `workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json`

**Step 1: Add a minimal example upstream state fixture**

Write:

```json
{"status":"completed"}
```

This file exists to satisfy `v2.1` relpath input binding in example dry-runs and smoke tests. It is not a queue or state migration feature.

**Step 2: Reuse the fixture in the new runtime smoke test**

Copy it into the tmp workspace in the same way the signature and prompt fixtures are copied now.

### Task 3: Create An Isolated Prompt Tree For The V2 Rewrite

**Files:**
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2/draft_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2/review_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2/revise_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2/implement_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2/review_implementation.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2/fix_implementation.md`

**Step 1: Copy the current prompt set as the starting point**

Start from the existing prompt tree:

- `prompts/workflows/dsl_follow_on_plan_impl_loop/`

Do not try to redesign prompt behavior in the same pass.

**Step 2: Make only boundary-aware edits**

Adjust wording only where the new workflow needs it:

- refer to the same `design`, `plan`, `execution_report`, and review artifacts
- avoid references to removed shell gates or counter files
- keep the existing “unfinished plan work is blocking” behavior in the implementation review/fix prompts

**Step 3: Keep the new prompt tree independent**

The new workflow must not read prompt files from the old prompt directory.

### Task 4: Author The New `v2.7` Workflow

**Files:**
- Create: `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml`

**Step 1: Declare the new workflow boundary**

Set:

```yaml
version: "2.7"
name: "dsl-follow-on-plan-impl-review-loop-v2"
```

Add top-level `inputs` for:

- `upstream_state_path`
- `design_path`

Keep provider defaults in `context` unless there is a concrete need to externalize them.

**Step 2: Add stable `id` values to durable authored steps**

Every long-lived step and every structured statement should get an authored `id`, especially:

- upstream wait/validation steps
- `DraftPlan`
- `PlanReviewLoop`
- `RoutePlanDecision`
- `ExecuteImplementation`
- `ImplementationReviewLoop`
- `RouteImplementationDecision`
- final publication step

The point of this rewrite is to demonstrate `v2.0` identity discipline, not merely to satisfy parsing.

**Step 3: Keep internal relpath artifacts, but move the external contract to `inputs`/`outputs`**

Retain internal artifacts for prompt/dataflow:

- `design`
- `plan`
- `plan_review_report`
- `plan_review_decision`
- `execution_report`
- `implementation_review_report`
- `implementation_review_decision`

But stop hard-coding the external boundary in `state/*.txt` bootstrap logic.

Add one adapter step:

- `PublishDesignInput`

It should validate `${inputs.design_path}` and publish the internal `design` artifact so downstream provider steps can keep using `consumes`/`prompt_consumes`.

**Step 4: Replace the plan loop with `repeat_until` + `match`**

Use this shape:

```yaml
- name: PlanReviewLoop
  id: plan_review_loop
  repeat_until:
    id: plan_review_loop_body
    max_iterations: ${inputs.max_plan_iterations}
    outputs:
      review_decision:
        kind: scalar
        type: enum
        allowed: [APPROVE, REVISE]
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
      - name: RoutePlanDecision
        match:
          ref: self.steps.ReviewPlan.artifacts.plan_review_decision
          cases:
            APPROVE: ...
            REVISE: ...
```

The `REVISE` case should run `RevisePlan`.
The `APPROVE` case should not shell out just to route; use a tiny scalar-setting step or equivalent branch-local output.

**Step 5: Replace the implementation loop with `repeat_until` + `match`**

Keep the first implementation pass separate:

- `ExecuteImplementation`

Then use one structured loop for review/fix:

```yaml
- name: ImplementationReviewLoop
  id: implementation_review_loop
  repeat_until:
    ...
```

The `REVISE` case should run `FixImplementation`.
The `APPROVE` case should terminate the loop by producing an `APPROVE` loop-frame output.

**Step 6: Publish final outputs from a single terminal step**

Add one small terminal step after the loops, for example:

- `PublishFinalWorkflowOutputs`

It should republish:

- final `plan_path`
- final `execution_report_path`
- final `implementation_review_report_path`
- final `implementation_review_decision`

under stable single-producer artifact names so top-level workflow `outputs` can legally point at one source step.

### Task 5: Update The Workflow Catalog

**Files:**
- Modify: `workflows/README.md`

**Step 1: Add the new workflow to the catalog**

Add one row describing it as the structured `v2.7` rewrite of the follow-on workflow, emphasizing:

- typed `inputs`/`outputs`
- structured `match`
- structured `repeat_until`
- old `1.4` workflow retained for comparison

### Task 6: Make The New Test Pass

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`
- Create/modify: all files from Tasks 2-5

**Step 1: Run the targeted runtime smoke test until it passes**

Run:

```bash
pytest tests/test_workflow_examples_v0.py::test_dsl_follow_on_plan_impl_review_loop_v2_runtime -v
```

**Step 2: Run the load test**

Run:

```bash
pytest tests/test_workflow_examples_v0.py::test_workflow_examples_v0_load -v
```

**Step 3: If test files or names changed, run collection**

Run:

```bash
pytest --collect-only tests/test_workflow_examples_v0.py -q
```

### Task 7: Run Workflow Validation Checks

**Files:**
- No new file changes

**Step 1: Run the example-focused workflow smoke slice**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k "follow_on_plan_impl_review_loop_v2 or workflow_examples_v0_load" -v
```

**Step 2: Run a dry-run smoke check for the new workflow**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml \
  --dry-run \
  --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json \
  --input design_path=docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md \
  --stream-output
```

Expected: validation succeeds without executing the workflow.

**Step 3: Check diff cleanliness**

Run:

```bash
git diff --check -- \
  docs/plans/2026-03-09-follow-on-workflow-v2-rewrite-plan.md \
  workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml \
  workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json \
  prompts/workflows/dsl_follow_on_plan_impl_loop_v2/draft_plan.md \
  prompts/workflows/dsl_follow_on_plan_impl_loop_v2/review_plan.md \
  prompts/workflows/dsl_follow_on_plan_impl_loop_v2/revise_plan.md \
  prompts/workflows/dsl_follow_on_plan_impl_loop_v2/implement_plan.md \
  prompts/workflows/dsl_follow_on_plan_impl_loop_v2/review_implementation.md \
  prompts/workflows/dsl_follow_on_plan_impl_loop_v2/fix_implementation.md \
  workflows/README.md \
  tests/test_workflow_examples_v0.py
```

### Task 8: Commit In Coherent Chunks

**Files:**
- No new files; git only

**Step 1: Commit the test + fixture + workflow skeleton**

```bash
git add \
  workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json \
  workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml \
  tests/test_workflow_examples_v0.py
git commit -m "feat: add v2 follow-on workflow example"
```

**Step 2: Commit prompt + docs follow-ups**

```bash
git add \
  prompts/workflows/dsl_follow_on_plan_impl_loop_v2 \
  workflows/README.md
git commit -m "docs: add v2 follow-on workflow prompts and catalog entry"
```
