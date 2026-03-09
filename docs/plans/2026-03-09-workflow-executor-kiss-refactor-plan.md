# Workflow Executor KISS Consolidation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify the already-refactored `orchestrator/workflow/executor.py` and its new collaborators so the runtime is easier to reason about without introducing a second layer of framework-like abstractions or changing external workflow behavior.

**Architecture:** Treat the current tree as a post-extraction transitional state, not a greenfield refactor. Keep one concrete `WorkflowExecutor` as the kernel, keep the extracted concrete modules that are earning their keep, and redesign only where the first-pass refactor left muddled authority boundaries. In practice that means tightening who owns routing and run status, shrinking or removing abstractions that merely forward back into the executor, and extracting one or two remaining seams only if they materially simplify the kernel.

**Tech Stack:** Python runtime modules under `orchestrator/workflow/`, existing `StateManager`, provider/exec layers, pytest regression coverage, workflow dry-run/smoke validation.

---

## Current State

The earlier principled refactor plan has already been implemented in significant part. The codebase now contains:
- `prompting.py`
- `dataflow.py`
- `calls.py`
- `resume_planner.py`
- `finalization.py`
- `runtime_types.py`
- `runtime_context.py`
- `step_runner.py`

But the refactor is not finished in the architectural sense:
- `executor.py` is still `3519` LOC
- `execute()` is still about `487` LOC
- `StepRunner` currently acts mostly as a dispatcher back into executor methods
- provider/command transport is still largely in `executor.py`
- outcome/persistence logic is still mixed into the kernel

So this plan is deliberately a **consolidation** plan, not a “split the file again” plan.

## What The Prior Refactor Got Right

Keep these:
- characterization-first discipline
- `WorkflowExecutor` remains the coordinator
- extracted prompt/dataflow/finalization/call seams
- no DSL or `state.json` redesign during the refactor

## What Needs Correction

1. `StepRunner` is too close to a pass-through abstraction.
2. Authority boundaries are still implicit.
3. Provider/command transport and outcome persistence still muddy the kernel.
4. Some extracted modules may be keeping indirection without enough simplification.

## Audit Results

This section records the current keep/shrink/remove decisions so the next tasks do not repeat the first refactor’s mistakes.

### Keep

- `ResumePlanner`
  - Small, near-pure, and clearly responsible for restart-point selection.
  - It does not depend on executor internals and already matches the desired authority boundary.

- `FinalizationController`
  - Concrete, stateful, and cohesive.
  - It owns workflow-finalization bookkeeping without trying to own top-level routing.
  - This is a real seam, not just file extraction.

- `PromptComposer`
  - Small enough and fully detached from executor internals.
  - It is doing real prompt assembly work, not merely forwarding into the kernel.

### Keep, But Watch Scope

- `DataflowManager`
  - It is large, but it owns a real seam: publish/consume bookkeeping and consume-bundle writing.
  - It is not the first abstraction to remove because it already has explicit injected dependencies and no direct executor back-references.
  - It should be split only if a concrete sub-seam emerges, not just because it is large.

- `CallExecutor`
  - It owns real call-specific behavior: bound-input resolution, write-root validation, resume checksum validation, and child-executor orchestration.
  - But it is still too coupled to `self.executor`.
  - The follow-on work should reduce that coupling, not inline the whole thing back into `executor.py`.

### Shrink Or Remove

- `StepRunner`
  - This is the weakest current abstraction.
  - It branches on step kind, immediately calls private executor methods, and then persists results through executor methods again.
  - It currently reduces very little conceptual load and adds an extra hop in the most important control path.
  - Default recommendation: remove it unless it can be reduced to a very small dispatch helper with no lifecycle or persistence authority.

### Not Yet Extracted

- Provider/command transport
  - Still mostly lives in `executor.py`.
  - This is the strongest remaining candidate for a new concrete module because it is both large and semantically self-contained.

- Outcome/result persistence helpers
  - Still muddy the kernel.
  - Extract only if the seam can be kept concrete and routing-neutral.

## KISS Constraints

These are mandatory:

1. Keep `WorkflowExecutor` as one concrete kernel.
2. No abstract base classes for step execution.
3. No plugin system, registry, or event bus.
4. No “framework” layer above the current runtime.
5. Do not preserve abstractions that only forward to executor methods.
6. Do not extract new modules unless they reduce both LOC and conceptual load.

## Authority Boundaries

This is the main design rule for the consolidation.

`WorkflowExecutor` must remain the sole owner of:
- current top-level step cursor
- current-step lifecycle
- transition and visit guards
- restart/resume cursor selection
- top-level routing decisions
- top-level run status

Collaborators may:
- prepare prompts
- enforce consume/publish bookkeeping
- execute provider/command transport
- orchestrate call-frame setup/execution
- assemble normalized result payloads

Collaborators may not:
- mutate top-level run status
- advance the top-level cursor directly
- make hidden routing decisions behind the kernel’s back

## Recommended End State

At the end of this consolidation, the runtime should look like:

- `WorkflowExecutor`
  - small orchestration kernel
  - explicit routing / status authority

- `PromptComposer`
  - kept if still materially simpler than inlining

- `DataflowManager`
  - kept if publish/consume bookkeeping remains meaningfully isolated

- `CallExecutor`
  - kept if it owns real call orchestration instead of thin forwarding

- `StepRunner`
  - either reduced to a very small step-kind dispatch helper
  - or removed entirely if it adds more hops than value

- possible new small modules only if the seam is real:
  - `provider_execution.py`
  - `outcomes.py`

## Design Heuristics

Use these to decide whether a module stays, shrinks, or disappears:

- Keep it if it owns a coherent responsibility with its own tests.
- Shrink it if it mostly relays into executor internals.
- Delete it if removing it makes the control path shorter and clearer.
- Extract a new module only when the current code is both large and semantically self-contained.

## Scope

In scope:
- `orchestrator/workflow/executor.py`
- existing extracted runtime modules under `orchestrator/workflow/`
- one or two new modules if the seam is justified by the audit
- focused regression tests
- representative workflow dry-run/smoke checks

Out of scope:
- DSL redesign
- `StateManager` storage redesign
- performance tuning as a primary goal
- general runtime “architecture cleanup” unrelated to the executor kernel

## Task Breakdown

### Task 1: Audit the extracted runtime seams against KISS

**Files:**
- Modify: `docs/plans/2026-03-09-workflow-executor-kiss-refactor-plan.md`
- Inspect: `orchestrator/workflow/executor.py`
- Inspect: `orchestrator/workflow/step_runner.py`
- Inspect: `orchestrator/workflow/calls.py`
- Inspect: `orchestrator/workflow/prompting.py`
- Inspect: `orchestrator/workflow/dataflow.py`
- Inspect: `orchestrator/workflow/finalization.py`

**Step 1: Record module-by-module keep/shrink/delete decisions**

Write down for each extracted module:
- what authority it owns
- what it still delegates back into the executor
- whether it is earning its keep

**Step 2: Identify the minimum necessary next cuts**

Decide explicitly:
- keep `PromptComposer` / `DataflowManager` as-is or simplify them
- keep, shrink, or remove `StepRunner`
- whether provider/command transport deserves its own module now
- whether outcome/persistence helpers deserve their own module now

**Step 3: Do not change code in this task**

This task exists to prevent another round of mechanical extraction.

**Step 4: Commit the updated plan note if needed**

```bash
git add docs/plans/2026-03-09-workflow-executor-kiss-refactor-plan.md
git commit -m "docs: record workflow executor consolidation decisions"
```

### Task 2: Pin the current kernel authority with characterization tests

**Files:**
- Create: `tests/test_workflow_executor_characterization.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_provider_execution.py`

**Step 1: Add tests around top-level kernel authority**

Cover:
- stale `current_step` vs completed entries
- loop revisit behavior during resume
- top-level routing after step completion
- terminal status changes only through the kernel

**Step 2: Add tests around step-result persistence**

Cover:
- normalized outcomes
- persisted step result shape
- current-step clearing
- routing after persistence

**Step 3: Run the characterization set**

Run:

```bash
pytest tests/test_workflow_executor_characterization.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_subworkflow_calls.py tests/test_provider_execution.py -k "resume or routing or outcome or call or provider" -v
```

Expected:
- current post-refactor behavior is pinned before further redesign

**Step 4: Collect-only for the new module**

Run:

```bash
pytest --collect-only tests/test_workflow_executor_characterization.py -q
```

Expected:
- clean collection

**Step 5: Commit**

```bash
git add tests/test_workflow_executor_characterization.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_subworkflow_calls.py tests/test_provider_execution.py
git commit -m "test: pin workflow executor consolidation behavior"
```

### Task 3: Decide the fate of `StepRunner` and remove needless indirection

**Files:**
- Modify: `orchestrator/workflow/step_runner.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_for_each_execution.py`
- Modify: `tests/test_scalar_bookkeeping.py`
- Modify: `tests/test_structured_control_flow.py`

**Step 1: Measure what `StepRunner` actually owns**

If it mostly:
- branches on step kind
- immediately calls executor private methods
- persists through executor again

then it is not a real seam.

**Step 2: Choose one of two paths**

Path A: keep `StepRunner` only as a tiny dispatch helper
- no lifecycle authority
- no persistence authority
- no hidden routing

Path B: inline it back into the executor and remove the extra hop

Recommended default:
- choose Path B unless the simplified `StepRunner` remains obviously useful after the audit

**Step 3: Run focused execution tests**

Run:

```bash
pytest tests/test_for_each_execution.py tests/test_scalar_bookkeeping.py tests/test_structured_control_flow.py tests/test_workflow_executor_characterization.py -k "loop or scalar or assert or structured or routing" -v
```

Expected:
- execution behavior is unchanged while indirection decreases

**Step 4: Commit**

```bash
git add orchestrator/workflow/step_runner.py orchestrator/workflow/executor.py tests/test_for_each_execution.py tests/test_scalar_bookkeeping.py tests/test_structured_control_flow.py tests/test_workflow_executor_characterization.py
git commit -m "refactor: simplify workflow step dispatch"
```

### Task 4: Extract provider/command transport only if the seam is still real

**Files:**
- Create if justified: `orchestrator/workflow/provider_execution.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_provider_execution.py`
- Modify: `tests/test_workflow_executor_characterization.py`

**Step 1: Inspect the current provider/command path in `executor.py`**

Specifically evaluate:
- invocation preparation
- substitution context assembly
- output capture normalization
- expected output contract application

**Step 2: Extract only the transport-heavy parts**

If extracted, move:
- provider/command invocation preparation
- transport normalization
- output-contract application helpers

Do not move:
- top-level routing
- current-step lifecycle
- top-level run status

If inspection shows the seam is still too entangled, do not create the module yet. Simplify in place first.

**Step 3: Run focused provider tests**

Run:

```bash
pytest tests/test_provider_execution.py tests/test_workflow_executor_characterization.py -k "provider or command or output_contract or outcome" -v
```

Expected:
- provider behavior stays stable

**Step 4: Commit**

```bash
git add orchestrator/workflow/executor.py orchestrator/workflow/provider_execution.py tests/test_provider_execution.py tests/test_workflow_executor_characterization.py
git commit -m "refactor: isolate provider execution transport"
```

### Task 5: Consolidate outcome/persistence handling

**Files:**
- Create if justified: `orchestrator/workflow/outcomes.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_workflow_executor_characterization.py`

**Step 1: Separate result assembly from routing**

Move or isolate:
- normalized outcome attachment
- persisted result shape assembly
- step-summary projection if it belongs with outcomes

Keep in kernel:
- when to persist
- what step/routing happens next
- final run status

**Step 2: Keep this extraction concrete**

No “outcome strategy” abstraction.
Use plain functions or a tiny concrete helper if needed.

**Step 3: Run focused lifecycle tests**

Run:

```bash
pytest tests/test_runtime_step_lifecycle.py tests/test_workflow_executor_characterization.py -k "outcome or persistence or current_step or status" -v
```

Expected:
- persisted runtime behavior remains unchanged

**Step 4: Commit**

```bash
git add orchestrator/workflow/executor.py orchestrator/workflow/outcomes.py tests/test_runtime_step_lifecycle.py tests/test_workflow_executor_characterization.py
git commit -m "refactor: isolate workflow outcome persistence helpers"
```

### Task 6: Re-evaluate extracted modules and simplify the kernel last

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/calls.py`
- Modify: `orchestrator/workflow/prompting.py`
- Modify: `orchestrator/workflow/dataflow.py`
- Modify: `tests/test_workflow_executor_characterization.py`

**Step 1: Remove transitional glue**

Delete:
- wrappers retained only because earlier tasks were incomplete
- duplicate helpers that now exist in two places
- module methods that only bounce back into executor

**Step 2: Make `execute()` read like a kernel**

At the end of this task, `execute()` should mainly:
- choose the next top-level step
- initialize the step lifecycle
- delegate to a real helper
- apply routing and final status

**Step 3: Run the focused consolidation suite**

Run:

```bash
pytest tests/test_workflow_executor_characterization.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_subworkflow_calls.py tests/test_provider_execution.py tests/test_for_each_execution.py tests/test_scalar_bookkeeping.py tests/test_structured_control_flow.py -v
```

Expected:
- the runtime still behaves the same, with a smaller and clearer kernel

**Step 4: Commit**

```bash
git add orchestrator/workflow/executor.py orchestrator/workflow/calls.py orchestrator/workflow/prompting.py orchestrator/workflow/dataflow.py tests/test_workflow_executor_characterization.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_subworkflow_calls.py tests/test_provider_execution.py tests/test_for_each_execution.py tests/test_scalar_bookkeeping.py tests/test_structured_control_flow.py
git commit -m "refactor: consolidate workflow executor kernel"
```

### Task 7: Final verification and review checkpoint

**Files:**
- No new files required

**Step 1: Run the focused runtime suite**

Run:

```bash
pytest tests/test_workflow_executor_characterization.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_subworkflow_calls.py tests/test_provider_execution.py tests/test_prompt_contract_injection.py tests/test_artifact_dataflow_integration.py tests/test_for_each_execution.py tests/test_scalar_bookkeeping.py tests/test_structured_control_flow.py tests/test_workflow_examples_v0.py -k "executor or resume or call or provider or routing or follow_on_plan_impl_review_loop_v2_call or design_plan_impl_review_stack_v2_call" -v
```

Expected:
- targeted executor/runtime coverage passes

**Step 2: Run collection on the characterization module**

Run:

```bash
pytest --collect-only tests/test_workflow_executor_characterization.py -q
```

Expected:
- clean collection

**Step 3: Run representative workflow dry-runs**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml --dry-run --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json --input design_path=docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md --stream-output
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run --stream-output
```

Expected:
- representative `call` and structured-control workflows still validate

**Step 4: Request review**

Use `superpowers:requesting-code-review` before merging any consolidation branch or stacking feature work on top of it.

## Success Criteria

This plan succeeds only if:
- `executor.py` is materially easier to follow
- top-level authority boundaries are explicit
- at least one non-paying abstraction is removed or sharply reduced
- new modules are added only where they clearly simplify the kernel
- workflow behavior and persisted-state semantics remain stable

## Failure Modes To Avoid

Stop and revise if the consolidation drifts into:
- preserving all existing abstractions “because they already exist”
- adding a third layer of wrappers around the executor
- extracting modules that still require intimate knowledge of executor internals
- replacing one god object with a network of thin god-adjacent helpers
- optimizing for line count instead of conceptual clarity
