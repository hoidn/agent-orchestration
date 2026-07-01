# Std Drain Selector-Blocked Carrier Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove and preserve the shared `std/drain::backlog-drain` contract where selector `BLOCKED` carries only `reason`, while terminal `DrainResult.BLOCKED` is projected from loop-owned state and optional terminal effects remain separate consumers.

**Architecture:** Treat this slice as shared-contract hardening first, not family-local repair. The current checkout already passes the relevant selector-blocked proof lanes, so execution starts by re-running that proof ladder and only edits code if those checks expose real drift between the shared stdlib owner lane, its lowering path, and the Design Delta regression evidence.

**Tech Stack:** Workflow Lisp `.orc` stdlib modules, Python lowering/typecheck/runtime tests, pytest

---

## Current Baseline And Causal Risk

The current checkout already reflects the accepted owner split:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` defines `SelectionResult.BLOCKED` as `(reason String)`.
- `DrainLoopState` / `DrainLoopTerminal` keep terminal ownership in loop-owned fields such as `acc__loop-status`, `acc__items-processed`, `acc__progress-report-path`, and `acc__blocker-class`.
- `tests/test_workflow_lisp_drain_stdlib.py`, `tests/test_workflow_lisp_stdlib_form_migration.py`, and `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` already pass the targeted selector-blocked lanes on this checkout.
- The Design Delta blocked-route smoke already asserts runtime-native terminal-effect evidence under `state/workflow_lisp/lisp-frontend-design-delta-drain--drain/`, not `state/run_state.json`.

Because the slice is green today, the causal failure to guard against is contract drift: a future change could reintroduce selector-carried blocked state, stale compatibility evidence, or family-specific repair logic that bypasses the shared owner lane.

## File Map

Primary owner files:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`

Primary proof files:

- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_stdlib_form_migration.py`
- `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/fixtures/workflow_lisp/invalid/backlog_drain_selector_blocked_reason_missing_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/backlog_drain_selector_blocked_extra_state_field_invalid.orc`

Reference-family files to touch only if proof drift is found:

- `workflows/library/lisp_frontend_design_delta/types.orc`
- `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc`
- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`

### Task 1: Reconfirm The Shared Carrier-Free Contract

**Files:**
- Inspect: `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- Inspect: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Test: `tests/test_workflow_lisp_drain_stdlib.py`
- Test: `tests/test_workflow_lisp_stdlib_form_migration.py`

- [ ] **Step 1: Re-run the narrow shared proof ladder from repo root**

Run:
```bash
pytest tests/test_workflow_lisp_drain_stdlib.py -k "selector_blocked or target_contract_exposes_selector_blocked_variant or pins_selector_blocked_compatibility_blocker_class" -q
pytest tests/test_workflow_lisp_stdlib_form_migration.py -k "drain_stdlib" -q
```

Expected: PASS. If either command fails, capture the first failing assertion before changing code.

- [ ] **Step 2: Re-read the owner surfaces before editing**

Confirm:
- `SelectionResult.BLOCKED` is still `(reason String)` only.
- blocked terminal projection still comes from loop-owned state plus the pinned compatibility blocker class.
- `consume-drain-terminal-effects` remains optional terminal-effect consumption, not return-value transport.

- [ ] **Step 3: Add or tighten characterization only if the shared proof no longer fully covers the contract**

If a gap is exposed, write the narrowest failing assertion in `tests/test_workflow_lisp_drain_stdlib.py` first. Prefer checks that prove:
- selector `BLOCKED` rejects extra fields;
- missing `reason` still fails with `workflow_call_signature_erased`; and
- lowering still pins selector-blocked `acc__blocker-class` to `user_decision_required`.

- [ ] **Step 4: Re-run the exact narrowed tests**

Run the same two pytest commands again.

Expected: PASS.

### Task 2: Reconfirm The Design Delta Regression Evidence Uses Runtime-Native Terminal State

**Files:**
- Test: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Inspect if needed: `workflows/library/lisp_frontend_design_delta/types.orc`
- Inspect if needed: `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc`
- Inspect if needed: `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`

- [ ] **Step 1: Re-run the narrow reference-family smoke lane**

Run:
```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "removes_run_state_from_authored_loop_state or removes_run_state_from_work_item_authored_signatures_while_preserving_private_bridge or smokes_selector_blocked_path" -q
```

Expected: PASS. The blocked-route smoke should prove:
- `return__variant == "BLOCKED"`
- `return__reason == "selector_blocked"`
- `return__drain-summary__drain_status == "BLOCKED"`
- `artifacts/work/drain_summary.json` exists
- `artifacts/work/item_summary.json` does not exist
- `state/workflow_lisp/lisp-frontend-design-delta-drain--drain/drain-run-state-state.json` records `drain_status == "BLOCKED"`
- `write-drain-status-audit.jsonl` ends with a committed `BLOCKED` projection

- [ ] **Step 2: If the smoke fails, identify whether the defect is stale evidence or shared-lowering drift**

Use the failure to classify the defect:
- test only reads the wrong authority surface: fix the test or reference-family projection narrowly;
- selector payload now carries state again: treat as shared contract drift;
- blocked route only works via family-specific compatibility plumbing: treat as shared-lowering drift, not a Design Delta exception.

- [ ] **Step 3: Only if stale family evidence exists, update it without widening the shared contract**

Allowed family-side changes:
- keep `DesignDeltaSelectionResult.BLOCKED` reason-only;
- keep blocked-route assertions on typed outputs and runtime-native terminal-effect artifacts;
- remove any assertion that treats `state/run_state.json`, pointer files, rendered summaries, provider prose, or stdout as blocked-route semantic authority.

- [ ] **Step 4: Re-run the same Design Delta selector once the narrow fix is in**

Expected: PASS.

### Task 3: Repair The Shared Owner Lane Only If Proof Drift Exposes A Real Defect

**Files:**
- Modify if needed: `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- Modify if needed: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Modify if needed: `orchestrator/workflow_lisp/drain_stdlib.py`
- Test if needed: `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`

- [ ] **Step 1: Trace the blocked path through the shared lowerer**

Follow the selector `BLOCKED` route in `phase_drain.py` and confirm it still:
- marks loop status as `BLOCKED`;
- preserves loop-owned accumulator responsibility;
- projects terminal `DrainResult.BLOCKED` without selector-carried state; and
- keeps source-map attribution on the imported `std/drain::backlog-drain` owner lane.

- [ ] **Step 2: Implement the smallest generic fix**

Permitted fixes:
- restore reason-only selector `BLOCKED` compatibility checks;
- restore loop-owned terminal projection;
- restore the pinned selector-blocked blocker-class mapping;
- restore runtime-native terminal-effect evidence as a separate consumer.

Forbidden fixes:
- adding `run-state`, `run_state_path`, checkpoint paths, summary paths, pointer files, or generated roots to selector `BLOCKED`;
- widening selector, `run-item`, or `gap-drafter` signatures;
- adding Design Delta-specific branches, wrappers, or compatibility-only shims.

- [ ] **Step 3: Add a narrow proof-boundary regression only if shared code changed**

If Task 3 touched lowering or stdlib owner code, add the smallest assertion in `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py` that proves blocked terminal projection still belongs to imported `std/drain::backlog-drain`.

- [ ] **Step 4: Re-run the shared and reference-family proof ladder**

Run:
```bash
pytest tests/test_workflow_lisp_drain_stdlib.py -k "selector_blocked or target_contract_exposes_selector_blocked_variant or pins_selector_blocked_compatibility_blocker_class" -q
pytest tests/test_workflow_lisp_stdlib_form_migration.py -k "drain_stdlib" -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "removes_run_state_from_authored_loop_state or removes_run_state_from_work_item_authored_signatures_while_preserving_private_bridge or smokes_selector_blocked_path" -q
pytest tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py -k "runtime_proof_profile_records_non_promotable_boundary_evidence_and_source_map_lineage" -q
```

Expected: PASS.

### Task 4: Close The Slice With Evidence, Not Assumptions

**Files:**
- Modify if tests were renamed: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify if tests were renamed: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] **Step 1: Run collect-only if any test names or modules changed**

Run only if applicable:
```bash
pytest --collect-only tests/test_workflow_lisp_drain_stdlib.py
pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py
```

Expected: the renamed tests collect cleanly.

- [ ] **Step 2: Summarize the final evidence in the execution handoff or commit message**

Record:
- whether the slice required no code changes or a shared generic fix;
- which tests were run and passed;
- whether any family-side assertion was corrected; and
- that selector `BLOCKED` remained reason-only throughout.

## Acceptance Criteria

- `SelectionResult.BLOCKED` remains `(reason String)` only on the shared stdlib lane.
- Imported `std/drain::backlog-drain` returns terminal `DrainResult.BLOCKED` from loop-owned state, not selector-carried state.
- Runtime-native terminal-effect artifacts remain separate consumers and evidence, not return-value transport.
- Design Delta blocked-route smoke proves the carrier-free contract via typed outputs plus runtime-native terminal-effect state.
- No Design Delta-specific compiler/lowering exception is introduced.
