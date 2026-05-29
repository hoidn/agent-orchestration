# Watchdog Run 20260523T015051Z-bo9619 Recovery Plan

> **Context:** The implementation-phase workflow fix already exists in the worktree and passes targeted verification. The persisted run still fails because its nested `implementation_phase` call frame records the pre-fix workflow checksum, so `resume` rejects the modified callee before it can re-enter the failed implementation path.

**Goal:** Recover run `20260523T015051Z-bo9619` without replaying earlier approved drain phases, while preserving the persisted restart boundary inside the existing nested implementation-phase call frame.

**Architecture:** Treat the persisted run state as authoritative for restart position. Do not relaunch a fresh drain run. Verify the implementation-phase workflow fix, back up the run state, update only the affected nested call-frame `workflow_checksum` to the current checksum for `workflows/library/lisp_frontend_implementation_phase.v214.yaml`, then resume the original run in tmux so the callee can retry from its persisted failed implementation path under the repaired contract.

**Tech Stack:** JSON run state, workflow YAML checksum verification, targeted pytest runtime smokes, `python -m orchestrator resume`, tmux.

## Task 1: Verify The Workflow Fix Before State Repair

- [ ] Run `pytest --collect-only` on `tests/test_lisp_frontend_autonomous_drain_runtime.py` because the test surface changed.
- [ ] Run targeted regression tests covering canonical completed-report publication and the adjacent implementation/reuse flows.
- [ ] Run one explicit drain runtime smoke so the verification includes an end-to-end workflow path.

## Task 2: Repair Only The Affected Nested Checksum

- [ ] Back up `.orchestrate/runs/20260523T015051Z-bo9619/state.json` beside the run before editing it.
- [ ] Compute the current checksum for `workflows/library/lisp_frontend_implementation_phase.v214.yaml`.
- [ ] Update only `call_frames["root.drain_lisp_frontend_work#0.lisp_frontend_drain_iteration.route_selection.design_gap_path.run_design_gap_work_item::visit::1"].state.call_frames["root.run_implementation_phase::visit::1"].state.workflow_checksum` to that current checksum.
- [ ] Leave run status, step results, visit counts, restart position, and outer workflow checksums unchanged.

## Task 3: Resume And Record Evidence

- [ ] Resume the original run in tmux with `python -m orchestrator resume 20260523T015051Z-bo9619`.
- [ ] Capture the final tmux pane output and the resulting persisted run status.
- [ ] Write `artifacts/work/generic-run-watchdog/repair-report.md` and `artifacts/work/generic-run-watchdog/repair-result.json` with the root cause, verification, checksum repair, and recovery outcome.
