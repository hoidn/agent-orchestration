use receiving-code-review to address the feedback

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, and `plan_review_report` artifacts before acting.

Update the current plan in place at the workspace-relative path stored in `state/plan_path.txt`.
Address every finding whose status is:
- `STILL_OPEN`
- `NEW`
- `SPLIT`

Do not spend time on findings marked `RESOLVED`.
If a finding is `SUPERSEDED`, address the replacing finding instead.

Write JSON to the workspace-relative path stored in `state/plan_resolution_report_path.txt` using this shape:

```json
{
  "addressed": [
    {
      "id": "PLAN-H1",
      "change_summary": "what changed in the plan"
    }
  ],
  "not_addressed": [
    {
      "id": "PLAN-M2",
      "reason": "why it remains open"
    }
  ]
}
```
