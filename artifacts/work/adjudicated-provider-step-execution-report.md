# Adjudicated Provider Step Execution Report

## Completed In This Pass

- Added DSL `2.11` loader, surface AST, executable IR, lowering, runtime-step, and executor dispatch support for `adjudicated_provider`.
- Added adjudication helpers for frame/visit paths, baseline copy manifests, candidate workspace preparation, scoring packets, evaluator JSON parsing, selection, score ledgers, ledger mirrors, outcome mapping, and selected-output promotion.
- Added runtime execution for sequential adjudicated candidates using candidate workspaces, evaluator scoring, selected-output promotion, stdout suppression, adjudication state, and normal artifact publication after promotion.
- Added the reusable evaluator prompt and `workflows/examples/adjudicated_provider_demo.yaml`, then indexed the example.
- Updated normative specs, workflow author guidance, docs index, report projection, and this execution report.
- Recorded one plan deviation: the approved plan called for per-task commits, but the user requested a single final scoped commit in the current checkout, so intermediate commits were intentionally skipped.

## Completed Plan Tasks

- Task 1: documentation for the `2.11` DSL surface, validation, provider/evaluator delivery, IO, state, observability, security, versioning, and acceptance.
- Task 2 and Task 3: loader tests plus loader/IR/lowering/runtime-step support.
- Task 4: baseline path/copy helpers and selected-output promotion helpers for the covered V1 cases.
- Task 5: scorer identity, evidence packet, evaluator parsing, selection, score-row, and mirror helper coverage for the covered V1 cases.
- Task 6: mocked-provider runtime execution for highest score, candidate-order tie-break, optional single-candidate score failure, partial multi-candidate scoring failure, stdout suppression, promotion, and publication.
- Task 7: outcome mapping and deadline helper coverage.
- Task 8: reusable evaluator prompt, demo workflow, workflow index, and adjudicated example smoke test.
- Task 10: workflow drafting guide and docs index updates plus required verification commands.

## Remaining Required Plan Tasks

- Task 4 deeper promotion coverage remains: exhaustive destination preimage modes, duplicate destination roles, rollback conflict cases, and promotion resume-state tests are not complete.
- Task 5 deeper scorer/ledger coverage remains: scorer-unavailable snapshot persistence, non-UTF-8/read-error packet cases, dynamic ledger/output collision checks, and full mirror ownership conflict matrix are not complete.
- Task 6 runtime coverage remains partial for invalid candidate exclusion, scorer-resolution failure, required-score single-candidate failure, and log sidecar assertions.
- Task 7 is not fully wired at runtime: one logical wall-clock deadline is represented by a helper, but candidate/evaluator subprocess retries do not yet fully share and enforce that deadline.
- Task 9 resume reconciliation is not implemented: persisted baseline/candidate/scorer/packet/ledger/promotion state is not fully reconciled on `orchestrator resume`, and `adjudication_resume_mismatch` is covered as an outcome mapping rather than an end-to-end resume behavior.
- No numerical parity or regression tolerances were specified by the plan, so no `atol`/`rtol` comparison standard applied.

## Verification

- `pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q` -> 77 passed.
- `pytest --collect-only tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q` -> 77 tests collected.
- `python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run` -> workflow validation successful.
- `pytest tests/test_workflow_examples_v0.py -k adjudicated -q` -> 1 passed, 27 deselected.
- `pytest tests/test_workflow_examples_v0.py tests/test_prompt_contract_injection.py -q` -> 49 passed.
- `pytest tests/test_observability_report.py -q` -> 21 passed.
- `git diff --check` -> no whitespace errors after fixing docs-index trailing whitespace.

## Residual Risks

- The feature is a sequential V1 runtime; no candidate concurrency is implemented.
- Resume, retry, and promotion rollback semantics are narrower than the full design and should be treated as follow-up work before relying on interrupted-run recovery.
- Score-critical evidence handling is text-focused and covered for size and declared-secret checks, but not the full binary/read-error matrix.
- Candidate workspaces reduce orchestrator-managed output bleed-through but are not OS sandboxes; child providers retain the filesystem access permitted by the process environment.
