# Execution Report

## Completed In This Pass

- Added Phase 0 draft references for current v2.14 materialization and
  variant-output behavior plus a minimal NeurIPS behavior matrix.
- Added a deterministic fake provider, normalized golden-state helper, primitive
  oracle fixtures, and minimal NeurIPS fixture workspace.
- Added primitive and NeurIPS oracle regression suites plus an explicit loader
  test that normal paths still reject public `version: "2.14"`.

## Completed Plan Tasks

- Task 1: Drafted the Phase 0 reference docs and indexed them in `docs/index.md`.
- Task 2: Built the primitive oracle harness, fake provider, normalized
  observation layer, and dedicated regression tests.
- Task 3: Built the minimal NeurIPS oracle harness and regression tests covering
  completed, blocked, ambiguous, missing-output, fresh-plan, recovered-plan,
  and selected-item runtime scenarios.
- Task 4: Added the public version-gate proof in
  `tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected`.
- Task 5: Ran the targeted pytest selectors, the roadmap-gate deterministic
  checks, and the top-level backlog-drain dry-run smoke.

## Remaining Required Plan Tasks

- None.

## Verification

- `pytest --collect-only tests/test_v214_primitive_oracle.py -q`
- `pytest --collect-only tests/test_neurips_v214_equivalence_oracle.py -q`
- `pytest tests/test_v214_primitive_oracle.py -q`
- `pytest tests/test_neurips_v214_equivalence_oracle.py -q`
- `pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- `python -m json.tool docs/backlog/roadmap_gate.json`
- `python workflows/library/scripts/build_neurips_backlog_manifest.py --backlog-root docs/backlog/active --output state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json`
- `python workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py --manifest-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json --gate-policy-path docs/backlog/roadmap_gate.json --progress-ledger-path state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --run-state-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --output state/DSL-V214-MATERIALIZATION-VARIANTS/roadmap_gate_check.json`
- `python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json`
- Oracle comparison standard: exact normalized JSON equality for the golden
  observation fixtures; no `atol` or `rtol` applies.

## Residual Risks

- The oracle suites intentionally freeze current behavior, including brittle
  current semantics such as report-presence outcome selection. Phase 1 runtime
  work will need to update these fixtures deliberately when semantics change.
- The minimal NeurIPS workspace is intentionally narrow; it characterizes queue,
  plan-gate, and implementation-outcome behavior without mirroring every
  downstream project detail.
