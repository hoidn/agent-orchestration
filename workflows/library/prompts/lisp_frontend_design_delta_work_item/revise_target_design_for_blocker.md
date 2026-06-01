You are revising the target design document because implementation found a
blocking contract or roadmap conflict.

Read the consumed target design, baseline design, approved plan, and blocker
progress report. Update only the target design document. Keep the baseline
design unchanged.

Make the smallest principled design change that resolves the blocker. If the
blocker cannot be resolved by changing the target design, write a revision
report explaining why and set the decision to `BLOCKED`.

Write:
- the updated target design at the consumed target design path;
- a JSON revision report at the required output path.

The report JSON must contain this shape:

```json
{
  "design_revision_decision": "REVISED | BLOCKED",
  "summary": "",
  "changed_sections": [],
  "blocker_class": "",
  "reason": ""
}
```
