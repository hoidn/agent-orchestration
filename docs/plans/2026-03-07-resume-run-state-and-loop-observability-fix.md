# Resume Run State And Loop Observability Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make resumed runs report truthful top-level state while active and make looped revisits to the same top-level step name observable without ambiguity.

**Architecture:** Keep the fix narrowly scoped to runtime state and status reporting. Do not change workflow control-flow semantics again; instead, make `execute()` reassert `status: "running"` when a resumed run becomes live, and thread the already-existing top-level visit counter into `current_step` and completed top-level step results so operators can distinguish “last completed visit” from “current in-flight visit.” Execute this work in a separate worktree, not the live workflow checkout, so it does not interfere with the in-progress implementation loop.

**Tech Stack:** Python orchestrator runtime, `state.json` persistence, CLI resume flow, deterministic status snapshot rendering, pytest unit/integration coverage, one workflow dry-run smoke check.

---

### Task 1: Lock In The Broken Resume-State Semantics With Failing Tests

**Files:**
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_observability_report.py`

**Step 1: Add a failing executor-level test for resumed runs reporting `status: "running"` while a resumed step is active**

Add a test beside `test_long_running_step_updates_current_step_heartbeat` that:

```python
def test_resumed_long_running_step_marks_run_running(tmp_path: Path):
    workflow = {
        "version": "1.1.1",
        "name": "resume-running-status",
        "steps": [
            {"name": "LongCommand", "command": ["bash", "-lc", "python -c 'import time; time.sleep(0.6)'"]},
        ],
    }
    # Seed failed state, then run executor.execute(resume=True) in a thread.
    # While current_step is present, assert state["status"] == "running".
```

The point is to prove the current resumed execution leaves `state.status == "failed"` even while `current_step` is actively running.

**Step 2: Add a failing lifecycle test for looped same-name revisits**

Add a second test in `tests/test_runtime_step_lifecycle.py` using a tiny top-level loop:

```python
def test_looped_resume_exposes_active_visit_count(tmp_path: Path):
    # Seed first review/fix cycle as completed, then resume into the second review visit.
    # While ReviewImplementation is running:
    #   current_step["visit_count"] == 2
    #   steps["ReviewImplementation"]["visit_count"] == 1
```

This should assert the exact ambiguity we saw in the live run: the state needs to show both the active visit and the last completed visit.

**Step 3: Add a failing status-snapshot test for the report surface**

In `tests/test_observability_report.py`, add a state fixture like:

```python
state = {
    "status": "running",
    "step_visits": {"ReviewImplementation": 2},
    "current_step": {
        "name": "ReviewImplementation",
        "status": "running",
        "visit_count": 2,
        "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
    },
    "steps": {
        "ReviewImplementation": {
            "status": "completed",
            "visit_count": 1,
            "exit_code": 0,
        }
    },
}
```

Assert the snapshot exposes:
- run status `running`
- step `visit_count == 2`
- step `last_result_visit_count == 1`
- step `current_visit_count == 2`

**Step 4: Verify the new tests fail for the current code**

Run:

```bash
pytest --collect-only tests/test_runtime_step_lifecycle.py tests/test_resume_command.py tests/test_observability_report.py -q
pytest tests/test_runtime_step_lifecycle.py -k "resumed_long_running_step_marks_run_running or looped_resume_exposes_active_visit_count" -v
pytest tests/test_observability_report.py -k looped_resume -v
```

Expected:
- collect-only succeeds
- the new selectors fail because resumed runs still look failed and visit metadata is missing

**Step 5: Commit the failing tests**

```bash
git add tests/test_runtime_step_lifecycle.py tests/test_observability_report.py
git commit -m "test: pin resumed run-state observability regressions"
```

### Task 2: Make Resumed Runs Truthful While They Are Actively Executing

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Test: `tests/test_runtime_step_lifecycle.py`
- Test: `tests/test_resume_command.py`

**Step 1: Re-read the existing control-flow/heartbeat helpers before editing**

Read these exact regions:

```bash
nl -ba orchestrator/workflow/executor.py | sed -n '155,240p'
nl -ba orchestrator/workflow/executor.py | sed -n '440,520p'
nl -ba orchestrator/state.py | sed -n '329,480p'
```

Focus points:
- `execute()` only writes the final terminal status in `finally`
- `start_step()` owns `current_step`
- `_increment_step_visit()` already exists and returns the correct ordinal

**Step 2: Implement the minimal run-status fix**

Update `execute()` so that once execution is actually starting, the persisted run state is set back to `running` before the loop enters its first active step.

Minimal shape:

```python
state = run_state.to_dict()
self.state_manager.update_status("running")
state["status"] = "running"
```

Do this once near the top of `execute()` after state load, not in ad hoc step handlers.

**Step 3: Thread the visit ordinal into `current_step` and top-level step results**

Add `visit_count` support in the state model:

```python
@dataclass
class StepResult:
    ...
    visit_count: Optional[int] = None

def start_step(..., visit_count: Optional[int] = None):
    ...
    if visit_count is not None:
        self.state.current_step["visit_count"] = visit_count
```

Then in the top-level step execution path:
- call `_increment_step_visit(...)` before `start_step(...)`
- pass that `visit_count` into `start_step(...)`
- include the same `visit_count` in the finalized `StepResult` for the top-level step

Do not add a second visit counter or a new per-visit history store in this change.

**Step 4: Re-run the narrow lifecycle tests**

Run:

```bash
pytest tests/test_runtime_step_lifecycle.py -k "resumed_long_running_step_marks_run_running or looped_resume_exposes_active_visit_count" -v
pytest tests/test_resume_command.py -k "resume_revisits_top_level_review_step_after_fix_loop or resume_clears_current_step_after_looped_completion or stale_current_step" -v
```

Expected: PASS

**Step 5: Commit the runtime/state fix**

```bash
git add orchestrator/workflow/executor.py orchestrator/state.py tests/test_runtime_step_lifecycle.py tests/test_resume_command.py
git commit -m "fix: surface truthful resumed run state"
```

### Task 3: Make Status Snapshots Explicit About Active Vs Last Completed Visits

**Files:**
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Test: `tests/test_observability_report.py`

**Step 1: Extend the snapshot surface without inventing a new history model**

In `build_status_snapshot(...)`, keep the existing `visit_count`, but make it unambiguous:

```python
entry = {
    ...
    "visit_count": step_visits.get(name),
    "current_visit_count": current_step_visit_if_running,
    "last_result_visit_count": result.get("visit_count"),
}
```

Rules:
- `visit_count` remains the total top-level visit counter from `step_visits`
- `current_visit_count` is present only when `current_step.name == name`
- `last_result_visit_count` comes from the last completed/skipped/failed persisted result for that step name

This keeps the change additive and backwards-compatible for report consumers.

**Step 2: Make the observability test pass**

Run:

```bash
pytest tests/test_observability_report.py -k looped_resume -v
```

Expected: PASS

**Step 3: Update the normative docs**

Update:
- `specs/state.md`
  - document `current_step.visit_count`
  - document `steps.<PresentationKey>.visit_count` as “visit ordinal of the recorded result”
- `specs/observability.md`
  - document `visit_count`, `current_visit_count`, and `last_result_visit_count`
- `docs/runtime_execution_lifecycle.md`
  - clarify that name-keyed `steps.<StepName>` stores the latest completed result, while `current_step` may refer to a later in-flight visit of the same top-level step name

**Step 4: Commit the observability/doc change**

```bash
git add orchestrator/observability/report.py tests/test_observability_report.py specs/state.md specs/observability.md docs/runtime_execution_lifecycle.md
git commit -m "docs: clarify resumed loop visit observability"
```

### Task 4: Full Verification And Smoke Check

**Files:**
- No new files; verification only

**Step 1: Run targeted regression modules**

Run:

```bash
pytest --collect-only tests/test_runtime_step_lifecycle.py tests/test_resume_command.py tests/test_observability_report.py -q
pytest tests/test_runtime_step_lifecycle.py tests/test_resume_command.py tests/test_observability_report.py -v
```

Expected: PASS

**Step 2: Re-run the existing resume-loop regression coverage**

Run:

```bash
pytest tests/test_resume_command.py -k "resume_revisits_top_level_review_step_after_fix_loop or stale_current_step or retry_defaults" -v
pytest tests/test_runtime_step_lifecycle.py -k "resume_restart_index or long_running_step_updates_current_step_heartbeat" -v
```

Expected: PASS

**Step 3: Run one orchestrator smoke check from the repo root**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/cycle_guard_demo.yaml --dry-run --stream-output
```

Expected: validation succeeds and the CLI exits `0`

**Step 4: Final diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected:
- no whitespace/errors from `git diff --check`
- only the intended source/test/doc files are modified

**Step 5: Final integration commit**

```bash
git add orchestrator/workflow/executor.py orchestrator/state.py orchestrator/observability/report.py tests/test_runtime_step_lifecycle.py tests/test_resume_command.py tests/test_observability_report.py specs/state.md specs/observability.md docs/runtime_execution_lifecycle.md
git commit -m "fix: clarify resumed run state and loop observability"
```

## Scope Notes

- Do not change workflow YAML, provider prompts, or artifact contracts in this fix.
- Do not introduce per-visit archival history for top-level steps; that is a larger design change than this bug requires.
- Do not touch the live run directory outside test fixtures while implementing this in the worktree.
