Read the listed steering, target design, baseline design, command-adapter
contract, progress ledger, typed design-gap subject record, architecture
targets, existing implementation architecture index, and drafted
implementation architecture before acting.

Review whether the gap design is consistent with the target design.
Reject it if it changes, weakens, bypasses, or leaves ambiguous any
target-design requirement that the implementation could affect.
Reject it if it turns the architecture into an execution plan: task order,
command-order checklists, workflow recovery procedure, and manifest/report
refresh chores belong outside `implementation_architecture.md`.
Reject it if its only material deliverable is refreshing derived reports,
inventories, manifests, conformance packages, labels, or closeout evidence
instead of changing source/runtime behavior, authoring surface, or contracts.

The baseline design is compatibility context. The target design is the active
contract for this review.

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
