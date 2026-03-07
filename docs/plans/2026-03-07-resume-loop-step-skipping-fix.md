# Resume Loop Step Skipping Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `orchestrate resume` restart from the correct execution point without globally skipping looped steps that legitimately need to run again.

**Architecture:** Treat resume as a one-time restart-position decision, not as a run-wide "skip every previously completed step" mode. Use persisted run state to choose the initial top-level restart point, preserve partial `for_each` recovery where it already exists, and then return to normal control-flow semantics so `goto` loops can revisit the same step names safely.

**Tech Stack:** Python orchestrator runtime, `state.json` persistence, workflow executor control flow, CLI resume command, pytest unit/integration tests, runtime docs.

---

## Principled Fix Direction

- Resume should answer one question: "where do we restart?"
- Resume should not keep applying a name-keyed completed-step skip rule after execution has re-entered normal control flow.
- `state.steps[step_name]` is presentation-oriented and cannot distinguish:
  - "this step already completed before the interruption"
  - from "this loop is intentionally revisiting the same top-level step name"
- The restart decision should come from persisted run position:
  - first preference: persisted `current_step.index` when an in-flight step exists
  - fallback: first top-level step whose persisted status is neither `completed` nor `skipped`
- After the executor reaches that restart point, the global resume-skip behavior must turn off.
- `_execute_for_each(..., resume=True)` should remain the mechanism for partial loop recovery inside the resumed step body; top-level resume should not try to emulate that by skipping same-named top-level steps forever.

## Non-Goals

- Do not redesign workflow-level `resume` semantics beyond this bug.
- Do not introduce new DSL fields.
- Do not change normal `run` behavior.
- Do not solve every stale-observability issue in the same patch unless directly required for the resume fix.

### Task 1: Reproduce the looped-resume bug with focused tests

**Files:**
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Reference: `workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml`

**Step 1: Add a failing resume regression test for revisited top-level steps**

Add a test to `tests/test_resume_command.py` that seeds a run state representing:
- a completed `ReviewImplementation`
- a completed `FixImplementation`
- a completed `IncrementImplementationCycle`
- a failed `ImplementationReviewGate`
- a completed `ImplementationCycleGate`
- `implementation_cycle = 1`

Use a minimal workflow with this shape:

```yaml
steps:
  - name: ExecuteImplementation
    command: ["bash", "-lc", "printf 'impl\\n' > state/execution.txt"]
  - name: ReviewImplementation
    command: ["bash", "-lc", "printf 'REVISE\\n' > state/decision.txt"]
  - name: ImplementationReviewGate
    command: ["bash", "-lc", "test \"$(cat state/decision.txt)\" = APPROVE"]
    on:
      success: { goto: _end }
      failure: { goto: ImplementationCycleGate }
  - name: ImplementationCycleGate
    command: ["bash", "-lc", "test \"$(cat state/cycle.txt)\" -lt 20"]
    on:
      success: { goto: FixImplementation }
      failure: { goto: MaxImplementationCyclesExceeded }
  - name: FixImplementation
    command: ["bash", "-lc", "printf 'APPROVE\\n' > state/decision.txt"]
    on:
      success: { goto: IncrementImplementationCycle }
  - name: IncrementImplementationCycle
    command: ["bash", "-lc", "printf '2\\n' > state/cycle.txt"]
    on:
      success: { goto: ReviewImplementation }
  - name: MaxImplementationCyclesExceeded
    command: ["bash", "-lc", "exit 1"]
```

Assert that a resumed execution reruns `ReviewImplementation` after `FixImplementation`, instead of skipping directly to terminal failure.

**Step 2: Add a failing executor-level test for one-time resume skipping**

In `tests/test_runtime_step_lifecycle.py`, add a lower-level test that:
- seeds state with an already-completed step that will later be revisited through `goto`
- executes with `resume=True`
- asserts the step is only skipped before the restart point, not after control flow loops back to it

**Step 3: Run the new tests to verify they fail for the right reason**

Run: `pytest tests/test_resume_command.py tests/test_runtime_step_lifecycle.py -k "resume and loop" -v`

Expected:
- FAIL
- failure shows resumed execution incorrectly skips a legitimately revisited completed step

**Step 4: Commit the failing-test checkpoint**

```bash
git add tests/test_resume_command.py tests/test_runtime_step_lifecycle.py
git commit -m "test: reproduce resume loop skipping bug"
```

### Task 2: Replace global completed-step skipping with restart-point semantics

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Test: `tests/test_resume_command.py`
- Test: `tests/test_runtime_step_lifecycle.py`

**Step 1: Introduce an explicit restart-point helper**

Add a helper in `orchestrator/workflow/executor.py` that computes the top-level resume restart index from persisted state:
- if `state.current_step.index` exists and `state.current_step.status == "running"`, use that index
- otherwise find the first top-level step whose persisted status is not `completed` or `skipped`
- otherwise return `None`

Keep this helper purely top-level; do not mix it with nested `for_each` replay logic.

**Step 2: Remove the run-wide name-keyed skip rule**

Replace the current block at `execute()` that does:

```python
if resume and step_name in state["steps"]:
    ...
    if status in ["completed", "skipped"]:
        step_index += 1
        continue
```

with logic equivalent to:

```python
resume_restart_index = self._determine_resume_restart_index(state) if resume else None

while step_index < len(self.steps):
    if resume_restart_index is not None and step_index < resume_restart_index:
        step_index += 1
        continue

    # once we reach the restart point, normal control flow resumes
    resume_restart_index = None
```

Do not use step name alone to decide whether a revisited top-level step should be skipped.

**Step 3: Preserve partial `for_each` resume behavior**

Keep `_execute_for_each(..., resume=resume)` working, but pass nested-resume intent based on actual resumed entry into that step, not on perpetual global resume mode after later loop iterations.

The intended contract is:
- top-level restart selection happens once
- inside the restarted step, partial loop recovery may still apply
- later revisits to the same top-level step name run normally

**Step 4: Run the focused tests**

Run: `pytest tests/test_resume_command.py tests/test_runtime_step_lifecycle.py -k "resume and loop" -v`

Expected:
- PASS

**Step 5: Commit the executor fix**

```bash
git add orchestrator/workflow/executor.py orchestrator/state.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py
git commit -m "fix: make resume skip only to restart point"
```

### Task 3: Add broader resume regression coverage for real loop patterns

**Files:**
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_workflow_examples_v0.py`
- Reference: `workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml`

**Step 1: Add a workflow-shaped regression for implementation review/fix loops**

In `tests/test_resume_command.py`, add a test that mirrors the implementation loop pattern:
- `ReviewImplementation -> ImplementationReviewGate -> ImplementationCycleGate -> FixImplementation -> IncrementImplementationCycle -> ReviewImplementation`

Seed state as if one review/fix pass already happened, then resume and assert:
- `FixImplementation` may be rerun when appropriate
- `ReviewImplementation` is rerun after `IncrementImplementationCycle`
- `MaxImplementationCyclesExceeded` is not reached while cycle counter is still below the configured limit

**Step 2: Add a narrow example-level executor test if useful**

If the existing examples test harness can do this without brittle setup, add a focused runtime test around the control-flow shape rather than prompt contents. If not, keep the coverage in the lower-level resume test only.

**Step 3: Run the targeted regression slice**

Run: `pytest tests/test_resume_command.py tests/test_workflow_examples_v0.py -k "resume and implementation" -v`

Expected:
- PASS

**Step 4: Commit the regression coverage**

```bash
git add tests/test_resume_command.py tests/test_workflow_examples_v0.py
git commit -m "test: cover resume through review fix loops"
```

### Task 4: Verify state/observability behavior stays coherent

**Files:**
- Modify: `tests/test_state_manager.py`
- Modify: `docs/runtime_execution_lifecycle.md`
- Possibly modify: `specs/state.md`

**Step 1: Decide whether `current_step` semantics need a doc-only clarification**

Document that:
- `state.steps` is the authoritative per-step result map for the latest attempt by step name
- repeated visits in looped workflows may overwrite the same top-level step entry
- `current_step` identifies the active top-level cursor, not the historical list of all visits

If the current state spec already permits this, update only docs. If the spec is ambiguous, update `specs/state.md` minimally.

**Step 2: Add a test for cleared/terminal current-step state after resumed completion**

Add a test in `tests/test_state_manager.py` or `tests/test_resume_command.py` asserting that after a resumed run terminates, `current_step` is cleared and terminal run status is consistent.

This task is not about redesigning run history, only about preventing the obviously inconsistent "run failed but still running current_step" class of confusion where easy.

**Step 3: Run the targeted state/docs-adjacent checks**

Run: `pytest tests/test_state_manager.py tests/test_resume_command.py -k "current_step or resume" -v`

Expected:
- PASS

**Step 4: Commit the cleanup**

```bash
git add tests/test_state_manager.py tests/test_resume_command.py docs/runtime_execution_lifecycle.md specs/state.md
git commit -m "docs: clarify resume restart and current step behavior"
```

### Task 5: Run the full relevant verification slice and smoke the real workflow shape

**Files:**
- No new files required

**Step 1: Run the main targeted regression suite**

Run:

```bash
pytest tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_state_manager.py tests/test_workflow_examples_v0.py -k "resume or implementation or loop" -v
```

Expected:
- PASS
- no regression in resume behavior for straight-line workflows
- looped resume regressions remain green

**Step 2: Run collection for any modified/added test modules**

Run:

```bash
pytest --collect-only tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_state_manager.py tests/test_workflow_examples_v0.py -q
```

Expected:
- all new tests collected

**Step 3: Run a workflow smoke check**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml --dry-run --stream-output
```

Expected:
- validation succeeds

**Step 4: If the broken run is still available, resume it in tmux**

Run:

```bash
mkdir -p /tmp/claude-tmux-sockets
tmux -S /tmp/claude-tmux-sockets/claude.sock new -d -s resume-loop-fix \
  'cd /home/ollie/Documents/agent-orchestration && PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator resume 20260307T084343Z-mbzxdl --stream-output'
```

Then monitor with:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock capture-pane -p -J -t resume-loop-fix:0.0 -S -200
```

Expected:
- resumed workflow re-enters the implementation loop correctly
- it does not jump from `ImplementationCycleGate` straight to terminal failure while `implementation_cycle < max_impl_iterations`

**Step 5: Commit the verification-backed fix**

```bash
git add orchestrator/workflow/executor.py orchestrator/state.py tests/test_resume_command.py tests/test_runtime_step_lifecycle.py tests/test_state_manager.py tests/test_workflow_examples_v0.py docs/runtime_execution_lifecycle.md specs/state.md
git commit -m "fix: resume looped workflows without skipping revisited steps"
```
