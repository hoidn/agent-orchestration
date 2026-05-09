## Completed In This Pass

- Tightened loader validation so `pre_snapshot.digest` must be `sha256` and `select_variant_output.evidence.mode` must be `snapshot_diff`.
- Added explicit loader-side pointer-authority enforcement for `materialize_artifacts` publishes so noncanonical local relpath pointers now fail with `pointer_authority_conflict`.
- Updated publish-time dataflow handling to maintain the canonical top-level relpath pointer file and reject conflicting local materialization pointers before artifact lineage is recorded.
- Hardened `select_variant_output` runtime validation so selector evidence now rejects non-`snapshot_diff/v1` snapshot records, non-`sha256` digests, and snapshot/variant key mismatches instead of silently coercing them.
- Added focused regression coverage in `tests/test_loader_validation.py` and `tests/test_v214_runtime_semantics.py` for the review repros and the canonical-pointer happy path.

## Completed Current-Scope Work

- Review finding 1 is fixed: published relpath materializations now require canonical pointer ownership at load time, and successful publishes write the canonical top-level pointer file during runtime.
- Review finding 2 is fixed: unsupported snapshot selector contracts no longer load, and selector runtime execution now rejects mismatched snapshot metadata instead of normalizing it.
- No approved current-scope work remains open from the consumed implementation review.

## Follow-Up Work

- Add resume-path corruption coverage for snapshot sidecars, especially invalid JSON sidecars in addition to the existing missing-sidecar and hash-mismatch handling.
- Add a dedicated regression for runtime pointer-authority rejection on validation-bypassed state if later internal callers can construct executable steps without loader validation.

## Residual Risks

- Snapshot sidecar integrity behavior is still only partially covered; this pass did not add invalid-JSON sidecar resume tests.
- Canonical pointer writes now happen at publish time for relpath artifacts; broader legacy-surface expectations outside the exercised suites still rely on existing coverage rather than a repo-wide publish-pointer audit.

## Verification

- `pytest tests/test_loader_validation.py -q -k 'materialize_published_relpath_pointer_must_match_canonical_artifact_pointer or pre_snapshot_digest_must_be_sha256 or select_variant_output_evidence_mode_must_be_snapshot_diff'`
- `pytest tests/test_v214_runtime_semantics.py -q -k 'materialize_artifacts_publish_writes_canonical_top_level_pointer or select_variant_output_rejects_runtime_snapshot_metadata_mismatch'`
- `pytest tests/test_loader_validation.py tests/test_v214_runtime_semantics.py -q`
- `pytest tests/test_artifact_dataflow_integration.py -q -k 'pointer or publish'`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
- `pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- `python -m json.tool docs/backlog/roadmap_gate.json`
- `python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json`
