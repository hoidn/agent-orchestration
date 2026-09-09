Read `request.subject`: the steering, target design, baseline design,
selector manifest, progress ledger, and existing architecture index. Use the
manifest and ledger, including `attempt_history_summary` when present, to avoid
repeating failed or completed attempts. Use the target design, current
source/runtime behavior, and manifest to determine remaining work and DONE
eligibility.

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

Write the `SelectorPublicResult` JSON bundle required by the output contract
at its exact runtime-bound path. Set `selection_bundle_path` to that same
path. Populate `work_item_bootstrap` from the manifest-backed work-item context:
`work_item_source`, `work_item_id`, `plan_target_path`,
`check_commands: {"commands": [...]}`, and `architecture_path`.
Keep `selection_status` and the four routing booleans consistent:

| selection_status | is_selected | is_design_gap | is_done | is_blocked |
| --- | --- | --- | --- | --- |
| SELECT_BACKLOG_ITEM | true | false | false | false |
| DRAFT_DESIGN_GAP | false | true | false | false |
| DONE | false | false | true | false |
| BLOCKED | false | false | false | true |

Set `blocked_reason` to the concrete reason for `BLOCKED`, or an empty string
otherwise. For inactive bootstrap fields, use only existing manifest-backed
context; do not invent an item or make a terminal result select work merely to
populate the record. The output contract still requires those fields for
terminal results.
