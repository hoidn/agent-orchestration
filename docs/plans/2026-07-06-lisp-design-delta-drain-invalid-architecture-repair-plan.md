# Lisp Design Delta Drain Invalid Architecture Repair Plan

## Summary

Repair the `lisp_frontend_design_delta_drain.yaml` invalid design-gap architecture path so a `BLOCKED` drain status is not exposed before the drain run state records the corresponding blocked design gap. Keep the resolver invariant that rejects unrecorded `BLOCKED` terminals.

## Root Cause

- Iteration 3 of run `20260706T130130Z-wy6yz2` selected `DRAFT_DESIGN_GAP`.
- The imported design-gap architect returned `architecture_validation_status: INVALID`.
- `ResolveDesignGapArchitectureDrainStatus` produced `drain_status: BLOCKED`.
- `RouteSelection` surfaced that `BLOCKED` output immediately, so the later `RecordInvalidDesignGapArchitecture` step never executed.
- `WriteNormalIterationStatus` wrote `BLOCKED`, and `ResolveIterationDrainStatus` correctly failed because `state/.../run_state.json` had no recorded blocked item or run-level blocker.

## Repair Shape

1. Add a regression test that asserts the invalid design-gap branch finalizes its case output from a post-recording step rather than directly from `ResolveDesignGapArchitectureDrainStatus`.
2. Rewire the `DRAFT_DESIGN_GAP` case so:
   - the resolver still determines whether the architecture is `VALID` or `INVALID`;
   - invalid architectures record the blocked design gap in durable run state;
   - a final status materialization step runs after that recording and becomes the case output source.
3. Leave `resolve_lisp_frontend_drain_iteration_status.py` unchanged so it continues to reject naked `BLOCKED` statuses.

## Verification

- Run the targeted pytest selector covering the workflow contract regression.
- Run the targeted pytest selector covering drain-iteration status guards.
- Resume `20260706T130130Z-wy6yz2`.
- Re-read `.orchestrate/runs/20260706T130130Z-wy6yz2/state.json` and verify:
  - top-level status is not `failed`;
  - the resumed pid is alive;
  - `updated_at`/heartbeat advanced after resume;
  - no top-level step is `failed`;
  - no `call_frames[*].state.steps` entry is `failed`.

## Notes

- This is a durable workflow-mechanics repair, not a one-run state patch.
- The workspace already contains unrelated user changes; do not revert them.
