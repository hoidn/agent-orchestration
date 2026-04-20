# Adjudicated Provider Step Execution Report

## Completed In This Pass

- Fixed the high-severity logical deadline/retry defect from the implementation review.
- Wired a single `AdjudicationDeadline` through adjudicated provider execution and passed only the remaining logical budget to candidate and evaluator provider invocations.
- Added candidate provider retry handling using the adjudicated step's effective provider retry policy. Each retry starts from a fresh copy of the immutable baseline workspace, so failed-attempt files are not reused.
- Added evaluator retry handling using the same retry policy while reusing the already-persisted evaluation packet and without rerunning candidate generation.
- Changed exhausted candidate/evaluator timeout attempts to surface the logical step failure as `error.type: timeout`, `exit_code: 124`, and retryable timeout outcome instead of `adjudication_no_valid_candidates`.
- Added regression coverage for candidate timeout normalization, candidate retry/fresh-baseline behavior, and evaluator retry packet reuse.

## Completed Plan Tasks

- Advanced Task 7 Step 1 by covering candidate subprocess timeout as a logical adjudicated step timeout.
- Advanced Task 7 Step 2 by covering candidate provider retry scope, fresh baseline retry workspaces, and ledger `attempt_count: 2` for the retried candidate.
- Advanced Task 7 Step 3 by covering evaluator retry scope, evaluation packet reuse, and no candidate rerun.
- Advanced Task 7 Step 7 by implementing candidate and evaluator retry loops around provider subprocesses.
- No design, location, or ownership deviation was introduced. No numerical parity comparison or tolerance change was involved.

## Remaining Required Plan Tasks

- Task 4 promotion completion remains required: destination preimage coverage for all modes, destination conflict/rollback matrix, duplicate destination-role coverage, manifest-created directory cleanup, and promotion resume-state behavior.
- Task 5 completion remains required: scorer-unavailable metadata variants, full ledger mirror owner-conflict matrix, terminal-only mirror materialization proof, and complete packet/ledger metadata coverage.
- Task 6 completion remains required for scorer-resolution failure variants, required-score single-candidate behavior, invalid candidate exclusion variants, and stdout/stderr sidecar assertions.
- Task 7 remains partially incomplete: deadline tests do not yet cover every runtime-owned phase, retry-delay deadline crossing, candidate exit-code `124` retry success, exhausted evaluator variants, or non-retried terminal runtime failures.
- H2 / Task 9 remains required: resume-safe reconciliation for persisted baseline, candidate, scorer, packet, ledger, mirror, and promotion state is still unimplemented.

## Verification

- `pytest tests/test_adjudicated_provider_runtime.py -k "candidate_timeout_returns_logical_step_timeout or candidate_retry_starts_from_fresh_baseline or evaluator_retry_reuses_packet" -q` -> first run failed as expected before implementation: 3 failed.
- `pytest tests/test_adjudicated_provider_runtime.py -k "candidate_timeout_returns_logical_step_timeout or candidate_retry_starts_from_fresh_baseline or evaluator_retry_reuses_packet" -q` -> 3 passed, 9 deselected.
- `pytest tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q` -> 25 passed.
- `pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q` -> 88 passed.
- `pytest --collect-only tests/test_adjudicated_provider_runtime.py -q` -> 12 tests collected.
- `pytest tests/test_workflow_examples_v0.py -k adjudicated -q` -> 1 passed, 27 deselected.
- `python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run` -> workflow validation successful.
- `pytest tests/test_runtime_step_lifecycle.py tests/test_subworkflow_calls.py -q` -> 32 passed.
- `python -m py_compile orchestrator/workflow/executor.py` -> passed.
- `git diff --check -- orchestrator/workflow/executor.py tests/test_adjudicated_provider_runtime.py artifacts/work/adjudicated-provider-step-execution-report.md` -> no whitespace errors.

## Residual Risks

- The logical deadline is now enforced before major runtime-owned phases and through candidate/evaluator subprocess timeouts, but the full phase-by-phase Task 7 deadline matrix is not complete.
- Candidate and evaluator retry metadata is in runtime candidate records; durable resume reconciliation and sidecar reuse are still pending under Task 9.
- Promotion and ledger transaction completeness remain the largest correctness risks for interrupted runs.
- Candidate workspaces remain copy-backed process workspaces, not OS sandboxes.
