Review the consumed workflow implementation plan.

This is a review-only step. Do not edit files, implement the plan, update
state, or rewrite the plan.

Judge whether the plan is likely to improve workflow behavior without adding
unnecessary brittleness, slowdown, or churn. Focus on the behavior the workflow
will exhibit after the plan lands.

Approve only if all of these are true:

- the plan fixes a real workflow behavior problem, not just stale reports,
  manifests, inventories, labels, or closeout evidence;
- deterministic routing, filtering, parsing, counters, and state updates stay
  in workflow/runtime/script code rather than provider judgment;
- provider prompts keep only local judgment work and are not asked to manage
  loops, dependency graphs, ledgers, or recovery mechanics;
- generated run history such as `state/`, `artifacts/`, and `.orchestrate/`
  is not treated as source authority unless the selected task is specifically
  about generated run outputs;
- the plan preserves useful progress on unrelated eligible work instead of
  globally blocking for a defect attached only to hidden or ineligible work;
- missing or contradictory dependency state fails with a precise deterministic
  reason instead of causing provider improvisation or automatic work creation;
- verification is narrow enough to catch regressions from this plan without
  turning broad evidence refreshes into implementation work.

Return `REVISE` for any concrete issue that would make the workflow more
myopic, brittle, slow, or bookkeeping-driven. Return `BLOCK` only when the plan
cannot be safely repaired from the consumed inputs.

When reviewing, prefer these questions over checklist expansion:

1. What behavior changes?
2. Which bad choices become impossible?
3. What new failure mode or stall path is introduced?
4. Does the plan keep useful work moving when unrelated generated-state or
   dependency defects exist?
5. Are broad checks included only because touched code needs them, or because
   the plan is trying to prove unrelated evidence?

Write the review as JSON to the output-contract bundle path:

```json
{
  "decision": "APPROVE",
  "summary": "short behavior-focused summary",
  "unresolved_high_count": 0,
  "unresolved_medium_count": 0,
  "findings": [
    {
      "id": "PLAN-H1",
      "severity": "high",
      "title": "short title",
      "description": "specific behavior risk or missing plan repair",
      "evidence": ["path:line or short quoted plan phrase"]
    }
  ]
}
```

Allowed decisions are `APPROVE`, `REVISE`, and `BLOCK`.
