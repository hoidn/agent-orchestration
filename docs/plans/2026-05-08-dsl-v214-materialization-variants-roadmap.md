# DSL v2.14 Materialization And Variant Semantics Roadmap

This roadmap is the local NeurIPS-style execution authority for the v2.14
materialization and variant-output work. The detailed design authority is
`docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`.
The tagged-union validation surface decision is recorded in
`docs/design/dsl_v214_variant_surface_decision.md`.

## Current Gate

- Gate id: `dsl-v214-phase2-neurips-stack`
- Selectable phase prefix: `phase-2-dsl-v214-neurips-stack`
- Blocked future prefixes: none

The current gate advances to Phase 2 after the Phase 1 runtime semantics and
public v2.14 release tranche landed together.

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
- The Phase 0 oracle preserves the pre-release behavior evidence; current
  normal CLI and loader paths now accept public `version: "2.14"` after the
  Phase 1 release.
- The oracle can drive both primitive and minimal NeurIPS-style scenarios with
  fake providers.

## Phase 1: phase-1-dsl-v214-runtime

Objective: implement the narrow v2.14 semantic tranche after Phase 0 is stable.

Backlog authority:

- `docs/backlog/done/2026-05-09-output-bundle-variant-surface-review.md`
- `docs/backlog/done/2026-05-09-dsl-v214-pointer-authority-clarification.md`
- `docs/backlog/done/2026-05-09-roadmap-gate-empty-active-gap.md`
- `docs/backlog/done/2026-05-09-dsl-v214-runtime-semantics.md`

Scope:

- `materialize_artifacts`
- `pre_snapshot`
- `variant_output` tagged-union provider/command output validation
- `select_variant_output`
- `requires_variant`
- match-based variant proof
- snapshot-reference taxonomy
- variant field availability
- strict relpath pointer authority
- contract inheritance and refinement validation
- exact error taxonomy and runtime integration points

Gate:

- Phase 1 is complete.
- Public `version: "2.14"` is released through loader, runtime, docs, and tests.

## Phase 2: phase-2-dsl-v214-neurips-stack

Objective: translate the NeurIPS-style backlog workflows to same-version v2.14
YAML and prove behavioral equivalence against the Phase 0 oracle.

Backlog authority:

- `docs/backlog/done/2026-05-09-dsl-v214-neurips-stack-translation.md`
- `docs/backlog/done/2026-05-09-dsl-v214-yaml-ergonomics-loc-reduction.md`

Scope:

- `neurips_backlog_implementation_phase.v214.yaml`
- `neurips_backlog_seeded_plan_phase.v214.yaml`
- `neurips_backlog_roadmap_sync.v214.yaml`
- `neurips_selected_backlog_item.v214.yaml`
- old-stack versus v2.14-stack differential tests
- v2.14 YAML ergonomics correction so the translated production stack is
  smaller than the legacy stack
- LOC regression checks for the NeurIPS v2.14 workflow stack

Gate:

- Public v2.14 release tranche has landed.
- Same-version v2.14 call stacks are required.
- Recovery, resource transitions, phase outcomes, review-loop macros, mixed
  versions, and general expression-language work remain deferred.

## Progress Ledger Expectations

The workflow progress ledger should record completed items and tranches only
after reviewed implementation evidence exists. Planning documents alone do not
complete a roadmap phase.
