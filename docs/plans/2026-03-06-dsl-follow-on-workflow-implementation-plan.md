# DSL Follow-On Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new example workflow that waits for the active DSL ADR review/fix run to finish, drafts an implementation plan from the ADR, runs a bounded plan review/fix loop, then runs a bounded implementation review/fix loop.

**Architecture:** Reuse the repo's existing v1.4 artifact dataflow pattern instead of inventing a new loop shape. The workflow will publish the ADR as a `design` artifact, keep plan and execution outputs as typed relpath artifacts, route decisions through enum files, and bound both loops with shell gates plus explicit max-cycle failure steps.

**Tech Stack:** Workflow DSL v1.4, Codex provider templates, markdown prompt files, pytest example smoke tests, orchestrator dry-run validation.

---

### Task 1: Define the workflow contract and file layout

**Files:**
- Create: `workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/draft_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/review_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/revise_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/implement_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/review_implementation.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/fix_implementation.md`
- Modify: `workflows/README.md`

**Step 1: Define the state and artifact model**

Write the workflow around these deterministic files:

```text
state/design_path.txt
state/plan_path.txt
state/plan_review_report_path.txt
state/plan_review_decision.txt
state/execution_report_path.txt
state/implementation_review_report_path.txt
state/implementation_review_decision.txt
state/plan_cycle.txt
state/implementation_cycle.txt
```

Publish these artifacts:

```text
design
plan
plan_review_report
plan_review_decision
execution_report
implementation_review_report
implementation_review_decision
```

**Step 2: Define the wait contract**

Use:

```yaml
- name: WaitForUpstreamStateFile
  wait_for:
    glob: ".orchestrate/runs/20260307T073452Z-f1wx0q/state.json"
    timeout_sec: 86400
    poll_ms: 1000
    min_count: 1
```

Then add a command step that polls that `state.json` until `status != "running"` and exits non-zero unless the terminal status is `completed`. Use the literal current run id here too; `wait_for.glob` is not a safe place to depend on variable substitution in the current runtime.

**Step 3: Define the loop routing**

Use this high-level graph:

```text
WaitForUpstreamStateFile
-> WaitForUpstreamCompletion
-> InitializeWorkflowState
-> PublishDesign
-> DraftPlan
-> ReviewPlan
-> PlanReviewGate
-> ExecuteImplementation

PlanReviewGate failure -> PlanCycleGate -> RevisePlan -> IncrementPlanCycle -> ReviewPlan

ExecuteImplementation
-> ReviewImplementation
-> ImplementationReviewGate
-> _end

ImplementationReviewGate failure
-> ImplementationCycleGate
-> FixImplementation
-> IncrementImplementationCycle
-> ReviewImplementation
```

Add terminal failure steps for exhausted plan and implementation cycles.

### Task 2: Write the workflow YAML

**Files:**
- Create: `workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml`
- Modify: `workflows/README.md`

**Step 1: Write the failing validation target**

Draft the YAML first, then validate it with:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml --dry-run
```

Expected first result while authoring: schema or contract errors until all steps and paths line up.

**Step 2: Implement the minimal valid workflow**

Use `version: "1.4"` and a single `codex` provider:

```yaml
providers:
  codex:
    command: ["codex", "exec", "--model", "${model}", "--config", "reasoning_effort=${effort}"]
    input_mode: "stdin"
    defaults:
      model: "${context.workflow_model}"
      effort: "${context.workflow_effort}"
```

Set context defaults:

```yaml
context:
  max_plan_iterations: "10"
  max_impl_iterations: "10"
  workflow_model: "gpt-5.4"
  workflow_effort: "high"
```

Implement `PublishDesign` as a command step that validates `docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md` exists, then publishes it from `state/design_path.txt`.

**Step 3: Add bounded loop gates**

Plan loop gate:

```bash
test "$(cat state/plan_review_decision.txt)" = "APPROVE"
```

Cycle cap:

```bash
test "$(cat state/plan_cycle.txt)" -lt "${context.max_plan_iterations}"
```

Implementation loop equivalents should use `state/implementation_review_decision.txt` and `state/implementation_cycle.txt`.

**Step 4: Update the workflow catalog**

Add one row to `workflows/README.md` describing the new example and its purpose.

### Task 3: Write simple prompt files

**Files:**
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/draft_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/review_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/revise_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/implement_plan.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/review_implementation.md`
- Create: `prompts/workflows/dsl_follow_on_plan_impl_loop/fix_implementation.md`

**Step 1: Keep the prompts narrow**

Draft prompt:
- read consumed `design`
- write the plan to the path stored in `state/plan_path.txt`
- keep the plan concrete and implementation-oriented

Plan review prompt:
- reuse the principal-engineer framing from the ADR review prompt
- review the current plan against the design
- write markdown to the path stored in `state/plan_review_report_path.txt`
- write `APPROVE` or `REVISE` to `state/plan_review_decision.txt`
- approve only when there is no `## High` section and the plan is executable

Revise prompt:
- read consumed `design`, `plan`, and `plan_review_report`
- update the plan in place to address the review

Implementation prompt:
- read consumed `design` and `plan`
- implement the approved plan in the repo
- write a concise execution report to the path stored in `state/execution_report_path.txt`

Implementation review prompt:
- reuse the principal-engineer framing
- review the implementation against the design, plan, and execution report
- write markdown to the path stored in `state/implementation_review_report_path.txt`
- write `APPROVE` or `REVISE` to `state/implementation_review_decision.txt`
- approve only when there is no `## High` section

Fix prompt:
- read consumed `design`, `plan`, `execution_report`, and `implementation_review_report`
- fix the repo in place
- refresh the execution report for the next review pass

### Task 4: Extend example workflow tests

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add the example to loader coverage**

Append the new YAML filename to `EXAMPLE_FILES`.

**Step 2: Write the runtime smoke test**

Add a new test that:
- copies the workflow and prompt files into a temp workspace
- copies `docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md`
- seeds `.orchestrate/runs/20260307T073452Z-f1wx0q/state.json` with `{"status":"completed"}`
- mocks provider calls in this order:

```text
DraftPlan
ReviewPlan
RevisePlan
ReviewPlan
ExecuteImplementation
ReviewImplementation
FixImplementation
ReviewImplementation
```

- makes the first plan review write `REVISE`, the second `APPROVE`
- makes the first implementation review write `REVISE`, the second `APPROVE`

**Step 3: Assert loop behavior**

Assert:
- run status is `completed`
- provider call count is `8`
- plan artifacts were published by both `DraftPlan` and `RevisePlan`
- execution report artifacts were published by both `ExecuteImplementation` and `FixImplementation`
- `FixImplementation` consumed the first implementation review artifact version
- review prompts include the principal-engineer framing and consumed artifact paths

### Task 5: Run visible verification

**Files:**
- No file changes

**Step 1: Run the targeted pytest module**

```bash
pytest tests/test_workflow_examples_v0.py -v
```

Expected: all tests in the module pass, including the new workflow smoke test.

**Step 2: Run the required workflow smoke validation**

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml --dry-run
```

Expected: loader and runtime validation succeed with no contract violations.
