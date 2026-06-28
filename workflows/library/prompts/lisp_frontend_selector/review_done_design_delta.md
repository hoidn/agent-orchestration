Read the steering file, target design, baseline design, current-state inventory
when provided, backlog manifest, progress ledger, run state, and selector DONE
bundle before acting.

Review whether the selector's DONE candidate is actually justified for the
target design.

Use the target design as the active implementation target. Use the baseline
design as the compatibility contract that the target work must not violate.
Evaluate obligations from the target design itself, not from the presence or
absence of existing backlog items or design-gap directories.

Return `APPROVE_DONE` only when durable repo evidence shows the target design
has no remaining bounded implementation gaps. Use consumed current-state
inventory as evidence, not as a substitute for checking the target design
against the checkout. Durable evidence may include source, docs, fixtures,
tests, ledgers, run state, parity reports, reconciled inventories, and accepted
waivers. Do not require every obligation to have the same evidence shape; use
the evidence appropriate to that obligation.
Before approving, directly compare the target design's success criteria and
prohibited/final-shape clauses against the current source tree; do not approve
solely because run state, inventory, parity, or focused tests show no gaps.

Return `REJECT_DONE` when one next bounded target design gap remains. On
rejection, identify exactly one gap for the existing design-gap architect step
to turn into an implementation architecture.

If any consumed current-state source marks a target-design obligation
unresolved, it continues to block `DONE` until durable evidence shows it is
completed, superseded, explicitly deferred, or otherwise resolved by higher
authority.

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
