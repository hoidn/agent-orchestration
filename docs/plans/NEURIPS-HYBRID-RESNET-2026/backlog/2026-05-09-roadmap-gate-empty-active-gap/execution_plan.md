# Roadmap Gate Empty Active Gap Handling Execution Plan

> For implementation: keep ordinary long-running commands under implementation ownership until terminal success or documented recoverable failure handling is complete.

**Goal:** Correct the NeurIPS backlog roadmap gate so an empty `docs/backlog/active/` directory routes according to current-phase eligibility and configured `gap_policy` instead of being treated as completed roadmap work.

**Architecture:** This fix should stay small and local. First, extend the roadmap-gate regression harness so empty-active backlog scenarios are asserted explicitly for both `draft_backlog_item` and `block` policies while preserving the existing eligible-item and invalid-current-phase behavior. Then update the gate-status decision logic in the reconciliation script without changing the output payload shape or downstream workflow contract that already accepts `ELIGIBLE`, `BACKLOG_GAP`, `DONE`, and `BLOCKED`.

**Tech Stack:** Python CLI helper scripts, `pytest`, JSON fixtures, repo-local workflow contract awareness.

---

## Selected Item Objective

- Fix `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py` so roadmap-gated backlog draining no longer infers `DONE` from an empty active backlog when the gate policy instead requires `BACKLOG_GAP` or `BLOCKED`.

## Scope

- Update the gate-status decision order in `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py`.
- Add or adjust deterministic regression coverage in `tests/test_neurips_backlog_roadmap_gate.py` for empty-active backlog behavior under both supported gap policies.
- Preserve the existing `gap_request` artifact surface and make the new empty-active expectations assert useful diagnostic contents.
- Keep existing behavior unchanged for:
  - valid eligible current-phase items
  - invalid current-phase items that should still block selection
  - downstream workflow consumers that read `gate_status`, `eligible_manifest_path`, and `gap_request_path`

## Explicit Non-Goals

- Do not change the gap drafter prompt or validator unless the new tests prove the current `gap_request` shape is missing a field needed for the documented backlog-item acceptance criteria.
- Do not change selector provider behavior.
- Do not move backlog items between queue directories.
- Do not make `draft_backlog_item` the default for existing gates that currently declare `gap_policy: block`.
- Do not broaden this item into the Phase 1 v2.14 runtime semantics tranche, public `2.14` support, or Phase 2 NeurIPS-stack translation.
- Do not invent a new roadmap-completion signal in this item. If implementation discovers a pre-existing explicit completion signal, it may preserve that route only with direct test coverage; otherwise empty backlog alone must not imply `DONE`.

## Constraints And Prerequisite Status

- `docs/steering.md` and `docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md` keep this work inside the current Phase 1 gate only. Phase 2 translation remains blocked, and this fix must remain a narrow workflow-routing correction rather than a broader roadmap or runtime redesign.
- `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md` remains the binding design authority for the larger v2.14 effort, but the selected backlog item explicitly says this bugfix should not be bundled with that broader runtime-semantics implementation.
- `state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json` still shows no completed items or tranches and retains a stale Phase 0-era note. Treat that as bookkeeping drift, not as a blocker or a reason to expand scope. Planning alone must not mutate the ledger.
- `docs/backlog/roadmap_gate.json` currently sets `current_gate_id` to `dsl-v214-phase1-runtime`, allows `phase-1-dsl-v214-runtime`, disallows `phase-2-dsl-v214-neurips-stack`, and defaults `gap_policy` to `block`. Keep that file as a verification input, not an automatic edit target.
- `workflows/examples/neurips_steered_backlog_drain.yaml` already accepts `ELIGIBLE`, `BACKLOG_GAP`, `DONE`, and `BLOCKED` from the gate step. Preserve that output-bundle contract; this item changes when `DONE` is emitted, not the presence of the status surface itself.
- If a normal test or harness failure occurs, diagnose, narrow-fix, and rerun before considering `BLOCKED`. Reserve `BLOCKED` only for missing resources, external dependencies outside current authority, roadmap conflict, required user decision, or a failure that remains unrecoverable after a documented narrow fix attempt.

## Implementation Architecture

- **Routing decision unit:** the reconciliation script should own the gate-status decision tree and stop treating `total_active_count == 0` as terminal by itself.
- **Diagnostic artifact unit:** the existing `gap_request` bundle remains the contract surface for gap drafting; empty-active cases must still populate it with actionable counts and gate metadata.
- **Regression harness unit:** the roadmap-gate test module must prove the new empty-active routes and protect previously-correct eligible and invalid-current-phase behavior from regression.

## File And Artifact Targets

Mandatory implementation outputs:

- `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py`
- `tests/test_neurips_backlog_roadmap_gate.py`

Preferred packaging and conditional outputs:

- No durable docs or index updates are expected for the normal fix path because this item is a behavior correction, not a contract expansion.
- `docs/backlog/roadmap_gate.json` is a required deterministic validation input and should remain unchanged unless a narrowly-justified missing-field issue is discovered and approved by the acceptance criteria.
- Temporary verification artifacts created by the script or tests, such as generated `roadmap-gate.json`, `eligible_manifest.json`, or `gap_request.json` under temp/state directories, are evidence only and should not become committed source artifacts.

Read-only contract surfaces to preserve:

- `workflows/examples/neurips_steered_backlog_drain.yaml`
- `state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json`
- `docs/backlog/in_progress/2026-05-09-roadmap-gate-empty-active-gap.md`

## Execution Checklist

### Task 1: Extend Deterministic Empty-Active Regression Coverage

- [ ] Add focused tests in `tests/test_neurips_backlog_roadmap_gate.py` for the two missing scenarios:
  - empty active backlog plus `gap_policy: draft_backlog_item` yields `BACKLOG_GAP`
  - empty active backlog plus `gap_policy: block` yields `BLOCKED`
- [ ] Make the empty-active `draft_backlog_item` test assert that the emitted `gap_request` still includes the current gate id, required scope summary, allowed/disallowed roadmap prefixes, source manifest path, and zero-count diagnostics needed for gap drafting.
- [ ] Keep or strengthen regression assertions showing that:
  - an existing eligible current-phase item still yields `ELIGIBLE`
  - an invalid current-phase item still yields `BLOCKED`
- [ ] Use temp-workspace fixtures or helper routines already present in the module so the tests stay deterministic and do not rely on the repo’s live backlog directories.

Verification:

- Supporting: after adding the new tests, run `pytest tests/test_neurips_backlog_roadmap_gate.py --collect-only -q` so the repo-required collection check covers the module before behavior changes.
- Supporting: after adding the new tests, run the narrowest relevant `pytest` selectors for the new empty-active cases and one nearby regression case before changing script logic.
- Supporting: confirm the new tests fail against the current implementation because the script still short-circuits `total_active_count == 0` to `DONE`.

### Task 2: Change Gate Routing To Prefer Eligibility And Gap Policy Over Empty Queue

- [ ] Update `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py` so gate routing is decided in this order:
  - return `ELIGIBLE` when at least one eligible item exists
  - otherwise return `BLOCKED` when current-phase items exist but none are eligible
  - otherwise return `BACKLOG_GAP` when no current-phase item exists and `gap_policy` is `draft_backlog_item`
  - otherwise return `BLOCKED` when no current-phase item exists and `gap_policy` is `block`
- [ ] Remove the unconditional `total_active_count == 0` => `DONE` shortcut. Empty active backlog is only evidence that no active items are present, not proof that roadmap scope is complete.
- [ ] Preserve the current output payload shape, emitted file paths, and `gap_request` generation so downstream workflow wiring stays unchanged.
- [ ] Do not add a new explicit completion mechanism in this item. If implementation finds an already-existing explicit completion signal in the current inputs, preserve it only behind direct regression coverage and without widening the data contract.

Verification:

- Supporting: rerun the new empty-active selectors immediately after the script edit.
- Supporting: inspect the generated gate payloads in the test temp workspace to confirm `gate_status` changes while `eligible_manifest_path` and `gap_request_path` remain present and valid.

### Task 3: Run Full Gate Regressions And Required Deterministic Checks

- [ ] Run the full roadmap-gate unit test module after the targeted fixes so the existing eligible-item and invalid-current-phase cases are verified in the same pass as the new empty-active coverage.
- [ ] Run the selected backlog item’s required deterministic JSON validation exactly as recorded.
- [ ] If a required check fails due to a narrow issue introduced by this fix, diagnose, repair, and rerun the same command rather than downgrading the check.
- [ ] Record the final behavior change explicitly: empty active backlog no longer implies `DONE`; routing now follows eligible/current-phase/gap-policy semantics.

Verification:

- Blocking:

```bash
pytest tests/test_neurips_backlog_roadmap_gate.py -q
python -m json.tool docs/backlog/roadmap_gate.json
```

- Supporting: only if the implementation has to touch downstream workflow YAML or gate-policy structure unexpectedly, add the narrowest relevant orchestrator or workflow smoke check before completion and document why the scope expanded. That smoke check is not required for the normal script-and-tests-only path.

## Completion Criteria

- `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py` no longer treats empty active backlog as terminal roadmap completion by itself.
- `tests/test_neurips_backlog_roadmap_gate.py` deterministically proves:
  - empty active plus `draft_backlog_item` reaches `BACKLOG_GAP`
  - empty active plus `block` reaches `BLOCKED`
  - eligible current-phase behavior remains unchanged
  - invalid current-phase behavior remains unchanged
- The added test module content passes `pytest tests/test_neurips_backlog_roadmap_gate.py --collect-only -q` before final completion claims.
- The `gap_request` emitted for the empty-active drafting case contains actionable gate metadata and count diagnostics rather than a degenerate or missing payload.
- The selected backlog item’s required deterministic checks pass exactly as specified.
- No selector behavior, gap-drafter prompt behavior, queue movement, roadmap scope, or broader v2.14 runtime semantics are changed or implied.
