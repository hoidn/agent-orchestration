Read the consumed progress signals and non-progress decision before acting.

Diagnose why the recent workflow work is not converging. The workflow has
already decided that a step-back diagnosis is required; do not recount
iterations, scan artifact roots, mutate run state, or choose normal selector
routing.

Choose exactly one action:

- `CONTINUE_WITH_CURRENT_PLAN`
- `FIX_WORKFLOW_MECHANICS`
- `NEEDS_HUMAN_DECISION`

Use `CONTINUE_WITH_CURRENT_PLAN` when the loop's own recovery machinery is the
right responder to the evidence. Use `FIX_WORKFLOW_MECHANICS` when the
workflow itself is broken — stale state, recursive recovery, repeated
prerequisite generation, or a routing mismatch — and the drain should end for
repair. Use `NEEDS_HUMAN_DECISION` only for a real external decision that the
repository cannot resolve; this also ends the drain.

Write the output bundle JSON to the output-contract path.

```json
{
  "action": "FIX_WORKFLOW_MECHANICS",
  "rationale": "Short reason grounded in the consumed signals and decision."
}
```
