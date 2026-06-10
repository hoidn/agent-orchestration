# Repeat-Until Resume Stale Failure Fix Plan

## Problem

Watchdog evidence for run `20260609T213343Z-rsrr6i` shows a resumed `repeat_until`
body step remains persisted as `failed` in the parent run state while the same
nested child call is actively running again inside the resumed loop iteration.
That leaves the persisted state internally contradictory:

- root `current_step` is `DrainLispFrontendWork` with live heartbeats
- nested call-frame state shows `RunImplementationPhase` still running
- parent `steps["DrainLispFrontendWork[9].RouteSelection.DRAFT_DESIGN_GAP.RunDesignGapWorkItem"]`
  remains `failed`

This causes watchdog repair verification to fail even though the resumed work is
alive.

## Root Cause

`repeat_until` resume restores the unfinished iteration and restarts the first
non-terminal nested step, but it does not clear or replace the prior persisted
nested-step result before re-executing that step. The stale terminal result
therefore survives until the retried nested step finishes.

## Scope

Make resumed loop-body re-entry reflect active state truthfully by removing the
stale persisted nested-step result before rerunning it. Keep the fix narrow:

- no workflow YAML changes
- no watchdog prompt changes
- no new loop history model

## Implementation

1. Add a regression test that seeds a failed `repeat_until` nested call step,
   resumes into a deliberately long-running child call, and asserts the parent
   loop-step entry is no longer persisted as `failed` while the child run is
   active.
2. Add a narrow state helper for clearing one persisted loop-step result.
3. In the `repeat_until` resume path, clear the unfinished nested-step result
   from both in-memory iteration state and persisted root `steps` before
   rerunning that step.
4. Re-run the focused resume tests plus a narrow watchdog-oriented integration
   selector.
5. Resume the target run and verify:
   - resumed pid is alive
   - root heartbeat advanced
   - no top-level `steps[*].status == "failed"`
   - no nested `call_frames[*].state.steps[*].status == "failed"`

## Files

- `tests/test_resume_command.py`
- `orchestrator/state.py`
- `orchestrator/workflow/loops.py`

## Verification

- `pytest --collect-only tests/test_resume_command.py -q`
- `pytest tests/test_resume_command.py -k "repeat_until and stale" -v`
- `pytest tests/test_resume_command.py -k "repeat_until_call_resume_preserves_nested_call_frames_and_lowered_match_progress or repeat_until_smoke_resume_restarts_unfinished_iteration_without_replaying_completed_nested_steps" -v`
- `python -m orchestrator resume 20260609T213343Z-rsrr6i`
