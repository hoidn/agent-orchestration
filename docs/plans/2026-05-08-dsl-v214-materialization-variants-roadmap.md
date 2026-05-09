# DSL v2.14 Materialization And Variant Semantics Roadmap

This roadmap is the local NeurIPS-style execution authority for the v2.14
materialization and variant-output work. The detailed design authority is
`docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`.

## Current Gate

- Gate id: `dsl-v214-phase1-runtime`
- Selectable phase prefix: `phase-1-dsl-v214-runtime`
- Blocked future prefixes:
  - `phase-2-dsl-v214-neurips-stack`

The current gate advances to Phase 1 after the Phase 0 oracle item has produced
reviewed implementation evidence. Phase 2 remains blocked until Phase 1 lands.

## Phase 0: phase-0-dsl-v214-oracle

Objective: freeze existing behavior before changing DSL semantics.

Backlog authority:

- `docs/backlog/in_progress/2026-05-08-dsl-v214-phase0-oracle.md`

Required outcomes:

- Draft, non-normative v2.14 design and behavior-matrix documents.
- Primitive fixtures that emulate the future materialization, snapshot, and
  variant-selection behavior using currently supported DSL surfaces.
- Minimal NeurIPS-style fixtures with steering, design, roadmap, backlog,
  queue, and run-state shapes.
- A fake provider that can deterministically produce completed, blocked,
  ambiguous, and missing-output scenarios.
- A golden observation normalizer that removes volatile run data and preserves
  final outputs, artifact values, selected variants, file hashes, queue state,
  domain-state summaries, and failure classes.
- Regression tests that capture current behavior without enabling public
  `version: "2.14"` support.

Exit criteria:

- Phase 0 tests pass with no network or provider secrets.
- Normal CLI and loader paths still reject public `version: "2.14"`.
- The oracle can drive both primitive and minimal NeurIPS-style scenarios with
  fake providers.

## Phase 1: phase-1-dsl-v214-runtime

Objective: implement the narrow v2.14 semantic tranche after Phase 0 is stable.

Backlog authority:

- `docs/backlog/active/2026-05-09-output-bundle-variant-surface-review.md`
- `docs/backlog/active/2026-05-09-dsl-v214-pointer-authority-clarification.md`
- `docs/backlog/active/2026-05-09-roadmap-gate-empty-active-gap.md`
- `docs/backlog/in_progress/2026-05-09-dsl-v214-runtime-semantics.md`

Scope:

- `materialize_artifacts`
- `pre_snapshot`
- `variant_output`
- `select_variant_output`
- `requires_variant`
- match-based variant proof
- snapshot-reference taxonomy
- variant field availability
- strict relpath pointer authority
- contract inheritance and refinement validation
- exact error taxonomy and runtime integration points

Gate:

- Do not start until Phase 0 is complete.
- Do not expose public `version: "2.14"` until loader, runtime, docs, and tests
  land together.

## Phase 2: phase-2-dsl-v214-neurips-stack

Objective: translate the NeurIPS-style backlog workflows to same-version v2.14
YAML and prove behavioral equivalence against the Phase 0 oracle.

Backlog authority:

- `docs/backlog/active/2026-05-09-dsl-v214-neurips-stack-translation.md`

Scope:

- `neurips_backlog_implementation_phase.v214.yaml`
- `neurips_backlog_seeded_plan_phase.v214.yaml`
- `neurips_backlog_roadmap_sync.v214.yaml`
- `neurips_selected_backlog_item.v214.yaml`
- old-stack versus v2.14-stack differential tests

Gate:

- Do not start until the public v2.14 release tranche has landed.
- Same-version v2.14 call stacks are required.
- Recovery, resource transitions, phase outcomes, review-loop macros, mixed
  versions, and general expression-language work remain deferred.

## Progress Ledger Expectations

The workflow progress ledger should record completed items and tranches only
after reviewed implementation evidence exists. Planning documents alone do not
complete a roadmap phase.
