Read the steering, target design, command-adapter contract, typed design-gap
subject record, architecture targets, and drafted implementation architecture
before acting. The baseline design path is available as the accepted baseline
design contract.

Review whether the gap design is consistent with the target design.
Reject it if it changes, weakens, bypasses, or leaves ambiguous any
target-design requirement that the implementation could affect.
Reject it if it turns the architecture into an execution plan: task order,
command-order checklists, and workflow recovery procedure belong outside
`implementation_architecture.md`.
Also reject requirements or check commands not traceable to the target design
or to verified current behavior.

The baseline design is the accepted baseline design contract. The target design
is the active contract for this review.

Approve only when the drafted implementation architecture can be implemented
without changing or weakening the target-design contract. Return `REVISE` when
the draft can likely be corrected in place. Return `BLOCKED` when the selected
gap cannot be safely architected without a missing prerequisite or user
decision.

Write the review decision bundle to the output-contract path using this shape:

```json
{
  "review_decision": "APPROVE | REVISE | BLOCKED",
  "reason": "short reason"
}
```
