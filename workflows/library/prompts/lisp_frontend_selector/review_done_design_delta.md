Read the steering file, target design, compact selector manifest, and selector DONE
bundle before acting. Use the baseline design only as a compatibility
background when needed.
Treat `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json`
as the authority for post-WCC current-state inventory and DONE eligibility when
it is provided as an input.

Review whether the selector's DONE candidate is actually justified for the
target design.

Use the target design as the active implementation target. Use the baseline
design as the compatibility contract that the target work must not violate.
Evaluate current source/runtime/authoring behavior against the target design.
Use generated artifacts only when they are consumed inputs or required output
targets for this task.

Return `APPROVE_DONE` only when current source/runtime/authoring behavior has
no remaining bounded target-design gap. Before approving, compare the target
design's success criteria and prohibited/final-shape clauses against the current
source tree.

Return `REJECT_DONE` when one next bounded source/runtime/authoring gap remains.
On rejection, identify exactly one gap for the existing design-gap architect
step to turn into an implementation architecture.

Before rejecting DONE, check the manifest's attempt history; do not re-propose a design gap that is already completed or blocked.

Make only this review judgment. Do not edit files, move backlog items, update
ledgers, or manage the drain loop.

Write the output bundle JSON to the output-contract path.

Approved:

```json
{
  "done_decision": "APPROVE_DONE",
  "review_rationale": "short reason"
}
```

Rejected:

```json
{
  "done_decision": "REJECT_DONE",
  "review_rationale": "short reason",
  "design_gap_id": "<design_gap_id>",
  "source_design_path": "<target_design_path>",
  "source_sections": ["Target design section name"],
  "missing_component": "Under-specified or unimplemented target design unit",
  "proposed_scope": "Draft one bounded implementation architecture only."
}
```
