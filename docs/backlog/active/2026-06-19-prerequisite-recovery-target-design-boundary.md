# Backlog Item: Separate Prerequisite Recovery From Target Design Revision

- Status: active
- Created on: 2026-06-19
- Priority: P1
- Plan: none yet

## Problem

The Lisp frontend design-delta drain currently blurs two different recovery
routes:

- `TARGET_DESIGN_REVISION_REQUIRED`: the durable target design is wrong,
  incomplete, or internally inconsistent and needs a design-document edit.
- `PREREQUISITE_GAP_REQUIRED`: the selected gap cannot proceed until another
  bounded prerequisite gap is drafted, selected, or completed first.

The classifier prompt describes `PREREQUISITE_GAP_REQUIRED` as a missing
prerequisite capability or gap. But the recovery revision prompt currently says
that this route should update the consumed target design enough to add or
decompose the prerequisite gap. The YAML workflow also routes
`PREREQUISITE_GAP_REQUIRED` through `ReviseBlockedDesignGap` and the blocked
target-design revision review path.

That makes sequencing work look like architecture work. It risks polluting
target design documents with transient backlog state, stale run assumptions, or
work-order notes that belong in gap/backlog routing surfaces.

## Desired Outcome

Keep prerequisite recovery as a sequencing/decomposition route by default.

For `PREREQUISITE_GAP_REQUIRED`, the workflow should normally:

- leave the target design and baseline design unchanged;
- create or update the prerequisite gap/backlog/routing surface needed for
  selection;
- mark the current blocked gap as waiting for that prerequisite or retryable
  after it lands;
- update the current gap plan only when needed to express the prerequisite
  dependency; and
- preserve run-state evidence explaining why the prerequisite was introduced.

The workflow should edit the target design only when the blocker reveals a
durable target-design contract gap. In that case the recovery route should be
`TARGET_DESIGN_REVISION_REQUIRED`, or the prerequisite route should explicitly
escalate to that route with evidence.

## Suggested Implementation Direction

1. Update the recovery prompts so `PREREQUISITE_GAP_REQUIRED` no longer
   authorizes target-design edits by default.
2. Split the YAML route so prerequisite recovery does not reuse the blocked
   target-design revision/review lane.
3. Add a prerequisite recovery step that drafts or registers a prerequisite gap,
   or emits a structured request for the selector/backlog updater to do so.
4. Keep `GAP_DESIGN_REVISION_REQUIRED` focused on the current gap architecture
   and execution plan.
5. Keep `TARGET_DESIGN_REVISION_REQUIRED` focused on durable target design
   contract changes.
6. Add compatibility handling for existing run states that already classified a
   blocker as `PREREQUISITE_GAP_REQUIRED`.

## Acceptance Criteria

- A `PREREQUISITE_GAP_REQUIRED` blocker produces a prerequisite gap, backlog
  entry, routing update, or structured prerequisite request without modifying
  the target design.
- Target design edits happen only for `TARGET_DESIGN_REVISION_REQUIRED` or for
  an explicit escalation from prerequisite recovery to target-design revision.
- Recovery review artifacts name the route accurately and do not review a
  prerequisite-only change as a target-design revision.
- Existing blocked-recovery run state can resume or fail with an actionable
  compatibility diagnostic; it must not crash from checksum or missing-field
  drift.
- Tests or smoke checks cover all three nonterminal recovery routes:
  target-design revision, gap-design revision, and prerequisite-gap recovery.

## Non-Goals

- Do not redesign the whole design-delta drain.
- Do not change the meaning of the target design merely to record work order.
- Do not make prerequisite recovery terminal unless the prerequisite truly
  requires user intervention or external authority.
- Do not weaken the existing review gate for actual target-design revisions.

## Related Context

- `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`
- `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_prior_blocked_design_gap.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/backlog/active/2026-06-05-workflow-lisp-design-delta-drain-orc-migration.md`
