# Watchdog Run 20260630T233034Z-t3vtdv Recovery Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover run `20260630T233034Z-t3vtdv` by making blocked-recovery classification resilient to provider prose wrapped around the intended JSON decision.

**Architecture:** Keep the prompt unchanged for this repair. Instead, make the workflow own the recovery boundary: let `ClassifyBlockedImplementationRecovery` tolerate non-JSON stdout, then have the bundle materializer accept either strict JSON or the known prose pattern and emit the canonical blocked-recovery bundle for downstream routing.

**Tech Stack:** YAML workflow library steps, Python command adapter script, pytest workflow runtime harnesses, `python -m orchestrator resume`.

---

### Task 1: Reproduce The Noisy-Stdout Failure

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Add a provider stub that returns the observed prose-only blocked-recovery message instead of raw JSON.
- [ ] Add a focused failing runtime test for the design-gap work-item path that uses the prose-only classifier output.
- [ ] Run the narrow pytest selector and confirm the workflow fails for the expected blocked-recovery parse reason before the fix.

### Task 2: Repair The Workflow-Owned Recovery Boundary

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- Modify: `workflows/library/scripts/materialize_lisp_frontend_blocked_recovery_bundle.py`

- [ ] Change `ClassifyBlockedImplementationRecovery` so JSON parse errors are non-fatal and the stdout capture still lands in the deterministic workspace file.
- [ ] Extend the materializer so it first accepts strict JSON and otherwise falls back only to the known prose pattern needed for blocked-recovery route/reason extraction.
- [ ] Keep the canonical emitted bundle path unchanged as `${inputs.state_root}/blocked-implementation-recovery.json`.

### Task 3: Verify The Durable Surface

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Re-run the new failing selector until it passes.
- [ ] Re-run the existing stdout-only blocked-recovery regression selector to confirm the strict-JSON path still works.
- [ ] Run `python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run` with the failed run's recorded inputs.

### Task 4: Resume And Re-verify The Target Run

**Files:**
- Create: `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/watchdog-20260630T233034Z-t3vtdv/repair-report.md`
- Create: `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/watchdog-20260630T233034Z-t3vtdv/repair-result.json`

- [ ] Resume `20260630T233034Z-t3vtdv` in tmux with `python -m orchestrator resume 20260630T233034Z-t3vtdv --stream-output`.
- [ ] Re-read `.orchestrate/runs/20260630T233034Z-t3vtdv/state.json` and verify the heartbeat advanced, the resumed pid is alive, no top-level step is failed, and no nested call-frame step remains failed.
- [ ] Write the repair report and final repair-result bundle with the actual verified outcome.
