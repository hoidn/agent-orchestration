# Adjudicated Provider Step Execution Report

## Completed In This Pass

- Fixed review H2: `score_ledger_path` is now substituted in the active execution frame before collision checks, state projection, and workspace-visible mirror materialization. The resolved mirror path is runtime-checked as workspace-relative, under `artifacts/`, and protected against symlink escapes outside the parent workspace.
- Fixed review H3: candidate and evaluator subprocess exit code `124` is now treated as candidate/evaluator attempt metadata unless the shared logical adjudicated-step deadline is actually exhausted. Candidate exit `124` can retry while deadline remains, and an exited/timed-out candidate no longer prevents later candidates from running.
- Strengthened ledger/state materialization from review M1: the run-local ledger is written after selection with selected-row `promotion_status: "pending"` before promotion starts, the workspace-visible mirror remains withheld until terminal finalization, and candidate state now projects `candidate_run_key`, `score_run_key`, and attempt metadata.
- Added regression coverage for resolved ledger mirror paths, artifacts symlink escape rejection, subprocess exit `124` continuation/retry behavior, pre-promotion pending run-ledger materialization, and candidate ledger key projection.
- No design, location, ownership, YAML, prompt, or transient-state deviation was introduced. No numerical parity comparison or tolerance change was involved.

## Completed Plan Tasks

- Closed the concrete Task 5 / ledger contract defect reported as H2 by substituting and path-checking `score_ledger_path` before mirror writes.
- Closed the concrete Task 7 / deadline-retry defect reported as H3 by separating subprocess exit `124` from logical adjudicated-step timeout.
- Advanced Task 5 Step 8 with runtime coverage for substituted mirror paths, symlink escape rejection, and terminal-only mirror withholding while the run-local ledger records pending selection.
- Advanced Task 7 Step 2 with runtime coverage proving candidate exit `124` can retry successfully while the logical deadline remains.
- Advanced Task 9 prerequisites by preserving selection and ledger identity state needed for later resume reconciliation.

## Remaining Required Plan Tasks

- H1 / Task 9 remains required: full resume-safe reconciliation for persisted baseline, candidate, scorer, packet, ledger, mirror, publication, and report projection state is still unimplemented. Existing sidecars still fail fast instead of being reconciled.
- Task 5 remains partially incomplete for the full scorer-unavailable metadata variant matrix and the complete workspace-visible mirror matrix, including all owner-conflict, invalid JSONL, shared-path, and published relpath pointer cases.
- Task 6 Step 2 remains partially incomplete for the full required-score scorer-unavailable runtime variant matrix.
- Task 7 remains partially incomplete for the full logical-deadline phase matrix, retry-delay deadline crossing, exhausted evaluator variants, non-retried terminal runtime failure coverage, and explicit step-visit-count/other-candidate retry assertions.
- The adjudication helper module still needs to be split before full resume reconciliation expands it further.

## Verification

- `pytest tests/test_adjudicated_provider_runtime.py -q` -> first regression run failed as expected: 4 failed, 17 passed.
- `pytest tests/test_adjudicated_provider_runtime.py::test_score_ledger_path_rejects_artifacts_symlink_escape -q` -> first symlink-escape regression run failed as expected: 1 failed.
- `pytest tests/test_adjudicated_provider_runtime.py::test_score_ledger_path_rejects_artifacts_symlink_escape -q` -> 1 passed.
- `pytest tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q` -> 52 passed.
- `pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q` -> 108 passed.
- `pytest --collect-only tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q` -> 35 tests collected.
- `python -m py_compile orchestrator/workflow/executor.py` -> passed.
- `python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run` -> workflow validation successful.
- `pytest tests/test_workflow_examples_v0.py -k adjudicated -q` -> 1 passed, 28 deselected.
- `pytest tests/test_workflow_examples_v0.py tests/test_prompt_contract_injection.py -q` -> 50 passed.
- `git diff --check` -> passed.

## Residual Risks

- Resume reconciliation is still the largest correctness gap; interruption after sidecar creation still cannot resume to completion.
- Mirror conflict coverage is stronger but still not the full approved matrix.
- Deadline and retry coverage now covers exit `124` continuation/retry behavior, but the full phase matrix remains outstanding.
- Candidate workspaces remain copy-backed process workspaces, not OS sandboxes.
