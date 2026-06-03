Read the consumed steering, target design, baseline design, backlog manifest,
progress ledger, and run state before acting.

Select exactly one next implementation unit for the target design delta.

Use the target design as the active implementation target. Use the baseline
design as the parent compatibility contract that the target work must not
violate.

Decision rules:

- Return `SELECT_BACKLOG_ITEM` when an active backlog item directly covers the
  next useful target-delta implementation task.
- Return `DRAFT_DESIGN_GAP` when no active backlog item is the right next task
  and the target delta still has an under-specified or unimplemented bounded
  unit.
- Return `DONE` only when the target delta is implemented and no target-delta
  gaps remain.
- Return `BLOCKED` only when target-delta work remains but the target and
  baseline docs are insufficient or contradictory.

Do not select unrelated baseline/frontend work unless it is required to satisfy
the target delta without violating the baseline design.

If run state contains a blocked design gap with
`recovery_status: PREREQUISITE_WORK_PENDING`, select or draft the prerequisite
target-delta work needed to unblock that gap before unrelated target-delta work.
For that prerequisite-recovery case, include `prerequisite_relation` in the
selected or drafted output. The relation should name how the selected unit
unblocks the original blocked design gap; use `BLOCKED` instead when no safe
prerequisite can be selected.

Refactoring may be selected when it is the best next step toward completing the
target delta, but only as a bounded expansion-enabling pass.

Do not select refactoring twice in a row. If the most recent completed unit was
refactoring, select target-delta feature work, `DONE`, or `BLOCKED`.

A refactor must leave the frontend ready for the next target-delta feature
slice. If it changes current relied-upon architecture/design docs, update those
docs in scope. Do not rewrite historical per-gap implementation architecture
docs merely to match the refactor.

Before returning `DONE`, compare the target delta against durable repo evidence:
source, docs, fixtures, tests, ledgers, and run state. Evaluate obligations from
the target design itself, not from the set of existing backlog items or
design-gap directories. A missing work item or design-gap directory is not
evidence that a target-delta obligation is complete.

For any target-delta obligation, return `DRAFT_DESIGN_GAP` unless the available
evidence shows a coherent completed treatment of that obligation, or the target
design explicitly marks it out of scope. Do not require every obligation to have
the same evidence shape; use the evidence that is appropriate to the obligation.
When the ledger says complete but source/docs/fixtures/tests do not support that
claim, prefer `DRAFT_DESIGN_GAP` over `DONE`.

Make only this step's local selection judgment and explain it. Do not edit
files, move backlog items, or draft architecture content. For design gaps,
identify one bounded unit for the architect step to turn into an implementation
architecture.

Write the output bundle JSON to the output-contract path.

Backlog selection:

```json
{
  "selection_status": "SELECT_BACKLOG_ITEM",
  "selected_item_id": "<selected_item_id>",
  "selected_item_path": "<selected_item_path>",
  "prerequisite_relation": "only when selecting prerequisite recovery work",
  "selection_rationale": "short reason"
}
```

Design gap:

```json
{
  "selection_status": "DRAFT_DESIGN_GAP",
  "design_gap_id": "<design_gap_id>",
  "source_design_path": "<target_design_path>",
  "source_sections": ["Target-delta section name"],
  "missing_component": "Under-specified or unimplemented target-delta unit",
  "proposed_scope": "Draft one bounded implementation architecture only.",
  "prerequisite_relation": "only when drafting prerequisite recovery work",
  "selection_rationale": "short reason"
}
```

Done:

```json
{
  "selection_status": "DONE",
  "selection_rationale": "The target delta is implemented and no target-delta gaps remain."
}
```

Blocked:

```json
{
  "selection_status": "BLOCKED",
  "selection_rationale": "short reason",
  "blocking_reasons": ["short reason"]
}
```
