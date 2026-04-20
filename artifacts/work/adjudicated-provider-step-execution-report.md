Completed In This Pass
- Read `docs/index.md` and the consumed design, implementation plan, prior execution report, and implementation review before editing.
- Verified review findings against the current code paths for output-contract validation, promotion, scoring evidence, selection, ledger mirror materialization, and baseline null-path comparison.
- Added failing regression coverage for basename normalization in `relpath` expected-output promotion, output-bundle relpath target promotion, output-bundle evidence collection, optional-score single-candidate selection reason, optional `depends_on` null-path recording, and ledger mirror conflicts on no-selection failures.
- Fixed promotion to reuse validator-normalized artifact values when copying required relpath targets, including output-bundle fields whose raw JSON value is accepted through `under` basename normalization.
- Fixed evaluation-packet bundle target evidence to read the normalized artifact value instead of the raw JSON pointer value.
- Recorded `selected_candidate_id` in new promotion manifests and passed the selected candidate id from the executor so resume can reject manifest/current-selection mismatches.
- Fixed optional-score single-candidate selection to report `single_candidate_contract_valid` even when an optional score was successfully recorded.
- Wired optional `depends_on` paths into adjudication baseline null-path comparison so excluded optional paths are recorded as optional/absent-equivalent instead of being omitted.
- Fixed workspace-visible score ledger mirror owner conflicts so `ledger_conflict` is surfaced even for no-selection failures.
- Left unrelated dirty dashboard, roadmap, workflow, prompt, and docs-index files untouched.

Completed Current-Scope Work
- Addressed all high-severity review blockers:
  - Promotion now handles validated `relpath` basename normalization for expected outputs.
  - Scoring evidence and promotion now handle validated output-bundle relpath target normalization.
  - No-selection ledger mirror owner conflicts now fail as `ledger_conflict` instead of being silently suppressed.
  - Promotion manifests now include the selected candidate id and promotion resume compares it when the executor supplies a current selection.
- Addressed both medium review items:
  - Optional-score single-candidate selection keeps the single-candidate selection reason while retaining any recorded score.
  - Optional `depends_on` path surfaces are passed into baseline null-path comparison and recorded in the manifest.
- Verification completed:
  - Red run before fixes: six focused regression tests failed for the expected review defects.
  - `pytest tests/test_adjudicated_provider_promotion.py::test_promotes_relpath_bare_basename_normalized_under_root tests/test_adjudicated_provider_promotion.py::test_promotes_output_bundle_bare_basename_normalized_under_root tests/test_adjudicated_provider_scoring.py::test_build_evaluation_packet_uses_validated_output_bundle_artifact_values tests/test_adjudicated_provider_scoring.py::test_selection_rules_cover_single_optional_multi_partial_and_ties tests/test_adjudicated_provider_runtime.py::test_optional_depends_on_paths_are_recorded_in_baseline_null_comparison tests/test_adjudicated_provider_runtime.py::test_mirror_conflict_on_no_valid_candidates_is_reported_as_ledger_conflict -v`: 6 passed.
  - `pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_resume.py tests/test_adjudicated_provider_outcomes.py -v`: 161 passed.
  - `pytest tests/test_workflow_surface_ast.py tests/test_workflow_ir_lowering.py tests/test_provider_execution.py tests/test_artifact_dataflow_integration.py tests/test_subworkflow_calls.py tests/test_resume_command.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_workflow_examples_v0.py -k "adjudicated or provider or output or call or resume or report" -v`: 128 passed, 57 deselected.
  - `pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_dependency_injection.py tests/test_provider_integration.py tests/test_workflow_executor_characterization.py tests/test_workflow_output_contract_integration.py tests/test_workflow_examples_v0.py -v`: 224 passed.
  - `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run`: validation successful.
  - `pytest --collect-only -q tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py`: 93 tests collected.
- Numerical parity/regression tolerances: not applicable; this pass did not involve numerical comparisons or tolerance changes.

Follow-Up Work
- The approved future-extension list remains unchanged and was not implemented: parallel candidate execution, command evaluators, source-edit promotion, overlay workspaces, provider-session support in candidates, aggregate score-report tooling, and aggregate append-only ledgers.
- No additional current-scope follow-up is known from the implementation review after this pass.

Residual Risks
- Promotion manifest selected-candidate reconciliation is enforced when the executor supplies the current selected candidate id. Existing legacy manifests without `selected_candidate_id` are still resumable by the lower-level helper for backward compatibility with previously materialized test fixtures.
- Optional baseline null-path wiring currently covers `depends_on.optional`, which is the optional path surface present in this implementation's step payload. Future optional path surfaces should be added to the same helper when introduced.
- The checkout still contains unrelated pre-existing dirty files outside this task; they were not inspected for correctness and are excluded from this task's commit.
