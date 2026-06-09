# Parent Drain `.orc` Readiness Blockers

Status: active blocker record
Updated: 2026-06-09

This record explains why Task 9 in
`docs/plans/2026-06-09-lisp-frontend-design-delta-drain-orc-migration-plan.md`
should not start by writing a parent drain `.orc` wrapper.

The parent drain candidate must call selector, design-gap architect, work-item,
plan, and implementation modules while preserving blocked recovery, drain-state
mutation, resource movement, resume identity, and public YAML boundary parity.
Current leaf candidates are useful migration evidence, but they are not yet
complete callable substitutes for the YAML family.

## Blocking Prerequisites

1. Selector bundle publication is still a bridge.

   `selector.orc` currently compiles the provider decision as typed state, but
   it does not yet replace `PublishSelectionBundle` or preserve the YAML
   `selection_bundle_path` public output. The parent drain needs a structured
   selection bundle to route normal work, gap drafting, prerequisite work, and
   terminal done/blocked states.

2. Design-gap target and validation paths are still bridge work.

   `design_gap_architect.orc` currently compiles draft and validation leaves,
   but target derivation, architecture-index construction, architecture review
   and revise, and work-item bundle publication are not yet parent-callable
   parity surfaces.

3. Implementation phase composition is split.

   `implementation_phase.orc` currently exposes execute-attempt and
   completed-review leaves. The full YAML phase cannot yet be expressed by
   placing the stdlib review/revise loop inside the `COMPLETED` arm of an
   implementation-attempt `match`; shared validation rejects nested structured
   `repeat_until` and `match` steps under that branch.

4. Work-item orchestration is incomplete.

   `work_item.orc` currently compiles terminal-classification and
   blocked-recovery-classification leaves. It does not yet resolve selected
   work-item inputs, call the plan and implementation candidates, select
   recovery routes, record terminal outcomes, or update run state.

5. Run-state mutation and resource transitions are not native yet.

   Several YAML helper scripts update run state, recovery state, prerequisite
   edges, summary pointers, and drain status. A parent `.orc` candidate must not
   hide those semantics in a wrapper. They need typed projections,
   resource-transition ownership, or certified adapter boundaries.

6. Public boundary parity is not ready.

   The YAML parent exposes many `state/` paths and artifact root defaults. The
   first `.orc` leaf candidates intentionally avoid raw public low-level state
   paths. A parent candidate must either preserve the YAML public boundary via
   accepted compatibility adapters or use an explicitly accepted private
   context bridge with parity evidence.

## Required Fix Before Task 9

Before a parent drain `.orc` candidate is implementation-ready, complete one of
these routes:

- implement the missing typed/private context bridges and certified adapters so
  selector, architect, work-item, plan, and implementation modules are
  parent-callable without exposing raw generated state paths; or
- fix the frontend/shared-validation composition limitation for nested
  structured control so the implementation phase and work-item can compose
  typed branches directly; or
- explicitly accept a staged interop wrapper as a non-promotable exploratory
  checkpoint, with the migration record stating that it is not a principled
  family migration and cannot contribute to `--require-promotable`.

Until one of those routes lands, Task 9 remains blocked for principled
implementation. Continuing with a parent wrapper would recreate YAML-shaped
Lisp and obscure the remaining semantic work.
