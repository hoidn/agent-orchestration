Read the consumed steering, target design, baseline design, current-state
inventory when provided, backlog manifest, progress ledger, and run state
before acting.

Select exactly one next implementation unit for the target design.

Use the target design as the active implementation target. Use the baseline
design as the parent compatibility contract that the target work must not
violate.

Decision rules:

- Return `SELECT_BACKLOG_ITEM` when an active backlog item directly covers the
  next useful target design implementation task.
- Return `DRAFT_DESIGN_GAP` when no active backlog item is the right next task
  and the target design still has an under-specified or unimplemented bounded
  unit.
- Return `DONE` only when the target design is implemented and no target design
  gaps remain.
- Return `BLOCKED` only when target design work remains but the target and
  baseline docs are insufficient or contradictory.

Do not select unrelated baseline/frontend work unless it is required to satisfy
the target design without violating the baseline design.

If run state contains a blocked design gap with
`recovery_status: PREREQUISITE_WORK_PENDING`, select or draft the prerequisite
target design work needed to unblock that gap before unrelated target design work.
If pre-selection metadata says `recovery_pointer_status: WAITING`, select the
work named by `waiting_on_work_id` / `waiting_on_work_source` and do not select
other work first. If it says `READY_TO_RETRY`, retry the blocked work named by
`retry_target_id` / `retry_target_source`. If it says `INVALID`, return
`BLOCKED`. For prerequisite recovery, include `prerequisite_relation` only as a
short explanation.
If the pending prerequisite already has durable completion evidence, do not
draft another prerequisite; select the original gap for retry or report BLOCKED
with stale prerequisite state as the reason.

Refactoring may be selected when it is the best next step toward completing the
target design, but only as a bounded expansion-enabling pass.
Do not select work that only preserves a temporary workaround. Select it only if
it removes the workaround, confines it to an external boundary, or removes a
specific blocker to deleting it.
Do not select or draft implementation work only to refresh reports, summaries,
manifests, inventories, labels, or other derived views. Treat stale derived
views as closeout follow-up unless the view is the requested product behavior,
a stable input to normal runtime/product behavior, or evidence that implemented
behavior is wrong. Acceptance, progress, review, promotion, conformance, and
closeout evidence are not implementation work just because a design mentions
them.
Select implementation work only for source/runtime behavior, authoring surface,
or contract defects. If the only remaining issue is stale closeout evidence,
do not turn it into another implementation gap; return `BLOCKED` with stale
closeout/gate drift as the reason.

Do not select refactoring twice in a row. If the most recent completed unit was
refactoring, select target design feature work, `DONE`, or `BLOCKED`.

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
  "source_sections": ["Target design section name"],
  "missing_component": "Under-specified or unimplemented target design unit",
  "proposed_scope": "Draft one bounded implementation architecture only.",
  "prerequisite_relation": "only when drafting prerequisite recovery work",
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
