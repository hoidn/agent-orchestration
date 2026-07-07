Read the consumed steering, target design, and selector manifest before acting.
Use `attempt_history_summary` when present to avoid repeating failed or
completed attempts.
Treat `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json`
as the authority for post-WCC current-state inventory and DONE eligibility when
it is provided as an input.

Select exactly one next implementation unit for the target design.

Use the target design as the active implementation target.

Decision rules:

- Return `SELECT_BACKLOG_ITEM` when an active backlog item directly covers the
  next useful target design implementation task.
- Return `DRAFT_DESIGN_GAP` only for a design gap listed as eligible in the
  manifest.
- Return `DONE` only when the target design is implemented and no target design
  gaps remain.
- Return `BLOCKED` only when target design work remains but the target and
  baseline docs are insufficient or contradictory.

Do not select unrelated baseline/frontend work unless it is required to satisfy
the target design without violating the baseline design.

Refactoring may be selected when it is the best next step toward completing the
target design, but only as a bounded expansion-enabling pass.
Select implementation work for source/runtime behavior, authoring surface, or
contract defects required by the target design. If no such target-design work
can be identified from the available inputs, return `DONE` or `BLOCKED` with a
short reason.

A refactor must leave the frontend ready for the next target design feature
slice. If it changes current relied-upon architecture/design docs, update those
docs in scope. Do not rewrite historical per-gap implementation architecture
docs merely to match the refactor.

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
  "selection_rationale": "short reason"
}
```

Design gap:

```json
{
  "selection_status": "DRAFT_DESIGN_GAP",
  "design_gap_id": "<design_gap_id>",
  "source_design_path": "<target_design_path>",
  "source_sections": ["Target design section name"],
  "missing_component": "Under-specified or unimplemented target design unit",
  "proposed_scope": "Draft one bounded implementation architecture only.",
  "selection_rationale": "short reason"
}
```

Done:

```json
{
  "selection_status": "DONE",
  "selection_rationale": "The target design is implemented and no target design gaps remain."
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
