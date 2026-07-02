# Watchdog Run 20260630T182211Z-vbqa3m Recovery Plan

**Goal:** Recover run `20260630T182211Z-vbqa3m` without replaying earlier approved drain stages after a verified workflow-mechanics fix changed the current workflow checksum.

**Architecture:** Treat the persisted run state as authority for restart position. First verify the blocked-recovery bundle fix on the current workflow surface. Then back up the run state, update only the checksum fields needed for the edited top-level workflow and the failed nested design-delta work-item call frame, and retry `resume` in tmux. Do not relaunch a fresh run unless checksum-compatible resume still fails for a deeper concrete reason.

**Tech Stack:** JSON run state, workflow YAML checksum verification, targeted pytest selectors, `python -m orchestrator resume`, tmux.

## Task 1: Verify The Durable Workflow Fix

- [ ] Run the narrow structural/runtime pytest selectors that cover blocked recovery bundle materialization.
- [ ] Dry-run `workflows/examples/lisp_frontend_design_delta_drain.yaml` with the failed run's recorded input bindings.
- [ ] Confirm the verified surface matches the failure mode: provider stdout capture plus workflow-owned bundle materialization.

## Task 2: Repair Only The Required Persisted Checksums

- [ ] Back up `.orchestrate/runs/20260630T182211Z-vbqa3m/state.json` beside the run before editing it.
- [ ] Compute the current checksum for `workflows/examples/lisp_frontend_design_delta_drain.yaml`.
- [ ] Compute the current checksum for `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`.
- [ ] Update only the top-level `workflow_checksum` and the failed nested work-item call-frame `state.workflow_checksum`.
- [ ] Leave run status, step outputs, visit counts, and restart position unchanged.

## Task 3: Resume And Re-verify Health

- [ ] Resume the original run in tmux with `python -m orchestrator resume 20260630T182211Z-vbqa3m --stream-output`.
- [ ] Re-read `.orchestrate/runs/20260630T182211Z-vbqa3m/state.json` and verify the resumed pid is alive, the heartbeat advanced, and no top-level or nested step remains failed.
- [ ] If resume reveals a deeper mismatch or semantic failure, stop and report `BLOCKED` with the exact condition instead of force-restarting silently.

## Task 4: Record Repair Evidence

- [ ] Write the repair report under `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/watchdog-20260630T182211Z-vbqa3m/`.
- [ ] Write the final `repair-result.json` with the actual recovery action and outcome.
