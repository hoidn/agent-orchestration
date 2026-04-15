Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, and `open_findings` artifacts before acting.

First, review the current plan from scratch.
Check that the plan faithfully carries the consumed design into executable work: material design requirements should appear as concrete tasks with proportionate verification, or be explicitly identified as outside this plan's scope with the reason.
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
