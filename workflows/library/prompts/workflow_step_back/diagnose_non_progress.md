Read the consumed progress signals and non-progress decision before acting.

Diagnose why the recent workflow work is not converging. The workflow has
already decided that a step-back diagnosis is required; do not recount
iterations, scan artifact roots, mutate run state, or choose normal selector
routing.

Choose exactly one action:

- `REDRAFT_PLAN`
- `REVISE_REQUIREMENTS`
- `SPLIT_WORK_ITEM`
- `DROP_OR_DEMOTE_WORK_ITEM`
- `FIX_WORKFLOW_MECHANICS`
- `CONTINUE_WITH_CURRENT_PLAN`
- `NEEDS_HUMAN_DECISION`

Prefer `FIX_WORKFLOW_MECHANICS` when the evidence shows stale state, recursive
recovery, repeated prerequisite generation, or routing mismatch. Prefer
`REDRAFT_PLAN` or `SPLIT_WORK_ITEM` when the work item is valid but the plan is
not converging. Use `NEEDS_HUMAN_DECISION` only for a real external decision
that the repository cannot resolve.

Write the output bundle JSON to the output-contract path.

```json
{
  "action": "FIX_WORKFLOW_MECHANICS",
  "rationale": "Short reason grounded in the consumed signals and decision."
}
```
