## Completed In This Pass

- Implemented executable runtime handling for `materialize_artifacts` and `select_variant_output` in the workflow executor instead of lowering them into skipped nodes.
- Added durable `pre_snapshot` capture for command and provider steps, including step-state projection under `steps.<Step>.snapshots.<name>` and sidecar inflation/hash checking for larger snapshot records.
- Added snapshot structured-ref support (`root.steps.<Step>.snapshots.<name>`) so `select_variant_output.evidence.snapshot.ref` resolves through the normal runtime reference surface.
- Added a pre-execution `requires_variant` runtime guard that fails the consumer step with `variant_unavailable` when the producer selected a different variant.
- Fixed adjudicated-provider prompt assembly so `variant_output` survives path resolution and reaches prompt-contract injection as `variant_output` rather than being downgraded to `output_bundle`.
- Extended loader/dataflow validation so `materialize_artifacts` outputs can satisfy `publishes.from`, and adjudicated-provider validation now accepts `variant_output` as the single declared output contract.
- Added focused regression coverage in `tests/test_v214_runtime_semantics.py` for materialization, snapshot capture/selection, ambiguous no-commit behavior, `requires_variant`, and the adjudicated-provider prompt regression.

## Completed Current-Scope Work

- Review finding 1 is fixed: authored `materialize_artifacts` and `select_variant_output` steps now execute and persist normal step results instead of disappearing behind the unknown-step fallback.
- Review finding 2 is fixed for the approved runtime slice: snapshot evidence is captured before execution, persisted on the producing step, resolved by structured ref, and consumed by `select_variant_output` to atomically commit a validated selected bundle or fail without committing.
- Review finding 3 is fixed: explicit `requires_variant` now enforces variant availability before step execution, matching the Phase 1 runtime-guard requirement for variant-only artifacts.
- Review finding 4 is fixed: adjudicated-provider prompt injection preserves `variant_output`, so provider-side variant contract instructions remain available after path resolution.

## Follow-Up Work

- Add dedicated loader/runtime tests for author-time `match` proof propagation and unproved variant-ref rejection; this pass implemented the explicit runtime guard path and snapshot/runtime execution paths that were blocking review.
- Expand observability/report projections so snapshot summaries and selected-variant details are surfaced outside step-local state/debug payloads.

## Residual Risks

- `select_variant_output` currently covers the minimal extractor surface required by this tranche; broader extractor shapes need separate tests before depending on them in wider workflows.
- Snapshot sidecar integrity handling is implemented, but resume-path corruption/missing-sidecar scenarios were not part of this pass's executed test set.

## Verification

- `pytest --collect-only tests/test_v214_runtime_semantics.py -q`
- `pytest tests/test_v214_runtime_semantics.py -q`
- `pytest tests/test_prompt_contract_injection.py -q`
- `pytest tests/test_adjudicated_provider_loader.py -q`
- `pytest tests/test_artifact_dataflow_integration.py -q`
- `pytest tests/test_v214_runtime_semantics.py tests/test_prompt_contract_injection.py tests/test_adjudicated_provider_loader.py tests/test_artifact_dataflow_integration.py tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
- `pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- `python -m json.tool docs/backlog/roadmap_gate.json`
- `python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json`
