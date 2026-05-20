Read the consumed steering, full design, MVP design, backlog manifest, progress
ledger, and run state before acting.

Select exactly one next Lisp frontend MVP implementation work item.

Use the MVP design as the target contract. Use the full design only as
background for terminology, boundaries, and later compatibility. Do not select
full-design-only work unless the MVP design requires it.

Decision rules:

- Return `SELECT_BACKLOG_ITEM` when an active backlog item directly covers the
  next useful Lisp frontend MVP implementation task.
- Return `DRAFT_DESIGN_GAP` when no active backlog item is the right next task
  but the MVP design clearly contains an unimplemented component that should be
  turned into an implementation architecture.
- Return `DONE` only when there are no active backlog items and no unimplemented
  MVP design gaps remain.
- Return `BLOCKED` only when MVP work remains but the available docs are
  insufficient or contradictory.

Make only this step's local selection judgment and explain it. Do not edit
files, move backlog items, or draft architecture content. For design gaps,
identify one bounded MVP component for the architect step to turn into an
implementation architecture.

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
  "source_design_path": "docs/design/workflow_lisp_frontend_mvp_specification.md",
  "source_sections": ["Stage 1: Frontend Core Without Workflow Execution"],
  "missing_component": "Parser and syntax objects",
  "proposed_scope": "Draft parser and syntax-object implementation architecture only.",
  "selection_rationale": "short reason"
}
```

Done:

```json
{
  "selection_status": "DONE",
  "selection_rationale": "No active backlog items or design gaps remain."
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
