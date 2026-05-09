# Execution Report: 2026-05-09-dsl-v214-neurips-stack-translation

## Completed In This Pass

- Fixed the remaining v2.14 runtime correctness defects that were blocking the differential evidence:
  - `materialize_artifacts` now substitutes templated pointer paths before writing them.
  - published artifact-registry relpath pointers now substitute templated pointer paths before commit.
  - `select_variant_output` now substitutes its bundle path template before validation and commit.
- Reworked `workflows/library/neurips_selected_backlog_item.v214.yaml` so the selected-item surface is v2.14-native instead of a legacy `output_bundle` wrapper:
  - kept the existing selected-item materializer script for domain-shaped context generation;
  - replaced the workflow-facing bundle contract with `expected_outputs` on `ResolveSelectedItemInputs`;
  - added `MaterializeSelectedItemInputs` with `materialize_artifacts` for the pointerized relpath surfaces the plan called out;
  - added `MaterializeSelectionModeAuthority` with `variant_output`, and guarded `MoveSelectedItemToInProgress` with `requires_variant` for the active-selection path.
- Completed the primitive differential oracle work in `tests/test_v214_primitive_oracle.py`:
  - legacy fixture workflows are now compared against public v2.14 workflows for materialization success, missing-target failure, snapshot single/no/multi change, invalid-bundle failure, variant-proof accept/reject, and implementation-outcome completed/blocked/both/neither.
- Completed the NeurIPS differential harness work:
  - `tests/golden_state.py` now runs both the legacy stack and the v2.14 selected-item stack in test workspaces;
  - `tests/test_neurips_v214_equivalence_oracle.py` now compares normalized legacy-vs-v2.14 observations for all seven approved scenarios.
- Preserved the approved layout and unit boundaries. No location or ownership deviation from the design/plan was required.

## Completed Current-Scope Work

- Task 2 is complete. The implementation-phase translation now behaves correctly under the approved v2.14 runtime contract, including snapshot-based outcome selection and pointer publication.
- Task 4 is complete. The selected-item v2.14 workflow no longer begins with the legacy `output_bundle` surface, and the active-vs-recovered selection split now has explicit variant proof where it matters.
- Task 5 is complete. Both required differential suites now compare legacy behavior against public v2.14 behavior instead of asserting only one side in isolation.
- The blocking verification contract from the approved plan now passes in the current checkout.

## Verification

- `pytest tests/test_v214_primitive_oracle.py -q`
  - `16 passed in 1.44s`
- `pytest tests/test_neurips_v214_equivalence_oracle.py -q -k selected_item_runtime`
  - `1 passed, 6 deselected in 2.72s`
- `python -m orchestrator run workflows/library/neurips_selected_backlog_item.v214.yaml --dry-run --input state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/run --input current_roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input current_roadmap_pointer_path=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/current_roadmap_path.txt --input selector_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/selector --input manifest_path=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/manifest.json --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input run_state_path=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/run_state.json`
  - `[DRY RUN] Workflow validation successful`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
  - `23 passed in 17.69s`

## Follow-Up Work

- Optional maintainability follow-up from review: remove or centralize the `DeriveProgressReportTarget` shim in `workflows/library/neurips_backlog_implementation_phase.v214.yaml` once a shared runtime-owned path-derivation surface exists.
- If workflow automation requires a fresh published checks artifact JSON, rerun the higher-level backlog workflow that emits `artifacts/checks/.../2026-05-09-dsl-v214-neurips-stack-translation-checks.json` instead of editing that generated artifact by hand.

## Residual Risks

- The selected-item v2.14 workflow still depends on `workflows/library/scripts/materialize_neurips_selected_item_inputs.py` for the domain-shaped context and check-command materialization. If that script’s payload schema changes later, the workflow’s `expected_outputs` and `materialize_artifacts` field list must stay in sync.
- The approved differential matrix is covered, but these tests still run against the deterministic fake-provider harness rather than external providers. Real-provider behavior remains outside this backlog item’s verification contract.
