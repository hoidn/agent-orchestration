## Completed In This Pass

- Tightened resume-time snapshot sidecar inflation in `orchestrator/workflow/executor.py` so sidecar-backed snapshot state now requires a recorded `sha256` before the sidecar payload is trusted.
- Tightened resume-time snapshot sidecar path resolution in `orchestrator/workflow/executor.py` so sidecar-backed snapshot state must resolve under the orchestrator-managed run root before the runtime reads it.
- Normalized malformed snapshot sidecar JSON into the designed v2.14 failure surface instead of letting raw `JSONDecodeError` escape from resume-time selector execution.
- Tightened resume-time snapshot sidecar file validation in `orchestrator/workflow/executor.py` so selector resume paths reject directory-backed sidecars through `snapshot_state_missing` instead of raising `IsADirectoryError`.
- Tightened resume-time snapshot sidecar decoding in `orchestrator/workflow/executor.py` so parsed sidecar payloads must be object-shaped snapshot mappings before selector validation continues.
- Added regression coverage in `tests/test_v214_runtime_semantics.py` for the resume-time snapshot sidecar review repros:
  - sidecar path escapes the run root via parent traversal;
  - sidecar-backed snapshot state missing its recorded hash;
  - sidecar payload present with a matching hash but invalid JSON;
  - sidecar path resolving to an in-run-root directory;
  - sidecar payload present with a matching hash but the wrong top-level JSON type.

## Completed Current-Scope Work

- Review finding 1 is fixed: resume-time snapshot sidecars are no longer accepted without a recorded integrity hash.
- Review finding 2 is fixed: resume-time snapshot sidecars that resolve to directories now fail through the designed snapshot-state error surface instead of crashing selector resume.
- Review finding 3 is fixed: structurally wrong but valid-JSON sidecar payloads now fail as workflow snapshot-state errors instead of raising `AttributeError` in selector resume.
- Previously completed current-scope protections remain in place: malformed snapshot sidecar payloads and parent-escaping sidecar paths are still normalized into the approved failure taxonomy.
- No approved current-scope implementation work remains open from the consumed design, plan, checks report, or implementation review.

## Follow-Up Work

- None recorded from this pass.

## Residual Risks

- No new current-scope residual risk was introduced in this pass. Snapshot-sidecar corruption coverage now includes escaped-path, missing-hash, malformed-JSON, directory-backed, and wrong-top-level-type resume cases; broader schema/detail mismatches still rely on the existing snapshot and selector validation already exercised by the Phase 1 runtime suite.

## Verification

- `pytest --collect-only tests/test_v214_runtime_semantics.py -q`
- `pytest tests/test_v214_runtime_semantics.py -q -k 'directory_sidecar_snapshot_payload or non_mapping_sidecar_snapshot_payload or sidecar_snapshot_without_recorded_hash or malformed_sidecar_snapshot_payload or sidecar_snapshot_path_outside_run_root'`
- `pytest tests/test_v214_runtime_semantics.py -q`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
- `pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- `python -m json.tool docs/backlog/roadmap_gate.json`
- `python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json`
