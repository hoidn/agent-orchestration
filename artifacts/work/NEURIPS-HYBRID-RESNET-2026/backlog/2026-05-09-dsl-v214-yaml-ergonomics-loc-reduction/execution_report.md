# Execution Report

## Completed In This Pass

- Added loader, contract, and runtime support for `variant_output.shared_fields` and `materialize_artifacts.input_values`.
- Rewrote the v2.14 selected-item workflow to validate native `selected-item-inputs.json` directly and removed the `selected-item-inputs-fields/` fanout plus the separate `selection-mode-authority.json` step.
- Applied `input_values` to the v2.14 NeurIPS child workflows where the materialized contract is inherited directly from workflow inputs.
- Added deterministic LOC comparison tooling and tests, then updated the normative DSL and workflow-author documentation for the compact v2.14 authoring pattern.

## Completed Plan Tasks

- Tranche 1: implemented loader validation and output-contract coverage for `shared_fields` and `input_values`.
- Tranche 2: rendered shared fields in injected variant contracts and exposed them at runtime without variant proof while keeping variant-only proof requirements unchanged.
- Tranche 3: rewrote `workflows/library/neurips_selected_backlog_item.v214.yaml` to keep `selected-item-inputs.json` native, consume validated artifacts directly, and remove the separate selection-mode authority surface because no remaining consumer needed a distinct proof-only bundle.
- Tranche 3: applied `materialize_artifacts.input_values` to `neurips_backlog_seeded_plan_phase.v214.yaml`, `neurips_backlog_roadmap_sync.v214.yaml`, and `neurips_backlog_implementation_phase.v214.yaml` where contracts were uniform inherited input relpaths.
- Tranche 4: added `workflows/library/scripts/compare_workflow_loc.py`, added regression tests, and updated `specs/dsl.md`, `specs/acceptance/index.md`, and `workflows/README.md`.

## Remaining Required Plan Tasks

- None.

## Verification

- `pytest tests/test_loader_validation.py -k 'variant_output or materialize' -q`
  - `9 passed, 111 deselected`
- `pytest tests/test_output_contract.py -k 'variant' -q`
  - `3 passed, 22 deselected`
- `pytest tests/test_prompt_contract_injection.py -k 'variant_output' -q`
  - `2 passed, 21 deselected`
- `pytest tests/test_v214_runtime_semantics.py -q`
  - `17 passed`
- `pytest tests/test_workflow_loc_comparison.py -q`
  - `3 passed`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
  - `23 passed`
- `pytest tests/test_loader_validation.py tests/test_output_contract.py --collect-only -q`
  - `145 tests collected`
- `pytest tests/test_prompt_contract_injection.py tests/test_v214_runtime_semantics.py tests/test_workflow_loc_comparison.py --collect-only -q`
  - `43 tests collected`
- `python workflows/library/scripts/compare_workflow_loc.py --old workflows/library/neurips_backlog_implementation_phase.yaml --old workflows/library/neurips_backlog_seeded_plan_phase.yaml --old workflows/library/neurips_backlog_roadmap_sync_phase.yaml --old workflows/library/neurips_selected_backlog_item.yaml --new workflows/library/neurips_backlog_implementation_phase.v214.yaml --new workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml --new workflows/library/neurips_backlog_roadmap_sync.v214.yaml --new workflows/library/neurips_selected_backlog_item.v214.yaml --require-total-reduction-pct 1`
  - `old_loc=2224`
  - `new_loc=2160`
  - `absolute_delta=64`
  - `percent_delta=2.88`
  - threshold met against required total reduction `1.0%`
- `python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json`
  - `[DRY RUN] Workflow validation successful`
- Additional evidence:
  - No literal `${inputs.*}` directories or files were created during this pass.
  - `selected-item-inputs.json` is now validated directly and is no longer split into per-field text files.

## Residual Risks

- The `shared_fields` and `input_values` surfaces are intentionally narrow. Future workflow authors may still overuse `variant_output` where `output_bundle` would be simpler, so the new README guidance matters for keeping v2.14 YAML compact.
- The LOC reduction target is met at the four-file stack level, but `neurips_selected_backlog_item.v214.yaml` itself is slightly longer than the legacy file because the direct tagged-union contract is now expressed explicitly in YAML.
