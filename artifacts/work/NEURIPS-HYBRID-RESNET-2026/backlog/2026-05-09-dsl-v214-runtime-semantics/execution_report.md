## Completed In This Pass

- Extended the loader’s Phase 1 artifact catalog so `variant_output`, `select_variant_output`, and `materialize_artifacts` surfaces publish typed authored-step metadata for validation-time ref analysis.
- Added narrow loader validation for `materialize_artifacts`, `pre_snapshot`, `select_variant_output`, and `requires_variant`, including author-time variant-proof enforcement on variant-only refs and explicit rejection of snapshot refs outside `select_variant_output.evidence.snapshot.ref`.
- Propagated match-case proof context for discriminant-based variant routing so variant-only refs inside the proven case load successfully without weakening the existing runtime `variant_unavailable` guard.
- Added normalized report projections for selected variants and snapshot summaries in `orchestrator/observability/report.py`, with markdown rendering that surfaces those summaries directly instead of requiring readers to inspect raw debug payloads.
- Added focused regression coverage in `tests/test_loader_validation.py` and `tests/test_observability_report.py` for unproved variant refs, match-proved refs, snapshot-ref misuse, and the new report projection.

## Completed Current-Scope Work

- Review finding 1 is fixed: variant-only structured refs now fail at load time without match or `requires_variant` proof, and match over the same discriminant provides the approved author-time proof path.
- Review finding 2 is fixed: snapshot refs remain runtime-resolvable for selector evidence, but authored misuse outside `select_variant_output.evidence.snapshot.ref` is now rejected during load.
- Review finding 3 is fixed: status reports now project selected variants and snapshot summaries directly from step state/debug payloads, satisfying the remaining current-scope observability requirement.

## Follow-Up Work

- Add resume-path corruption and missing-sidecar coverage for persisted snapshot records before wider workflow dependence accumulates around snapshot sidecars.
- Broaden author-time proof coverage beyond the current Phase 1 materialization/snapshot-selector surfaces if later tranches introduce additional authored ref surfaces that can legally target variant-only fields.

## Residual Risks

- Snapshot sidecar integrity handling is implemented, but resume-path corruption and missing-sidecar scenarios were not part of this pass's executed test set.
- The new author-time proof enforcement is intentionally scoped to the current Phase 1 authored surfaces that can consume typed refs (`materialize_artifacts`, `pre_snapshot`, `select_variant_output`, and match-case routing); any future expansion of variant-only ref surfaces should add the same proof plumbing explicitly.

## Verification

- `pytest tests/test_loader_validation.py -q -k 'variant_specific_materialize_ref_requires_author_time_proof or match_case_proof_allows_variant_specific_materialize_ref or snapshot_refs_are_restricted_to_selector_evidence'`
- `pytest tests/test_observability_report.py -q -k 'variant_and_snapshot_summaries'`
- `pytest tests/test_loader_validation.py tests/test_observability_report.py tests/test_v214_runtime_semantics.py -q`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
- `pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- `python -m json.tool docs/backlog/roadmap_gate.json`
- `python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json`
