Completed In This Pass
- Read consumed design and implementation plan before runtime edits, plus `docs/index.md`.
- Preserved the current dirty checkout and left unrelated dashboard, roadmap, prompt, and workflow files untouched.
- Converted `orchestrator.workflow.adjudication` from a single module into a package with `models`, `paths`, `baseline`, `evidence`, `scoring`, `ledger`, `promotion`, `resume`, and an internal `utils` module.
- Preserved the legacy `orchestrator.workflow.adjudication` public import surface through package-root re-exports, including compatibility hooks used by existing tests.
- Added a structural package-split regression test and a dedicated `tests/test_adjudicated_provider_resume.py` selector for the plan's resume verification gate.
- Updated `docs/index.md` so the adjudicated provider implementation plan entry matches the full first-release scope.

Completed Plan Tasks
- Task 1: Baseline collection/tests and spec contract diff.
- Task 2: DSL `2.11` authored surface and loader validation.
- Task 3: Adjudication runtime helper package split.
- Task 4: Baseline snapshot, null-path comparison, and candidate workspace copy.
- Task 5: Candidate execution in candidate workspaces.
- Task 6: Scorer identity and evaluation packet construction.
- Task 7: Evaluator invocation, score parsing, and selection semantics.
- Task 8: Run-local ledgers and workspace-visible mirrors.
- Task 9: Transactional selected-output promotion.
- Task 10: Step state, publication, outcomes, and stdout suppression.
- Task 11: Resume reconciliation, deadline continuation, and idempotency.
- Task 12: Observability/report projection.
- Task 13: Shared evaluator prompt, example workflow, and docs.
- Task 14: Final integration gate.

Remaining Required Plan Tasks
- None.

Verification
- `pytest --collect-only -q tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py`: 146 collected before the package split.
- `pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -v`: 146 passed before the package split.
- `pytest tests/test_adjudicated_provider_baseline.py::test_adjudication_runtime_helpers_are_split_into_public_submodules -v`: failed red first with `ModuleNotFoundError` against the single-file module, then passed after the package split.
- `pytest --collect-only -q tests/test_adjudicated_provider_resume.py`: 10 collected.
- `pytest tests/test_adjudicated_provider_resume.py tests/test_resume_command.py -k "adjudicated or resume or mismatch or promotion" -v`: 42 passed.
- `pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_resume.py tests/test_adjudicated_provider_outcomes.py -v`: 157 passed.
- `pytest tests/test_prompt_contract_injection.py -v`: 21 passed.
- `pytest tests/test_workflow_surface_ast.py tests/test_workflow_ir_lowering.py tests/test_provider_execution.py tests/test_artifact_dataflow_integration.py tests/test_subworkflow_calls.py tests/test_resume_command.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_workflow_examples_v0.py -k "adjudicated or provider or output or call or resume or report" -v`: 128 passed, 57 deselected.
- `pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_dependency_injection.py tests/test_provider_integration.py tests/test_workflow_executor_characterization.py tests/test_workflow_output_contract_integration.py tests/test_workflow_examples_v0.py -v`: 224 passed.
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run`: validation successful.
- Numerical parity/regression tolerances: not applicable; the plan identified no atol/rtol-based numerical comparison for this implementation.

Residual Risks
- The package split adds an internal `utils.py` module not named in the plan to avoid duplicated private helper logic and circular imports; public behavior remains through the existing root import path.
- `tests/test_adjudicated_provider_resume.py` re-exports existing runtime resume scenarios instead of moving the shared runtime harness; this keeps the plan's selector stable without duplicating a large test harness.
- The checkout contained pre-existing unrelated dirty files when this pass started; those were not inspected for correctness and should remain outside this task's commit.
