# Blocked Recovery Bundle Materialization Repair Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the design-delta blocked-recovery classifier recoverable when the provider returns valid JSON on stdout but does not write the declared bundle file itself.

**Architecture:** Move the blocked-recovery bundle write from the provider boundary into workflow-owned mechanics for `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`. The provider step will capture strict JSON stdout to a deterministic file, and a follow-up command adapter will materialize the runtime-owned bundle path before downstream routing reads it.

**Tech Stack:** YAML workflow library steps, Python command adapter script, pytest workflow runtime harnesses.

---

### Task 1: Reproduce The Missing-Bundle Failure In The Runtime Harness

**Files:**
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Test: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] Add a helper mode that makes the fake blocked-recovery provider return JSON on stdout without writing `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
- [ ] Add a focused regression test covering the blocked design-gap work-item path under that stdout-only provider behavior.
- [ ] Run the new pytest selector and confirm it fails for the expected missing-bundle or blocked-recovery contract reason.

### Task 2: Make Bundle Materialization Workflow-Owned

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- Create: `workflows/library/scripts/materialize_lisp_frontend_blocked_recovery_bundle.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Change `ClassifyBlockedImplementationRecovery` to capture strict JSON stdout and tee it to a deterministic workspace file instead of declaring `output_bundle` directly on the provider step.
- [ ] Add a command adapter step that reads the captured stdout JSON and writes the declared blocked-recovery bundle through `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
- [ ] Update downstream references so `SelectBlockedRecoveryRoute` and recorder steps keep consuming the same canonical bundle path.
- [ ] Add or update a structural workflow test that asserts the provider step now uses capture-plus-materialize mechanics and that the new command adapter is present.

### Task 3: Verify The Durable Surface And Recover The Run

**Files:**
- Modify: `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/watchdog-20260630T182211Z-vbqa3m/repair-report.md`
- Modify: `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/watchdog-20260630T182211Z-vbqa3m/repair-result.json`

- [ ] Re-run the focused regression test and the narrow workflow-structure selector until both pass.
- [ ] Run `python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run` to validate the repaired workflow surface before resume.
- [ ] Resume `20260630T182211Z-vbqa3m` in tmux with `--stream-output`.
- [ ] Re-read `.orchestrate/runs/20260630T182211Z-vbqa3m/state.json` and confirm the resumed pid is alive, the heartbeat advanced, and no top-level or nested step remains failed.
- [ ] Write the repair report and final `repair-result.json` bundle with the actual recovery outcome.
