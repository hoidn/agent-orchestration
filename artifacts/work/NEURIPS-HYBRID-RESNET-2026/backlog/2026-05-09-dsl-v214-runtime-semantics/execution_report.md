## Completed In This Pass

- Added Phase 1 internal typed-surface plumbing for `variant_output`, `pre_snapshot`, `requires_variant`, `materialize_artifacts`, and `select_variant_output` across surface AST, executable IR, lowering, runtime-step compatibility views, and test bundle helpers.
- Added public loader gating for the new v2.14-only fields while keeping normal `version: "2.14"` workflows rejected.
- Implemented `variant_output` bundle validation plus provider prompt-contract rendering/injection and runtime post-step validation for provider/command/adjudicated-provider contract paths that already flow through executor output validation.
- Preserved the legacy `expected_outputs`/`output_bundle` mutual-exclusion error text while extending validation to cover the new output-contract fields.

## Completed Plan Tasks

- Task 1: extended loader/runtime typed surfaces enough to recognize the new Phase 1 fields and fail cleanly on public pre-2.14 usage instead of crashing during elaboration.
- Task 1: preserved public exposure gating for normal loader paths; `test_version_2_14_is_rejected` still passes.
- Task 2: implemented contract-layer `variant_output` bundle validation and provider prompt-contract formatting/injection.
- Task 2: wired executor path-template resolution and post-success contract validation for `variant_output`.

## Remaining Required Plan Tasks

- Finish Task 1 validation depth for exact Phase 1 authored shapes and error taxonomy beyond the current public version gates and mutual-exclusion handling.
- Implement contract inheritance/refinement and pointer-authority enforcement for `materialize_artifacts`.
- Implement `pre_snapshot`, snapshot refs/catalog/state persistence, and snapshot-sidecar resume integrity.
- Implement `select_variant_output` lowering and runtime execution, including atomic commit and snapshot diff selection.
- Implement variant proof/static availability checking (`match` proof and explicit `requires_variant`) plus runtime `variant_unavailable` guards.
- Extend dataflow/pointer publishing semantics and path-safety enforcement for the new Phase 1 surfaces.
- Add the remaining targeted tests named in the design/plan for v2.14 materialization, snapshots, selection, and variant-reference safety.

## Verification

- `pytest tests/test_loader_validation.py -k 'materialize_artifacts_requires_version_2_14 or variant_output_requires_version_2_14' -q`
- `pytest tests/test_output_contract.py -k 'variant_output_bundle' -q`
- `pytest tests/test_prompt_contract_injection.py -k 'provider_variant_output_appends_variant_contract_block_to_prompt' -q`
- `pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_prompt_contract_injection.py tests/test_workflow_output_contract_integration.py -q`
- `pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
- `python -m json.tool docs/backlog/roadmap_gate.json >/dev/null`
- `python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json`

## Residual Risks

- The runtime semantics tranche is only partially implemented in this pass; `materialize_artifacts`, `pre_snapshot`, `select_variant_output`, and variant-proof enforcement remain unimplemented.
- The current `variant_output` implementation is functional on the existing provider/executor path, but the broader Phase 1 error taxonomy and adjudicated-provider-specific coverage are not complete yet.
- No docs-index update was needed in this pass because no new durable internal documentation artifact was added.
