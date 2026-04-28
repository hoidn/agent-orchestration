Major-project tranche plan review additions:
- Read the consumed `upstream_escalation_context` artifact. If it is active, reconcile the plan against that evidence.
- Allowed decisions are `APPROVE`, `REVISE`, `ESCALATE_REDESIGN`, and `BLOCK`.
- Use `ESCALATE_REDESIGN` when the approved design does not support an executable plan for this tranche, including on the first pass.
- Use `BLOCK` only for missing authority, unavailable external prerequisites, or contradictions that redesign cannot safely repair from the available artifacts.
- Write a plan escalation context JSON to the target named by the `plan_escalation_context_path` output. It may be inactive for `APPROVE` or `REVISE`, but it must exist.

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `scope_boundary`, `plan`, and `open_findings` artifacts before acting.

First, review the current plan from scratch.
Check that the plan faithfully carries the consumed design and roadmap-authoritative `scope_boundary` into bounded executable work. Material design requirements and scope-boundary deliverables should appear as concrete tasks unless the scope boundary itself authorizes the work as a non-goal or deferred successor.
Check scope accountability before approval. The plan may sequence work inside the selected tranche, but it may not reduce, split, recharter, or move selected-tranche scope. Reject underscoped plans that defer material design or scope-boundary requirements without roadmap-level authority from `scope_boundary`. Reject overbroad plans that collapse separable phases or responsibilities into one hard-to-review implementation unit instead of sequencing them. If the selected tranche boundary itself must change, do not approve a local slice; require redesign or roadmap revision through the appropriate escalation path.
Reject plans that put dependent work too early. If a later task relies on a behavior, interface, data shape, integration, or user-visible result, the plan must first include the task that makes that result true and the check that proves it.
Reject plans that collapse the design's component boundaries, interfaces, invariants, or durable artifact contracts into undifferentiated implementation work instead of assigning tasks along those boundaries.
Reject plans that ignore or weaken design or roadmap layout and ownership decisions, or change locations or unit boundaries without explicit rationale.
Reject plans that need an Implementation Architecture section because correctness or maintainability depends on a boundary decision, but do not define implementable units and owned boundaries. Boundary decisions include component or file ownership, API or command surface, data or artifact contract, authored-vs-derived split, dependency direction, compatibility or migration boundary, and future consumer contract. A single-unit plan is acceptable only when the plan explicitly says no such boundary decision is needed.
Reject plans whose task list is dominated by exhaustive case matrices unless those matrices are part of the current-scope contract.
Reject plans that blur authored and derived artifacts or introduce reusable code without a maintainability rationale.
Check verification gates for practical executability and claim fit. Required commands must exist or be added by the plan before they are used as gates; environment-dependent commands must name their prerequisite or fallback; broad regression sweeps must say how pre-existing failures are separated from regressions caused by this work; and evidence gates must be strong enough for the claim being made.
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
- `APPROVE`, `REVISE`, `ESCALATE_REDESIGN`, or `BLOCK` to the `plan_review_decision` path specified in the Output Contract
- the unresolved high count integer to the `unresolved_high_count` path specified in the Output Contract
- the unresolved medium count integer to the `unresolved_medium_count` path specified in the Output Contract

Approve only if there are no unresolved high findings and the plan is ready to execute without inventing architecture, silently dropping material design or scope-boundary requirements, or deferring required work without roadmap-level authority.
