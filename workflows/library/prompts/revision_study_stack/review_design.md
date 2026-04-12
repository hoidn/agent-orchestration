Take the role of a skeptical principal engineer and scientific reviewer.

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `revision_design_seed`, `revision_context`, `approved_design`, and `open_findings` artifacts before acting.

Review the approved revision-study design from scratch, then reconcile your findings against the carried `open_findings` ledger. The design is ready only if it gives an implementation agent enough information to execute the study without inventing scientific policy, provenance rules, or reviewer-response scope.

Check especially for:
- ambiguity about source data, metric policy, or manuscript claim boundaries
- missing dependency/version/license/provenance decisions
- unclear pivot criteria when an experiment or external solver does not work cleanly
- missing required final assets or verification
- accidental instructions to edit the seed design in place
- scope too large for one coherent implementation plan

Write JSON to the path recorded by the `design_review_report_path` output-contract pointer using this shape:

```json
{
  "decision": "APPROVE",
  "summary": "short summary",
  "unresolved_high_count": 0,
  "unresolved_medium_count": 0,
  "findings": [
    {
      "id": "DESIGN-H1",
      "status": "NEW",
      "severity": "high",
      "scope_classification": "required_in_scope",
      "title": "short title",
      "description": "short explanation",
      "evidence": ["path#L1"]
    }
  ]
}
```

Also write:
- `APPROVE`, `REVISE`, or `BLOCK` to the `design_review_decision` output-contract path
- the unresolved high count integer to the `unresolved_high_count` output-contract path
- the unresolved medium count integer to the `unresolved_medium_count` output-contract path

Use `BLOCK` only when the study should not proceed to planning without human scope clarification or a materially different design.
Approve only if there are no unresolved high findings and the design is ready for planning.
