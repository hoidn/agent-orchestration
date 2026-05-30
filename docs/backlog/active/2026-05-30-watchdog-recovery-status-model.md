# Backlog Item: Separate Watchdog Recovery Action From Recovery Certification

- Status: active
- Created on: 2026-05-30
- Plan: none yet

## Problem

The generic run watchdog currently overloads recovery status, recovery action,
and target-run liveness in ways that make operator reports ambiguous.

In the `20260530T001340Z-7nbh7e` repair attempt, the watchdog result reported
`BLOCKED` with `recovery_action: "DECLINED"` while the target run had already
been resumed and was still alive and heartbeating. That was technically meant
to say "the watchdog did not certify successful recovery," but it read like
"the watchdog declined to resume" or "the target is not running."

This ambiguity makes it harder to decide whether to wait, resume again, repair
state, or treat a run as unrecoverable.

## Root Cause

The result schema and prompt conflate three separate facts:

- what action was attempted (`RESUME`, `RELAUNCH`, `RESTART`, or no action);
- whether the target run is currently alive, stale, completed, or failed;
- whether the watchdog can certify the recovery as successful.

The prompt-level fix now says to keep the actual action taken when reporting
`BLOCKED`, but the durable contract still lacks first-class fields for target
liveness and recovery certification.

## Desired Behavior

Watchdog outputs should make these distinctions explicit:

- target run state: persisted status, current step, heartbeat freshness, pid
  liveness, and failed-marker summary;
- recovery attempt: action attempted, command used, resulting pid/run id, and
  whether a new run was launched;
- certification: whether the watchdog certifies recovery, does not yet certify
  it, or rejects recovery as unsafe;
- reason: a machine-readable reason for non-certification, such as
  `persisted_failed_steps_remain`, `pid_not_alive`, `heartbeat_not_advanced`,
  `top_level_step_failed`, `nested_step_failed`, or `durable_fix_missing`.

Operator-facing reports should say "target run is alive but recovery is not
certified" instead of combining `BLOCKED` and `DECLINED` in a way that obscures
the actual process state.

## Candidate Contract Shape

Consider extending or versioning the repair result bundle with fields like:

```json
{
  "repair_status": "FIXED_AND_RESUMED | FIXED_AND_RELAUNCHED | PLAN_WRITTEN | BLOCKED",
  "recovery_action": "RESUME | RELAUNCH | RESTART | NONE",
  "recovery_certification": "CERTIFIED | NOT_CERTIFIED | REJECTED_UNSAFE",
  "target_run_status": "RUNNING | COMPLETED | FAILED | STALE | UNKNOWN",
  "target_run_liveness": "ALIVE | DEAD | UNKNOWN",
  "non_certification_reason": "persisted_failed_steps_remain"
}
```

The exact names may change during design, but the final contract should prevent
`DECLINED` from representing both "no recovery action was attempted" and
"recovery action was attempted but success could not be certified."

## Acceptance Criteria

This item is complete when:

- the watchdog repair result contract separates recovery action, target-run
  liveness, and recovery certification;
- the generic watchdog prompt and any result-writing workflow logic use the new
  distinction consistently;
- reports for an alive resumed run with remaining failed markers clearly say
  that the target is alive but recovery is not certified;
- `DECLINED` is either removed from the action field or reserved only for cases
  where no recovery action was attempted because concrete evidence showed it
  was unsafe;
- tests or smoke checks cover the confusing case: a resumed pid is alive and
  heartbeat advances, but persisted failed step markers remain;
- existing consumers of `repair-result.json` and `watchdog-result.json` are
  updated or given a compatibility path.

## Non-Goals

This item should not:

- weaken the post-resume checks for pid liveness, heartbeat advancement, or
  failed step markers;
- report `FIXED_AND_RESUMED` when recovery cannot be certified;
- hide target-run failed markers just because the resumed process is active;
- solve unrelated Workflow Lisp lowering or prompt-asset generation defects,
  except insofar as watchdog status must describe those defects accurately.

## Related Context

- `workflows/examples/generic_run_watchdog.yaml`
- `workflows/library/prompts/generic_run_watchdog/repair_run_failure.md`
- `state/KISS-EFFECTFUL-COMPOSITION/watchdog-20260530T001340Z-7nbh7e/watchdog-result.json`
- `artifacts/work/KISS-EFFECTFUL-COMPOSITION/watchdog-20260530T001340Z-7nbh7e/repair-result.json`
- `artifacts/work/KISS-EFFECTFUL-COMPOSITION/watchdog-20260530T001340Z-7nbh7e/repair-report.md`
