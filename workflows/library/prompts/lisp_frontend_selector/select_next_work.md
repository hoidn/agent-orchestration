Read the consumed steering, full design, MVP design, backlog manifest, progress
ledger, and run state before acting.

Select exactly one next Lisp frontend implementation work item.

Use the full design as the target contract. Use the MVP design only as
historical context for the initial proof slice and already-completed MVP work.
Do not return `DONE` just because the MVP is complete.

Decision rules:

- Return `SELECT_BACKLOG_ITEM` when an active backlog item directly covers the
  next useful Lisp frontend full-design implementation task.
- Return `DRAFT_DESIGN_GAP` when no active backlog item is the right next task
  and the next needed unit is either an unimplemented full-design component or a
  bounded refactor needed before further feature expansion.
- Return `DONE` only when there are no active backlog items and no unimplemented
  full-design gaps remain.
- Return `BLOCKED` only when full-design work remains but the available docs are
  insufficient or contradictory.

Refactoring may be selected when it is the best next step toward completing the
full design, but only as a bounded expansion-enabling pass.

Do not select refactoring twice in a row. If the most recent completed unit was
refactoring, select feature work, `DONE`, or `BLOCKED`.

A refactor must leave the frontend ready for the next feature slice. If it
changes current relied-upon architecture/design docs, update those docs in
scope. Do not rewrite historical per-gap implementation architecture docs merely
to match the refactor.

Before returning `DONE`, compare the full design against durable repo evidence:
source, docs, fixtures, tests, ledgers, and run state. Evaluate obligations from
the full design itself, not from the set of existing backlog items or design-gap
directories. A missing work item or design-gap directory is not evidence that an
obligation is complete.

For any full-design obligation, return `DRAFT_DESIGN_GAP` unless the available
evidence shows a coherent completed treatment of that obligation, or the full
design explicitly marks it out of scope. Do not require every obligation to have
the same evidence shape; use the evidence that is appropriate to the obligation.
When the ledger says complete but source/docs/fixtures/tests do not support that
claim, prefer `DRAFT_DESIGN_GAP` over `DONE`.

Make only this step's local selection judgment and explain it. Do not edit
files, move backlog items, or draft architecture content. For design gaps,
identify one bounded feature or refactoring unit for the architect step to turn
into an implementation architecture.

Write the output bundle JSON to the output-contract path.

Backlog selection:

```json
{
  "selection_status": "SELECT_BACKLOG_ITEM",
  "selected_item_id": "2026-05-18-existing-parser-item",
  "selected_item_path": "docs/backlog/active/2026-05-18-existing-parser-item.md",
  "selection_rationale": "short reason"
}
```

Design gap:

```json
{
  "selection_status": "DRAFT_DESIGN_GAP",
  "design_gap_id": "parser-syntax",
  "source_design_path": "docs/design/workflow_lisp_frontend_specification.md",
  "source_sections": ["Full-design section name"],
  "missing_component": "Unimplemented full-design component or bounded refactoring need",
  "proposed_scope": "Draft one bounded feature or refactoring implementation architecture only.",
  "selection_rationale": "short reason"
}
```

Done:

```json
{
  "selection_status": "DONE",
  "selection_rationale": "No active backlog items or full-design gaps remain."
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
