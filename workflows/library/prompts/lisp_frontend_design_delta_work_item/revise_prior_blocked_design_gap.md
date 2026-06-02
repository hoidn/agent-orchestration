You are revising the appropriate design surface because a prior run left a
design gap blocked during implementation.

Read the consumed target design, baseline design, prior blocked recovery bundle,
recovery classification bundle, blocker progress report, and any consumed gap
architecture or execution plan.

Use `blocked_recovery_route` from the recovery classification bundle as the
authority for what may be edited:

- `TARGET_DESIGN_REVISION_REQUIRED`: update only the consumed target design
  document. Keep the baseline design unchanged.
- `GAP_DESIGN_REVISION_REQUIRED`: update the consumed gap
  `implementation_architecture.md` and, if needed, its `execution_plan.md`.
  Keep the target and baseline design documents unchanged.

Make the smallest principled design change that resolves the blocker and gives a
future plan/implementation pass a coherent contract to use. If the blocker
cannot be resolved by changing the allowed editable surface, write a revision
report explaining why and set the decision to `BLOCKED`.

Write:
- the updated allowed design surface at its consumed path;
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
