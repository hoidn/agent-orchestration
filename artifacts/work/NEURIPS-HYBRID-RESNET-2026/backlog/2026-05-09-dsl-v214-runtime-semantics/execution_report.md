## Completed In This Pass

- Tightened resume-time snapshot sidecar inflation in `orchestrator/workflow/executor.py` so sidecar-backed snapshot state now requires a recorded `sha256` before the sidecar payload is trusted.
- Tightened resume-time snapshot sidecar path resolution in `orchestrator/workflow/executor.py` so sidecar-backed snapshot state must resolve under the orchestrator-managed run root before the runtime reads it.
- Normalized malformed snapshot sidecar JSON into the designed v2.14 failure surface instead of letting raw `JSONDecodeError` escape from resume-time selector execution.
- Added regression coverage in `tests/test_v214_runtime_semantics.py` for the resume-time snapshot sidecar review repros:
  - sidecar path escapes the run root via parent traversal;
  - sidecar-backed snapshot state missing its recorded hash;
  - sidecar payload present with a matching hash but invalid JSON.

## Completed Current-Scope Work

- Review finding 1 is fixed: resume-time snapshot sidecars are no longer accepted without a recorded integrity hash.
- Review finding 2 is fixed: malformed snapshot sidecar payloads now fail as workflow snapshot-state errors instead of crashing the resume path.
- Review finding 3 is fixed: resume-time snapshot sidecars now reject absolute or parent-escaping paths before any external file is read.
- No approved current-scope implementation work remains open from the consumed design, plan, checks report, or implementation review.

## Follow-Up Work

- None recorded from this pass.

## Residual Risks

- Snapshot-sidecar corruption coverage now includes escaped-path, missing-hash, and malformed-JSON resume cases, but structurally valid yet semantically corrupted sidecar payloads still rely on the broader existing snapshot/selector validation coverage.

## Verification

- `pytest tests/test_v214_runtime_semantics.py::test_select_variant_output_rejects_sidecar_snapshot_path_outside_run_root -q`
- `pytest tests/test_v214_runtime_semantics.py -q -k 'sidecar_snapshot_without_recorded_hash or malformed_sidecar_snapshot_payload'`
- `pytest tests/test_v214_runtime_semantics.py -q`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
- `pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- `python -m json.tool docs/backlog/roadmap_gate.json`
- `python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json`
