Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, and `open_findings` artifacts before acting.

First, review the current plan from scratch.
Check that the plan faithfully carries the consumed design into bounded executable work: material design requirements should appear as concrete tasks, or be explicitly identified as outside this plan's scope with the reason.
Check scope discipline before approval. Reject plans that cover every design topic by default instead of selecting a coherent current implementation scope and moving later work to follow-up. Reject plans that call the whole target system or first release the current scope when the work spans multiple major behavioral surfaces. Major surfaces include contract/docs, schema/loading, runtime behavior, state/resume, observability/reporting, examples/integration, durable artifacts/data, and public API. Current scope should include one coherent slice, plus only the prerequisite work needed to make that slice truthful, preserve an existing contract touched by that slice, prevent data loss or corruption in that slice, or unblock the next immediate slice.
Reject plans that collapse the design's component boundaries, interfaces, invariants, or durable artifact contracts into undifferentiated implementation work instead of assigning tasks along those boundaries.
Reject plans that ignore or weaken design or roadmap layout and ownership decisions, or change locations or unit boundaries without explicit rationale.
Reject plans that need an Implementation Architecture section because correctness or maintainability depends on a boundary decision, but do not define implementable units and owned boundaries. Boundary decisions include component or file ownership, API or command surface, data or artifact contract, authored-vs-derived split, dependency direction, compatibility or migration boundary, and future consumer contract. A single-unit plan is acceptable only when the plan explicitly says no such boundary decision is needed.
Reject plans whose task list is dominated by exhaustive case matrices unless those matrices are part of the current-scope contract.
Reject plans that blur authored and derived artifacts or introduce reusable code without a maintainability rationale.
Then reconcile your fresh review against the carried-forward `open_findings` ledger.

For each prior finding, classify it as one of:
- `RESOLVED`
- `STILL_OPEN`
- `SUPERSEDED`
- `SPLIT`

You may add `NEW` findings only if they are materially distinct.
Do not preserve a finding only because it existed before.

For the output contract's `plan_review_report_path`, read the path recorded in that file and write JSON to that current-checkout-relative path using this shape. Leave the `plan_review_report_path` file containing only the path.

```json
{
  "decision": "APPROVE",
  "summary": "short summary",
  "unresolved_high_count": 0,
  "unresolved_medium_count": 0,
  "findings": [
    {
      "id": "PLAN-H1",
      "status": "RESOLVED",
      "severity": "high",
      "title": "short title",
      "description": "short explanation",
      "evidence": ["path#L1"]
    }
  ]
}
```

Also write:
- `APPROVE` or `REVISE` to the `plan_review_decision` path specified in the Output Contract
- the unresolved high count integer to the `unresolved_high_count` path specified in the Output Contract
- the unresolved medium count integer to the `unresolved_medium_count` path specified in the Output Contract

Approve only if there are no unresolved high findings and the plan is ready to execute without inventing architecture or silently dropping material design requirements.
