# Execution Report: 2026-05-09-dsl-v214-neurips-stack-translation

## Completed In This Pass

Translated the four NeurIPS subworkflows that the plan named into same-version v2.14 YAML, validated them through the public loader, and proved a public CLI dry-run path works for the new selected-item stack.

- Added side-by-side public v2.14 workflows that obey the same-version v2.14 call rule:
  - `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
  - `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
  - `workflows/library/neurips_backlog_roadmap_sync.v214.yaml`
  - `workflows/library/neurips_selected_backlog_item.v214.yaml`
- Replaced only the glue Phase 1 made first-class:
  - `materialize_artifacts` for input pointer materialization across all four phases.
  - `pre_snapshot` on `ExecuteImplementation` plus `select_variant_output` for content-based outcome selection in the implementation phase, with a generic `extract` rule pulling `Blocker Class:` out of the blocked candidate file.
  - `requires_variant` proof on the variant-only publish steps (`PublishCompletedExecutionReport`, `PublishBlockedProgressReport`).
  - `match` proof inside the implementation review loop's outcome routing.
- Replaced the implementation phase's `phase_started_at_ns` mtime gate with the v2.14 snapshot-diff selector.
- Replaced the flat-optional `output_bundle` tagged-union emulation with a real `select_variant_output` bundle.
- Kept the original `2.7` stack untouched; the new files are strictly side-by-side.
- Built deterministic dry-run smoke inputs at `state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/`:
  - `current_roadmap_path.txt`
  - `manifest.json`
  - `selector/selection.json`
  - `run_state.json`
  - empty `run/` state-root directory
- Updated `workflows/README.md` with v2.14 entries plus a "When to use the v2.14 NeurIPS stack" section that names the runtime primitives each `.v214.yaml` workflow now relies on.

### Layout And Authority Notes

The implementation phase's `progress_report_target_path` is intentionally derived inside the v2.14 implementation phase via a small `DeriveProgressReportTarget` command step that runs before `MaterializeImplementationInputs`, then read back by `materialize_artifacts` through a structured `ref` source. This preserves the legacy convention (progress report sits next to the execution report under the per-item work directory) without changing `workflows/library/scripts/materialize_neurips_selected_item_inputs.py`, so the legacy `2.7` selected-item stack and its existing oracle fixtures remain bit-identical.

## Completed Plan Tasks

- [x] Task 1: Confirmed entry state (release supports `version: "2.14"`, `pytest tests/test_v214_runtime_semantics.py -q` passes 12 tests, loader sanity check accepts `version: "2.14"` for a minimal workflow).
- [x] Task 2: Implementation phase translated to native v2.14 semantics with `materialize_artifacts`, `pre_snapshot`, `select_variant_output`, `requires_variant`, and `match` over the implementation-state discriminant.
- [x] Task 3: Seeded plan phase translated. The bash plan-context pointer-write boilerplate (`InitializePlanPhasePaths` + `PublishPlanContextInputs`) collapsed into one `materialize_artifacts` step plus a small `SeedOpenFindings` command shim.
- [x] Task 4 (workflows): Roadmap sync and selected-item routing translated as a same-version v2.14 stack. The new selected-item workflow imports only `.v214.yaml` phases. Smoke inputs created and validated.
- [x] Task 4 (smoke dry-run): `python -m orchestrator run workflows/library/neurips_selected_backlog_item.v214.yaml --dry-run --input ...` reports `[DRY RUN] Workflow validation successful`.
- [x] Task 6 (docs): `workflows/README.md` documents the four `.v214.yaml` workflows, their replaced glue patterns, and the migration-baseline status of the original `2.7` stack.

## Remaining Required Plan Tasks

These items remain in scope for a follow-up tranche. They are bounded, mechanical-to-extend work, not blockers: this pass intentionally stopped after the workflow translation and smoke check to keep the change reviewable and to avoid touching unrelated pre-existing failures in `tests/test_neurips_v214_equivalence_oracle.py`.

- [ ] Task 5 (primitive oracle differential): `tests/test_v214_primitive_oracle.py` still asserts each scenario against a single Phase 0 emulation fixture. The plan calls for it to compare the legacy-emulation observation against a public v2.14 observation for every scenario in the required matrix (materialization success and missing-target failure, snapshot single-/no-/multi-change, variant-output success and invalid-bundle failure, variant-proof acceptance and rejection). New v2.14 fixture workflows under `tests/fixtures/v214_primitives/<scenario>/v214/` plus a parametrized comparison harness still need to land.
- [ ] Task 5 (NeurIPS equivalence differential): `tests/test_neurips_v214_equivalence_oracle.py` still compares the legacy drain stack against expected fixtures rather than the v2.14 stack. The plan calls for old-stack vs. v2.14-stack normalized observation comparison for the seven required scenarios (`completed`, `blocked`, `ambiguous`, `missing_output`, `fresh_plan`, `recovered_plan`, `selected_item_runtime`). This needs (a) a test-local v2.14 wrapper or driver that exercises `neurips_selected_backlog_item.v214.yaml` with the same scenario inputs, (b) `golden_state.run_neurips_workspace_workflow` to copy the four new `.v214.yaml` files into the workspace, and (c) the parametrized scenario-vs-scenario comparison.
- [ ] Pre-existing equivalence oracle failures (independent of this tranche): on the legacy drain alone, four scenarios — `completed`, `blocked`, `fresh_plan`, `selected_item_runtime` — currently fail because the drain attempts `DraftMissingBacklogItem`/`DrainBacklogItems` paths that do not match the committed `expected/*.json` fixtures. `ambiguous`, `missing_output`, and `recovered_plan` pass. These failures predate this tranche (verified: `git stash` of my changes leaves the same 4 failing). Resolving them is part of Task 5 work but is also a separate fix.

## Verification

Blocking sanity checks (Task 1):

```text
loader_accepts_2_14=true
pytest tests/test_v214_runtime_semantics.py -q
12 passed in 0.21s
```

V2.14 workflow loader validation (each new file):

```text
WorkflowLoader.load(workflows/library/neurips_backlog_implementation_phase.v214.yaml)  -> OK
WorkflowLoader.load(workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml)     -> OK
WorkflowLoader.load(workflows/library/neurips_backlog_roadmap_sync.v214.yaml)          -> OK
WorkflowLoader.load(workflows/library/neurips_selected_backlog_item.v214.yaml)         -> OK
```

Public v2.14 selected-item dry-run smoke (Task 4 blocking check):

```text
python -m orchestrator run workflows/library/neurips_selected_backlog_item.v214.yaml --dry-run \
  --input state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/run \
  --input current_roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md \
  --input current_roadmap_pointer_path=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/current_roadmap_path.txt \
  --input selector_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/selector \
  --input manifest_path=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/manifest.json \
  --input steering_path=docs/steering.md \
  --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md \
  --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json \
  --input run_state_path=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/run_state.json
[DRY RUN] Workflow validation successful
```

Legacy drain dry-run still passes (Task 6 blocking check, unchanged by this tranche):

```text
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run \
  --input steering_path=docs/steering.md \
  --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md \
  --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md \
  --input backlog_root=docs/backlog/active \
  --input roadmap_gate_path=docs/backlog/roadmap_gate.json \
  --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json \
  --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain \
  --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json
[DRY RUN] Workflow validation successful
```

Adjacent test suites unaffected by this tranche:

```text
pytest tests/test_v214_primitive_oracle.py tests/test_v214_runtime_semantics.py tests/test_loader_validation.py tests/test_prompt_contract_injection.py -q
167 passed in 1.56s

pytest tests/test_neurips_steered_backlog_runtime.py tests/test_neurips_implementation_state_materializer.py -q
7 passed in 6.85s
```

Equivalence oracle baseline (pre-existing, not introduced by this tranche):

```text
pytest tests/test_neurips_v214_equivalence_oracle.py -q
3 passed (ambiguous, missing_output, recovered_plan), 4 failed (completed, blocked, fresh_plan, selected_item_runtime)
```

The four failures pre-date this tranche; the failure mode (`DraftMissingBacklogItem` exit code 2 routing into `DrainBacklogItems` skips) is independent of any v2.14 workflow change.

## Residual Risks

- The seven minimal NeurIPS scenarios are not yet executed end-to-end against the new v2.14 stack. The new workflows have been validated by the loader, the smoke dry-run, and shape-equivalent translation, but only direct execution against the fake provider can confirm bit-equivalent normalized observations against the legacy stack. This is the Task 5 work tracked above.
- The selected-item v2.14 workflow currently keeps the legacy `MaterializeSelectedItemInputs` step's `output_bundle` shape. Migrating this step to `variant_output` (`ACTIVE_SELECTION` vs `RECOVERED_IN_PROGRESS`) would let `requires_variant` guard the active-only and recovered-only references downstream, but the plan called for keeping the existing `MaterializeSelectedItemInputs` script and bundle until a later tranche.
- The implementation phase's `DeriveProgressReportTarget` shim duplicates a small piece of derivation logic that previously lived inline in the legacy `InitializeImplementationPhasePaths` bash. Replacing it with a future runtime-supported path-derivation primitive (or extending `materialize_neurips_selected_item_inputs.py` to emit `progress_report_target_path` once the legacy fixtures are also regenerated) is a deferred follow-up.
- No documentation or roadmap-gate change is required by this tranche; the gate continues to authorize `phase-2-dsl-v214-neurips-stack` and the progress ledger already records the public release tranche.
