# Orchestrator Runtime Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce architecture risk in `orchestrator/` by unifying step execution semantics, introducing qualified execution identity for nested steps, and extracting the highest-churn bookkeeping out of `WorkflowExecutor`.

**Architecture:** Keep the DSL and persisted user-facing state contract stable where possible, but introduce internal execution identity and shared runtime services underneath it. Refactor in narrow slices: add characterization tests first, then land identity/dataflow changes, then unify command/provider execution, then collapse duplicate top-level vs loop execution paths.

**Tech Stack:** Python 3.11+, pytest, YAML workflows, current `orchestrator/` runtime modules.

---

## Scope

This plan targets the architectural issues identified in the audit:
- nested `for_each` steps share bare producer/consumer identities across iterations
- provider execution and command execution use different subprocess/capture/masking paths
- top-level and nested step execution are partially duplicated and drifting
- `WorkflowExecutor` owns too many unrelated responsibilities

## Non-Goals

- Do not redesign the external DSL in this pass.
- Do not change demo trial mechanics except where they depend on runtime refactors.
- Do not attempt a full `StateManager` storage redesign in the same tranche.
- Do not tackle imports/call/reusable subworkflows here; this refactor should make that future work safer.

## Success Criteria

- Nested loop executions have qualified internal identities for lineage/freshness bookkeeping.
- Top-level and loop steps use the same execution path for command/provider/assert/scalar behavior or a single shared execution core.
- Provider outputs are masked and captured through the same policy as command outputs.
- `WorkflowExecutor` shrinks materially because dataflow/control-flow/execution concerns move behind smaller modules.
- Existing visible runtime tests still pass, with new tests covering loop identity and shared execution behavior.

## Task Ordering

1. Lock behavior with characterization tests.
2. Introduce qualified execution identity and dataflow scoping.
3. Unify process execution/capture/masking for commands and providers.
4. Collapse duplicated top-level vs loop execution paths.
5. Extract bookkeeping services from `WorkflowExecutor`.
6. Run focused runtime smoke checks and request review.

---

### Task 1: Add Characterization and Refactor-Safety Tests

**Files:**
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_for_each_execution.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Create: `tests/test_workflow_nested_identity.py`
- Create: `tests/test_provider_output_masking.py`

**Step 1: Write failing tests for qualified nested identities**

Add tests that express the desired internal behavior without breaking current external compatibility:
- nested loop publications should record distinct internal producer identities per iteration
- loop consume freshness should be tracked per qualified nested execution, not one shared bare inner step name
- legacy flattened compatibility views can still exist in persisted state

Start in `tests/test_workflow_nested_identity.py` with cases such as:
- one loop, two iterations, same inner step name publishing one artifact each
- downstream consumer selecting latest successful version without alias collision
- freshness `since_last_consume` inside loop not poisoning sibling iterations

**Step 2: Write failing tests for provider masking parity**

In `tests/test_provider_output_masking.py`, add tests proving provider execution results are masked the same way as command execution results for:
- text capture
- lines capture
- JSON capture

Use a fake provider or mock provider executor result; do not rely on real CLIs.

**Step 3: Tighten existing loop execution tests to cover supported nested step types**

In `tests/test_for_each_execution.py`, add assertions around:
- nested `assert`
- nested scalar bookkeeping
- unsupported nested step types failing loudly instead of silently returning skipped placeholders

**Step 4: Run the new focused tests and verify they fail for the right reasons**

Run:
```bash
pytest tests/test_workflow_nested_identity.py tests/test_provider_output_masking.py tests/test_for_each_execution.py -q
```

Expected:
- failures showing current nested identity collisions and provider masking inconsistencies

**Step 5: Collect-only check for new modules**

Run:
```bash
pytest --collect-only -q tests/test_workflow_nested_identity.py tests/test_provider_output_masking.py
```

Expected:
- both new modules collect cleanly

**Step 6: Commit**

```bash
git add tests/test_workflow_nested_identity.py tests/test_provider_output_masking.py tests/test_for_each_execution.py tests/test_artifact_dataflow_integration.py tests/test_prompt_contract_injection.py
git commit -m "test: add runtime refactor characterization coverage"
```

---

### Task 2: Introduce Qualified Execution Identity for Nested Steps

**Files:**
- Create: `orchestrator/workflow/identity.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `tests/test_workflow_nested_identity.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_state_manager.py`

**Step 1: Add a small execution-identity model**

Create `orchestrator/workflow/identity.py` with a minimal internal model, for example:
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionIdentity:
    display_name: str
    qualified_name: str
    step_index: int
```

Support top-level identities like:
- `ReviewPlan`

And loop-qualified identities like:
- `LoopReview[0].ReviewInLoop`

Do not change public YAML step names in this task.

**Step 2: Route dataflow bookkeeping through qualified identities**

Update `WorkflowExecutor` so:
- publish lineage records use `qualified_name`
- consume freshness maps use `qualified_name`
- loop nested executions no longer pass bare `nested_name` into `_enforce_consumes_contract()` and `_record_published_artifacts()`

Preserve external step display names in compatibility-facing state where existing tests depend on them.

**Step 3: Extend state helpers only where needed**

Modify `StateManager` to persist any additional identity metadata required for debugability, but do not redesign `state.json` wholesale. Keep compatibility with current `steps.<Loop>[i].<Step>` flattened keys if existing tests/specs rely on them.

**Step 4: Make nested freshness tests pass**

Run:
```bash
pytest tests/test_workflow_nested_identity.py tests/test_artifact_dataflow_integration.py tests/test_state_manager.py -q
```

Expected:
- new nested identity tests pass
- legacy dataflow/state tests still pass or are updated only where the compatibility contract intentionally changes

**Step 5: Commit**

```bash
git add orchestrator/workflow/identity.py orchestrator/workflow/executor.py orchestrator/state.py tests/test_workflow_nested_identity.py tests/test_artifact_dataflow_integration.py tests/test_state_manager.py
git commit -m "refactor: qualify nested execution identities"
```

---

### Task 3: Unify Command and Provider Capture/Masking Policy

**Files:**
- Create: `orchestrator/exec/process_runner.py`
- Modify: `orchestrator/exec/step_executor.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_provider_output_masking.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify: `tests/test_execution_safety.py`

**Step 1: Extract shared subprocess execution core**

Create `orchestrator/exec/process_runner.py` to own:
- subprocess invocation
- timeout handling
- streamed vs non-streamed capture
- duration measurement

Keep it agnostic about command vs provider.

**Step 2: Reuse shared output capture and masking rules**

Refactor provider execution so provider output flows through the same masking/capture policy used for command execution. The key outcome is:
- provider text/lines/json outputs are masked before persistence
- provider stdout/stderr spilling behavior follows the same rules as command output

**Step 3: Minimize duplicated capture assembly in `WorkflowExecutor`**

`WorkflowExecutor` should not instantiate a second ad hoc `OutputCapture` for providers. Move that logic behind a shared executor/service and let `WorkflowExecutor` consume normalized results.

**Step 4: Run focused tests**

Run:
```bash
pytest tests/test_provider_output_masking.py tests/test_execution_safety.py tests/test_prompt_contract_injection.py -q
```

Expected:
- provider masking parity tests pass
- existing command/provider safety behavior remains intact

**Step 5: Commit**

```bash
git add orchestrator/exec/process_runner.py orchestrator/exec/step_executor.py orchestrator/providers/executor.py orchestrator/workflow/executor.py tests/test_provider_output_masking.py tests/test_execution_safety.py tests/test_prompt_contract_injection.py
git commit -m "refactor: unify command and provider process execution"
```

---

### Task 4: Collapse Duplicate Top-Level and Loop Execution Paths

**Files:**
- Create: `orchestrator/workflow/step_runner.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_for_each_execution.py`
- Modify: `tests/test_retry_behavior.py`
- Modify: `tests/test_conditional_execution.py`
- Modify: `tests/test_scalar_bookkeeping.py`

**Step 1: Extract a step runner that executes one step given an execution identity and context**

Create `orchestrator/workflow/step_runner.py` with a small API, for example:
```python
class StepRunner:
    def run_step(self, identity, step, context, state) -> dict:
        ...
```

This should handle:
- conditional evaluation
- consumes preflight
- retries
- dispatch by step type
- publish recording
- normalized result persistence hooks

**Step 2: Make both top-level execution and loop execution call the same runner**

Refactor:
- `WorkflowExecutor.execute()`
- `_execute_for_each()`

so they differ mainly in:
- how execution context is built
- how iteration summaries are accumulated

They should not have separate copies of condition handling, consumes enforcement, or step-type dispatch.

**Step 3: Remove silent nested-step skipping**

Unsupported nested step types should fail with a clear contract/pre-execution error, not fabricate `{'exit_code': 0, 'skipped': True}` placeholders.

**Step 4: Run focused regression suite**

Run:
```bash
pytest tests/test_for_each_execution.py tests/test_retry_behavior.py tests/test_conditional_execution.py tests/test_scalar_bookkeeping.py -q
```

Expected:
- nested execution behavior matches top-level semantics closely
- retries/conditions/scalars work in both contexts

**Step 5: Commit**

```bash
git add orchestrator/workflow/step_runner.py orchestrator/workflow/executor.py tests/test_for_each_execution.py tests/test_retry_behavior.py tests/test_conditional_execution.py tests/test_scalar_bookkeeping.py
git commit -m "refactor: unify top-level and loop step execution"
```

---

### Task 5: Extract Dataflow and Control-Flow Bookkeeping from `WorkflowExecutor`

**Files:**
- Create: `orchestrator/workflow/dataflow.py`
- Create: `orchestrator/workflow/control_state.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_control_flow_foundations.py`
- Modify: `tests/test_typed_predicates.py`

**Step 1: Move artifact publish/consume logic into a dedicated service**

Create `orchestrator/workflow/dataflow.py` to own:
- consume preflight
- consume bundle materialization
- publish recording
- artifact lineage/freshness state updates

Keep `WorkflowExecutor` responsible only for calling it.

**Step 2: Move transition/visit guard logic into a dedicated service**

Create `orchestrator/workflow/control_state.py` to own:
- transition counts
- step visit counts
- cycle-guard result building
- related persistence calls

**Step 3: Simplify `WorkflowExecutor` orchestration role**

After extraction, `WorkflowExecutor` should primarily coordinate:
- step ordering
- control-flow target resolution
- current-step lifecycle
- delegation to runner/services

It should no longer own raw artifact-ledger mutation logic inline.

**Step 4: Run focused tests**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py tests/test_control_flow_foundations.py tests/test_typed_predicates.py -q
```

Expected:
- publish/consume behavior unchanged externally
- cycle guards still enforced
- typed predicates still read the expected normalized state

**Step 5: Commit**

```bash
git add orchestrator/workflow/dataflow.py orchestrator/workflow/control_state.py orchestrator/workflow/executor.py tests/test_artifact_dataflow_integration.py tests/test_control_flow_foundations.py tests/test_typed_predicates.py
git commit -m "refactor: extract workflow bookkeeping services"
```

---

### Task 6: Final Verification, Smoke Check, and Review

**Files:**
- Modify: `docs/plans/2026-03-07-orchestrator-runtime-refactor-implementation-plan.md` (mark follow-up notes only if needed)

**Step 1: Run focused runtime regression suite**

Run:
```bash
pytest \
  tests/test_workflow_nested_identity.py \
  tests/test_provider_output_masking.py \
  tests/test_for_each_execution.py \
  tests/test_artifact_dataflow_integration.py \
  tests/test_retry_behavior.py \
  tests/test_conditional_execution.py \
  tests/test_scalar_bookkeeping.py \
  tests/test_control_flow_foundations.py \
  tests/test_typed_predicates.py \
  tests/test_state_manager.py \
  tests/test_prompt_contract_injection.py \
  tests/test_execution_safety.py -q
```

**Step 2: Run an orchestrator smoke check**

Because this touches workflows/runtime mechanics, run at least one smoke command:
```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
```

Expected:
- workflow validation succeeds

**Step 3: Request code review**

Use `superpowers:requesting-code-review` and ask for an architecture/regression-focused review of:
- nested identity behavior
- provider masking parity
- top-level vs loop execution unification
- dataflow/control-flow extraction boundaries

**Step 4: Final integration decision**

If all checks are green and review is clean, use `superpowers:finishing-a-development-branch` to decide merge/cleanup steps.
