# Adjudicated Provider Step Execution Report

## Completed In This Pass

- Fixed ledger mirror conflicts so `LedgerConflictError` is translated into a normalized adjudicated step failure with `error.type: ledger_conflict` instead of escaping as an uncaught runtime exception.
- Persisted scorer snapshots to `scorer/metadata.json`, including evaluator prompt content/hash, provider identity, resolved params, evidence limits, confidentiality policy, optional rubric content/hash, and `scorer_identity_hash`.
- Persisted scorer-resolution failure metadata to `scorer/resolution_failure.json` and keyed scorer-unavailable ledger rows from `scorer_resolution_failure_key`.
- Passed optional evaluator rubric content into score-critical evaluation packets.
- Tightened promotion rollback so parent validation failure rolls back only when touched destinations still match staged source hashes, and reports `promotion_rollback_conflict` without deleting or overwriting concurrent parent changes.
- Scoped adjudication sidecars and ledger owner fields to the current execution frame. Root steps still use `root`; adjudicated steps inside reusable calls use the durable call-frame id with a path-safe sidecar scope under the canonical parent run root.
- Removed numeric evaluator score from `score_run_key` identity for scored rows so non-deterministic score values do not change the row key for the same candidate packet and scorer snapshot.
- Recorded the current rationale for keeping baseline, scoring, ledger, promotion, and outcome helpers in one adjudication module for this tranche.

## Completed Plan Tasks

- Advanced Task 4 promotion completion by adding rollback-conflict behavior for parent validation failures after promotion writes.
- Advanced Task 5 scorer and ledger completion by persisting scorer snapshots, persisting scorer-unavailable metadata, using rubric evidence, and correcting score-row key identity.
- Advanced Task 6 runtime completion by normalizing ledger mirror conflicts and preserving adjudication failure outcomes through step-result persistence.
- Advanced frame-scoped state/ledger ownership from the design by covering adjudicated provider execution inside reusable-call frames.

## Remaining Required Plan Tasks

- Task 4 still needs exhaustive promotion coverage for destination preimage modes, duplicate destination roles, manifest-created directory cleanup, and promotion resume-state tests/implementation.
- Task 5 still needs dynamic ledger/output collision coverage, full mirror ownership conflict matrix coverage, unreadable/non-UTF-8 rubric and evidence cases beyond the current packet tests, and broader scorer-unavailable runtime variants.
- Task 6 runtime coverage remains incomplete for invalid candidate exclusion, required-score single-candidate failure, scorer-resolution failure paths, and stdout/stderr sidecar assertions.
- Task 7 deadline/retry semantics remain incomplete: candidate and evaluator retry loops are not fully wired to one logical step deadline.
- Task 9 resume reconciliation remains unimplemented for persisted baseline, candidate, scorer, packet, ledger, mirror, and promotion state.
- No numerical parity comparison or tolerance changes were involved in this pass.

## Verification

- `pytest tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py -q` -> 27 passed.
- `pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q` -> 83 passed.
- `pytest tests/test_workflow_examples_v0.py -k adjudicated -q` -> 1 passed, 27 deselected.
- `python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run` -> workflow validation successful.
- `pytest tests/test_runtime_step_lifecycle.py tests/test_subworkflow_calls.py -q` -> 32 passed.
- `pytest --collect-only tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py -q` -> 27 tests collected.
- `pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py tests/test_runtime_step_lifecycle.py tests/test_subworkflow_calls.py -q` -> 115 passed.
- `git diff --check` -> no whitespace errors.

## Residual Risks

- Promotion remains narrower than the full resume-safe transaction design; interrupted promotion resume and manifest-created directory cleanup are still follow-up work.
- Scorer snapshot persistence is now present, but full resume reconciliation against changed scorer identity is still missing.
- Ledger mirror conflict handling is normalized, but the full dynamic collision and owner-conflict matrix remains incomplete.
- Candidate/evaluator retries and logical deadline enforcement are still partial.
- Candidate workspaces remain process-level copies, not OS sandboxes.
