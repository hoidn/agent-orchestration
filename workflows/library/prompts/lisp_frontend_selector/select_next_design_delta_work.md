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

Make only this step's local selection judgment and explain it. Do not edit
files, move backlog items, or draft architecture content. For design gaps,
identify one bounded unit for the architect step to turn into an implementation
architecture.

Write the output bundle JSON to the output-contract path.

Backlog selection:

```json
{
  "selection_status": "SELECT_BACKLOG_ITEM",
  "selected_item_id": "2026-05-18-existing-procref-item",
  "selected_item_path": "docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION/2026-05-18-existing-procref-item.md",
  "selection_rationale": "short reason"
}
```

Design gap:

```json
{
  "selection_status": "DRAFT_DESIGN_GAP",
  "design_gap_id": "procref-static-surface-and-resolution",
  "source_design_path": "docs/design/workflow_lisp_proc_refs_partial_application.md",
  "source_sections": ["Target-delta section name"],
  "missing_component": "Under-specified or unimplemented target-delta unit",
  "proposed_scope": "Draft one bounded implementation architecture only.",
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
