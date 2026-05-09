# Minimal NeurIPS v2.14 Behavior Matrix

## Status

This matrix records the Phase 0 oracle scenarios used to freeze current
NeurIPS-style backlog-drain behavior before v2.14 semantics land.

## Primitive Oracle Scenarios

| Scenario | Current surface under test | Expected outcome | Preserve | Normalize away |
| --- | --- | --- | --- | --- |
| `completed` | implementation report materialization | `implementation_state=COMPLETED` | bundle fields, report path, report hash | run id, workspace path |
| `blocked` | blocked progress-report materialization | `implementation_state=BLOCKED` | blocker class, progress report path, report hash | run id, workspace path |
| `both_reports` | ambiguous dual-report selection | workflow failure | failure class, both report files present | run id |
| `neither_report` | missing-output selection | workflow failure | failure class, absent outcome bundle | run id |
| `review_approve` | review decision publication | `review_decision=APPROVE` | decision artifact, review report hash | run id |
| `review_revise` | review decision publication | `review_decision=REVISE` | decision artifact, review report hash | run id |
| `materialization_ok` | relpath bundle validation | published plan path | contract-validated bundle value | run id |
| `invalid_bundle` | invalid enum bundle | no published artifact | contract violation surface, invalid candidate file | run id |
| `missing_target` | missing relpath target | no published artifact | contract violation surface, missing-target reason | run id |
| `stricter_contract` | source-contract narrowing | accepted refinement | narrowed `under`, stricter `must_exist_target`, narrowed enum set | run id |
| `weaker_contract` | source-contract weakening rejection | workflow failure | weakening violation class, rejected proposal payload | run id |
| `single_changed` | single snapshot candidate diff | `selected_variant=COMPLETED` | candidate keys, changed key, selected path, file hashes | run id |
| `no_change` | zero snapshot candidate diffs | workflow failure | failure class, candidate keys, unchanged hashes | run id |
| `multi_change` | multiple snapshot candidate diffs | workflow failure | failure class, candidate keys, changed keys, file hashes | run id |
| `variant_proof_accept` | discriminant-backed field access | `selected_variant=COMPLETED` | selected variant, accessed relpath, bundle fields | run id |
| `variant_proof_reject` | discriminant mismatch rejection | workflow failure | `variant_unavailable` evidence, required variant, selected variant | run id |

## Minimal NeurIPS Drain Scenarios

| Scenario | Selector mode | Plan source | Implementation outcome | Final drain state | Preserve | Normalize away |
| --- | --- | --- | --- | --- | --- | --- |
| `completed` | active selection | fresh | completed + approved review | `DONE` | queue transition, run-state summary, plan-gate source `FRESH` | timestamps, run id |
| `blocked` | active selection | fresh | blocked progress report | `BLOCKED` | blocked-item reason, progress-report path, run-state block entry | timestamps, run id |
| `ambiguous` | active selection | fresh | both reports written | workflow failure | failure class, conflicting report files | timestamps, run id |
| `missing_output` | active selection | fresh | neither report written | workflow failure | failure class, absent implementation bundle | timestamps, run id |
| `fresh_plan` | active selection | fresh | completed + approved review | `DONE` | plan-gate source `FRESH`, selected-item materialization paths | timestamps, run id |
| `recovered_plan` | recovered in-progress selection | recovered | completed + approved review | `DONE` | plan-gate source `RECOVERED`, recovery report path, queue outcome | timestamps, run id |
| `selected_item_runtime` | active selection | fresh | completed + approved review | `DONE` | selected-item summary, check report, backlog queue move | timestamps, run id |

## Comparison Standard

Phase 0 comparisons use exact normalized JSON equality. No `atol` or `rtol`
applies because these are structural workflow-state and artifact-path oracles,
not numeric parity checks.
