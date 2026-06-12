# Consumer-Side Rendering Design Plan

Status: plan
Created: 2026-06-12
Scope: draft a follow-on target design,
`docs/design/workflow_lisp_consumer_side_rendering.md`, that inverts
materialization from producer-authored to consumer-derived, reducing
reliance on authored views in favor of native typed values.

## Origin

Design dialogue on the G4 materialized-view surface (2026-06-12): the
organizing insight is that rendering is a consumer-side concern. Today the
workflow that has a typed value writes files for whoever might need them;
every ergonomic complaint (ceremony, path plumbing, "why do authors deal
with materialization") traces to that direction. Inverting it per consumer
class shrinks body-level `materialize-view` to a small residue (timed and
interior publications).

## Inputs

- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  (G4 `materialize-view` kernel, boundary authority classes, census
  discipline; in-flight at drafting time — this design consumes the kernel
  and adds surfaces that lower to it).
- `docs/design/workflow_lisp_runtime_migration_foundation.md` (prompt
  composition, structured output authority).
- Observability surfaces (`orchestrate report`, dashboard; summaries are
  observability artifacts and must not drive routing).
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  (family promotion, idiom 10A values-before-artifacts, Tranche 9
  simplification).
- Sibling target: `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
  (no dependency either way; both gate on generic-core acceptance points).

## Design decisions to encode

1. Principle: producers publish typed values; rendering happens at the
   consumer seam. Four lanes: in-program prompt consumers (render at
   injection, ephemeral, evidence = composed-prompt log); humans
   (observability layer renders typed terminal results; authored human
   summaries retire); the outside (entry-boundary per-variant `:publish`
   policy, sugar lowering to `materialize-view` at terminal arms); legacy
   consumers (compatibility bridges as classification metadata that drives
   file maintenance; retirement = metadata deletion).
2. Kernel split: ephemeral renderings (no durable allocation) vs durable
   views (outside consumers only); the G4 renderer interface must be
   callable independently of file allocation (guard-rail task added to G4).
3. Residue stays authored: timed/interior publications (per-iteration
   progress views, mid-run evidence) remain body-level `materialize-view`.
4. Effects stay visible in every lane; nothing becomes implicit-invisible.
5. Tranches C0-C5 with contract/tasks/acceptance; future-target framing;
   not drain-selectable until G4 has acceptance evidence; no ordering
   constraint relative to the checkpoints target.

## Edits

1. Add the renderer-seam guard-rail task to the generic-core doc's G4
   tranche (rides with that file's entangled commit).
2. Create `docs/design/workflow_lisp_consumer_side_rendering.md`.
3. Add discoverability entries to `docs/design/README.md` and
   `docs/index.md`.

## Verification

- `git diff --check` clean; referenced files exist.
- No ownership conflicts; no claims that G4 in-flight scope is changed.
