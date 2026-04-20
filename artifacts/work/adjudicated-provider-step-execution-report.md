# Adjudicated Provider Step Execution Report

## Completed In This Pass

- Fixed evaluator packet evidence for consumed relpath artifacts. Adjudicated candidates now pass injected consumed artifact values and required relpath target contents into score-critical packet construction, including evidence-limit and declared-secret scanning.
- Fixed promotion preimage handling for included directories. Baseline manifests now record included directories, so a directory at a future file destination is treated as an unavailable baseline preimage and remains a promotion conflict even if removed after baseline creation.
- Closed the Task 7 deadline and non-retried terminal-failure coverage tranche. Added fake-clock tests for remaining candidate/evaluator timeout budgets and deadline expiry after baseline, candidate copy, selection, pending ledger materialization, promotion, and parent validation.
- Added non-retry coverage for dynamic ledger path collision, workspace-visible ledger conflict, ledger mirror failure, promotion conflict, promotion validation failure, and promotion rollback conflict with step retries enabled.
- Updated the implementation plan checkboxes for Task 7 Step 1 and Step 4. No YAML, prompt, transient state, design-location, or ownership deviation was introduced. No numerical parity comparison or tolerance change was involved.

## Completed Plan Tasks

- Completed Task 7 Step 1: fake-clock logical-deadline tests now cover shared remaining budgets, no provider launch after candidate-copy expiry, no ledger/promotion progression after runtime-owned phase expiry, and timeout after final parent validation overruns the logical deadline.
- Completed Task 7 Step 4: non-retried terminal-failure tests now cover `ledger_path_collision`, `ledger_conflict`, `ledger_mirror_failed`, `promotion_conflict`, `promotion_validation_failed`, and `promotion_rollback_conflict`.
- Addressed review H2: evaluation packets now embed consumed relpath target content that was injected into candidate prompts.
- Addressed review H3: promotion preimages no longer treat included baseline directories as absent destinations.

## Remaining Required Plan Tasks

- Task 9 remains required: resume-safe reconciliation for persisted baseline, candidate, scorer, packet, ledger, mirror, promotion, publication, and report projection state is still unimplemented; existing sidecars still fail fast.
- Task 9 Step 1 and Step 2 remain required for resume-after-candidates and resume-after-promotion tests.
- Task 9 Step 3 remains required for resume mismatch tests covering missing baseline, changed candidate config/prompt hash, changed scorer identity, scorer-unavailable transitions, missing scorer snapshot, and malformed scorer-unavailable ledger state.
- Task 9 Step 4 remains required for curated report projection of selected candidate id, selected/null score, selection reason, score ledger paths, promotion status, and adjudication failure type.
- Task 9 Step 5 through Step 7 remain required for durable resume markers, reconciliation implementation, and passing resume/observability selectors.
- The adjudication helper module still needs to be split before full resume reconciliation expands it further.

## Verification

- `pytest tests/test_adjudicated_provider_scoring.py -k "consumed_relpath" -q` -> first regression run failed as expected with unsupported consumed-evidence packet arguments; final run passed: 2 passed, 18 deselected.
- `pytest tests/test_adjudicated_provider_promotion.py::test_promotion_rejects_destination_directory_removed_after_baseline -q` -> first regression run failed as expected because promotion did not raise; final run passed: 1 passed.
- `pytest tests/test_adjudicated_provider_runtime.py::test_evaluator_packet_includes_consumed_relpath_target_content -q` -> first regression run failed as expected with required-score adjudication failure; final run passed: 1 passed.
- `pytest tests/test_adjudicated_provider_runtime.py -k "logical_deadline_remaining_budget or deadline_expiring" -q` -> first run exposed three deadline gaps; final run passed: 7 passed, 35 deselected.
- `pytest tests/test_adjudicated_provider_runtime.py -k "ledger_mirror_conflict_returns_normalized or output_bundle_relpath_target_ledger_collision or ledger_mirror_failure_is_not_retried or promotion_terminal_failures_are_not_retried or promotion_conflict_is_not_retried" -q` -> 6 passed, 39 deselected.
- `pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q` -> 136 passed.
- `pytest --collect-only tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py -q` -> 79 tests collected.
- `python -m py_compile orchestrator/workflow/adjudication.py orchestrator/workflow/executor.py` -> passed.
- `python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run` -> workflow validation successful.
- `pytest tests/test_workflow_examples_v0.py -k adjudicated -q` -> 1 passed, 28 deselected.
- `pytest tests/test_workflow_examples_v0.py tests/test_prompt_contract_injection.py -q` -> 50 passed.
- `git diff --check` -> passed.

## Residual Risks

- Resume reconciliation is still the largest correctness gap; interrupted adjudicated sidecars still cannot resume to completion.
- Observability reports still need curated adjudication projection tests instead of relying on raw adjudication payloads.
- `orchestrator/workflow/adjudication.py` remains an omnibus helper module and should be split before Task 9 implementation.
- Candidate workspaces remain copy-backed process workspaces, not OS sandboxes.
