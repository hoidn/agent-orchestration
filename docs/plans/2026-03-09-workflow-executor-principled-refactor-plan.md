# Workflow Executor Principled Refactor Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor `orchestrator/workflow/executor.py` into smaller runtime components without changing external DSL behavior or destabilizing persisted run semantics.

**Architecture:** Treat `WorkflowExecutor` as the long-term coordinator, not the place where every runtime concern lives. Extract subsystems along semantic seams: prompt composition, dataflow bookkeeping, resume planning, finalization, step dispatch, loop execution, and call-frame execution. Keep the external DSL, current `state.json` contract, and visible workflow behavior stable while the refactor is in progress. This repo forbids worktrees for implementation work, so execute in the current checkout and keep commits narrow.

**Tech Stack:** Python runtime modules under `orchestrator/workflow/`, existing state manager and provider/exec layers, pytest characterization and regression coverage, workflow dry-run/smoke validation.

---

## Recommended Design

Recommended approach:
- keep one thin `WorkflowExecutor.execute()` loop as the orchestration shell
- extract stateful subsystems only when they have a clear contract and dedicated tests
- prefer behavior-preserving extractions before any internal redesign
- unify step execution through one `StepRunner` only after shared services exist underneath it

Rejected alternatives:
- split the file mechanically by line count: reduces file size, not coupling
- rewrite the runtime as a new state machine in one pass: too risky
- redesign `state.json` or DSL at the same time: mixes refactor risk with feature risk

## Refactor Principles

1. Preserve external behavior first.
2. Extract by responsibility, not by helper count.
3. Do not duplicate new and old execution paths for long.
4. Keep `WorkflowExecutor` responsible for orchestration, not business logic.
5. Every extraction gets characterization coverage before and after the move.

## Target End State

`WorkflowExecutor` should eventually coordinate a small set of collaborators:
- `ResumePlanner`
- `FinalizationController`
- `PromptComposer`
- `DataflowManager`
- `StepRunner`
- `LoopExecutor`
- `CallExecutor`

It should not directly own prompt reading, consume enforcement, publish bookkeeping, loop replay, finalization bookkeeping, and provider/command dispatch details all at once.

## Scope

In scope:
- `orchestrator/workflow/executor.py`
- small new runtime modules under `orchestrator/workflow/`
- supporting tests that pin current behavior
- smoke validation for representative workflows

Out of scope:
- DSL redesign
- large `StateManager` storage redesign
- demo/scaffold redesign unrelated to executor seams
- speculative performance tuning beyond what falls out of the extraction

## Task Breakdown

### Task 1: Add characterization tests around executor seam behavior

**Files:**
- Create: `tests/test_workflow_executor_characterization.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_structured_control_flow.py`
- Modify: `tests/test_subworkflow_calls.py`

**Step 1: Add narrow tests for resume restart selection**

Cover:
- stale `current_step` vs completed step entries
- loop revisit behavior
- resumed runs re-entering the right top-level step

**Step 2: Add narrow tests for finalization bookkeeping**

Cover:
- body success -> finalization -> outputs export
- body failure + finalization failure secondary diagnostics
- resume from partially completed finalization

**Step 3: Add narrow tests for shared execution expectations**

Cover:
- top-level and loop-nested `assert`
- top-level and loop-nested scalar bookkeeping
- top-level and loop-nested provider/command result normalization

**Step 4: Run the focused characterization set**

Run:

```bash
pytest tests/test_workflow_executor_characterization.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_artifact_dataflow_integration.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py -k "resume or finalization or loop or call" -v
```

Expected:
- all current behavior is pinned before extraction begins

**Step 5: Collect-only for the new module**

Run:

```bash
pytest --collect-only tests/test_workflow_executor_characterization.py -q
```

Expected:
- the new module collects cleanly

**Step 6: Commit**

```bash
git add tests/test_workflow_executor_characterization.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_artifact_dataflow_integration.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py
git commit -m "test: pin workflow executor behavior before refactor"
```

### Task 2: Introduce small runtime contracts before moving logic

**Files:**
- Create: `orchestrator/workflow/runtime_types.py`
- Create: `orchestrator/workflow/runtime_context.py`
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_workflow_executor_characterization.py`

**Step 1: Add minimal runtime dataclasses / typed containers**

Introduce small internal shapes for concepts that are currently passed around as loose dicts:
- execution identity
- runtime context
- normalized step outcome
- next-step routing decision

Keep these internal only; do not change persisted state shape in this task.

**Step 2: Thread the types through `WorkflowExecutor` in place**

Replace the worst loose internal bundles first:
- substitution context
- step identity metadata
- step result normalization handoff

Do not move large behavior blocks yet.

**Step 3: Run the narrow executor characterization tests**

Run:

```bash
pytest tests/test_workflow_executor_characterization.py tests/test_runtime_step_lifecycle.py -k "executor or finalization or loop" -v
```

Expected:
- behavior remains unchanged

**Step 4: Commit**

```bash
git add orchestrator/workflow/runtime_types.py orchestrator/workflow/runtime_context.py orchestrator/workflow/executor.py tests/test_workflow_executor_characterization.py tests/test_runtime_step_lifecycle.py
git commit -m "refactor: introduce workflow executor runtime types"
```

### Task 3: Extract prompt composition and dataflow bookkeeping

**Files:**
- Create: `orchestrator/workflow/prompting.py`
- Create: `orchestrator/workflow/dataflow.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify: `tests/test_artifact_dataflow_integration.py`

**Step 1: Extract prompt-source reading and injection**

Move from `WorkflowExecutor` into `prompting.py`:
- base prompt source reading
- asset injection
- consumes injection
- output-contract suffix assembly
- prompt audit payload preparation

Leave actual file writes / audit persistence coordinated by the executor.

**Step 2: Extract publish/consume bookkeeping**

Move into `dataflow.py`:
- consume preflight
- artifact publish recording
- scalar latest-value helpers if they belong with dataflow

Keep state-manager calls explicit and narrow.

**Step 3: Run focused prompt/dataflow tests**

Run:

```bash
pytest tests/test_prompt_contract_injection.py tests/test_artifact_dataflow_integration.py -v
```

Expected:
- prompt composition and artifact lineage behavior are unchanged

**Step 4: Commit**

```bash
git add orchestrator/workflow/prompting.py orchestrator/workflow/dataflow.py orchestrator/workflow/executor.py tests/test_prompt_contract_injection.py tests/test_artifact_dataflow_integration.py
git commit -m "refactor: extract prompt composition and dataflow services"
```

### Task 4: Extract lifecycle planning for resume and finalization

**Files:**
- Create: `orchestrator/workflow/resume_planner.py`
- Create: `orchestrator/workflow/finalization.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_runtime_step_lifecycle.py`

**Step 1: Extract resume restart planning**

Move into `resume_planner.py`:
- terminal-entry checks
- restart-index determination
- loop/repeat pending-work tests

This module should be pure or near-pure.

**Step 2: Extract finalization bookkeeping/state transitions**

Move into `finalization.py`:
- initial state creation
- activation
- step-start recording
- settled-result projection
- export suppression/completion state changes

Keep terminal run-status writeback in the executor coordinator.

**Step 3: Run focused lifecycle tests**

Run:

```bash
pytest tests/test_resume_command.py tests/test_runtime_step_lifecycle.py -k "resume or finalization" -v
```

Expected:
- lifecycle behavior remains stable under extraction

**Step 4: Commit**

```bash
git add orchestrator/workflow/resume_planner.py orchestrator/workflow/finalization.py orchestrator/workflow/executor.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py
git commit -m "refactor: extract executor lifecycle planning"
```

### Task 5: Introduce a shared `StepRunner`

**Files:**
- Create: `orchestrator/workflow/step_runner.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_for_each_execution.py`
- Modify: `tests/test_scalar_bookkeeping.py`
- Modify: `tests/test_conditional_execution.py`
- Modify: `tests/test_provider_execution.py`

**Step 1: Define the `StepRunner` responsibility**

`StepRunner` should own one-step execution semantics:
- step kind dispatch
- retries
- provider/command/assert/scalar/wait execution handoff
- normalized result assembly

It should not own top-level workflow routing or final run status.

**Step 2: Make top-level execution use `StepRunner` first**

Refactor `WorkflowExecutor.execute()` to call the runner for top-level steps.

**Step 3: Make nested loop execution use the same runner**

Refactor nested `for_each` / `repeat_until` body execution to use the same shared runner instead of bespoke duplicated logic.

**Step 4: Run the focused execution tests**

Run:

```bash
pytest tests/test_for_each_execution.py tests/test_scalar_bookkeeping.py tests/test_conditional_execution.py tests/test_provider_execution.py -v
```

Expected:
- shared execution semantics stay aligned across top-level and nested paths

**Step 5: Commit**

```bash
git add orchestrator/workflow/step_runner.py orchestrator/workflow/executor.py tests/test_for_each_execution.py tests/test_scalar_bookkeeping.py tests/test_conditional_execution.py tests/test_provider_execution.py
git commit -m "refactor: route step execution through shared runner"
```

### Task 6: Extract loop and call engines last

**Files:**
- Create: `orchestrator/workflow/loops.py`
- Create: `orchestrator/workflow/calls.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_for_each_execution.py`
- Modify: `tests/test_structured_control_flow.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_state_manager.py`

**Step 1: Extract loop execution**

Move `for_each` and `repeat_until` body orchestration into `loops.py`, but keep the shared `StepRunner` underneath.

**Step 2: Extract `call` orchestration**

Move call-frame setup, bound-input resolution, resume validation, and callee execution orchestration into `calls.py`.

**Step 3: Keep `WorkflowExecutor` as coordinator**

At the end of this task, `WorkflowExecutor` should mainly:
- load/persist run state
- select the next step
- invoke collaborator modules
- apply routing and terminal status

**Step 4: Run focused loop/call/state tests**

Run:

```bash
pytest tests/test_for_each_execution.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_state_manager.py -k "loop or repeat_until or call or call_frame" -v
```

Expected:
- loop and call behavior remains intact after extraction

**Step 5: Commit**

```bash
git add orchestrator/workflow/loops.py orchestrator/workflow/calls.py orchestrator/workflow/executor.py tests/test_for_each_execution.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_state_manager.py
git commit -m "refactor: extract loop and call execution engines"
```

### Task 7: Final verification and review checkpoint

**Files:**
- No new files required

**Step 1: Run the focused runtime suite**

Run:

```bash
pytest tests/test_workflow_executor_characterization.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_artifact_dataflow_integration.py tests/test_prompt_contract_injection.py tests/test_for_each_execution.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_scalar_bookkeeping.py tests/test_provider_execution.py tests/test_state_manager.py -v
```

Expected:
- all targeted executor/refactor coverage passes

**Step 2: Run collection on any new modules**

Run:

```bash
pytest --collect-only tests/test_workflow_executor_characterization.py -q
```

Expected:
- clean collection

**Step 3: Run a workflow dry-run smoke**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml --dry-run --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json --input design_path=docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md --stream-output
```

Expected:
- workflow validation still succeeds after executor extraction

**Step 4: Request review**

Use `superpowers:requesting-code-review` before merging the refactor branch or stacking further executor changes.

## Notes

- This plan intentionally refines and narrows [2026-03-07-orchestrator-runtime-refactor-implementation-plan.md](/home/ollie/Documents/agent-orchestration/docs/plans/2026-03-07-orchestrator-runtime-refactor-implementation-plan.md) rather than replacing it wholesale.
- The core idea is to extract stable services before introducing the shared execution kernel, not after.
- Do not use git worktrees for this repo even though some generic skills recommend them; the repo-level instructions override that default.
