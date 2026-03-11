take the role of a principal engineer, expert in PLs, compilers, and agentic engineering. review the design / ADR with no holds barred skepticism

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `brief`, `design`, and `open_findings` artifacts before acting.

First, review the current design from scratch.
Then reconcile your fresh review against the carried-forward `open_findings` ledger.

You may require internal refactoring or egregious debt paydown before feature work only when it is:
- a correctness prerequisite
- a contract prerequisite
- or a major simplicity win that materially reduces feature risk

For each prior finding, classify it as one of:
- `RESOLVED`
- `STILL_OPEN`
- `SUPERSEDED`
- `SPLIT`

You may add `NEW` findings only if they are materially distinct.
Do not preserve a finding only because it existed before.

Each finding must include a `scope_classification` of:
- `blocking_prerequisite`
- `required_in_scope`
- `recommended_followup`
- `out_of_scope`

Write JSON to the exact path named by `${inputs.state_root}/design_review_report_path.txt` using this shape:

```json
{
  "decision": "APPROVE",
  "summary": "short summary",
  "unresolved_high_count": 0,
  "unresolved_medium_count": 0,
  "findings": [
    {
      "id": "DESIGN-H1",
      "status": "RESOLVED",
      "severity": "high",
      "scope_classification": "blocking_prerequisite",
      "title": "short title",
      "description": "short explanation",
      "evidence": ["path#L1"]
    }
  ]
}
```

Also write:
- `APPROVE`, `REVISE`, or `BLOCK` to `${inputs.state_root}/design_review_decision.txt`
- the unresolved high count integer to `${inputs.state_root}/unresolved_high_count.txt`
- the unresolved medium count integer to `${inputs.state_root}/unresolved_medium_count.txt`

Use `BLOCK` only when the design should not proceed to planning without earlier refactoring or problem redefinition.
Approve only if there are no unresolved high findings and the design is ready for planning.
