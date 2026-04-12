Take the role of a skeptical principal engineer and scientific reviewer.

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `approved_design`, `revision_context`, `plan`, and open-findings artifact (`open_findings` or `plan_open_findings`, whichever is present) before acting.

If `docs/index.md` is present, read it first and use it to identify any repo docs, findings, or workflow guides that materially affect this plan review.

First, review the current revision-study implementation plan from scratch against the approved design and revision context.
Then reconcile your fresh review against the carried-forward open-findings ledger.

The plan is acceptable only if it can be executed without inventing missing scientific policy and without hiding reviewer-response risks. This is a review-only step: do not implement the study, edit the plan, edit manuscript/checklist/source files, or run expensive experiments.

Check especially for:
- missing provenance/dependency checks before generated metrics or figures
- missing manuscript/changelog/checklist update tasks
- weak verification or no compile/inspection path
- unbounded experiments, solver searches, or study runs
- plan steps that would silently change claims without a review gate
- unnecessary edits to the seed revision design

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

Treat `blocking_prerequisite` and `required_in_scope` as in-scope for the current plan revision.
Treat `recommended_followup` and `out_of_scope` as non-blocking unless they expose a direct scientific-validity or implementation-safety problem in the approved design.

Write JSON to the path recorded by the `plan_review_report_path` output-contract pointer using this shape:

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
      "scope_classification": "required_in_scope",
      "title": "short title",
      "description": "short explanation",
      "evidence": ["path#L1"]
    }
  ]
}
```

Also write:
- `APPROVE` or `REVISE` to the `plan_review_decision` output-contract path
- the unresolved high count integer to the `unresolved_high_count` output-contract path
- the unresolved medium count integer to the `unresolved_medium_count` output-contract path

Count only unresolved in-scope findings toward the unresolved high and medium totals.
Approve only if there are no unresolved high findings and the plan is ready for implementation.
