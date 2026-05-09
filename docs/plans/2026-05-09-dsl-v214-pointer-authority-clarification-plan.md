# DSL v2.14 Pointer Authority Clarification Plan

## Objective

Clarify pointer-file authority before Phase 1 implements `materialize_artifacts`
and related artifact dataflow semantics.

## Scope

- Inventory current pointer-file usage in specs, docs, workflows, scripts, and
  tests.
- Classify each use as canonical artifact pointer, local step materialization,
  prompt/script compatibility input, stale compatibility shim, or ambiguous
  authority surface.
- Identify drift risks between artifact values, pointer-file contents,
  pointer-file paths, and published artifact lineage.
- Produce a design note with a single authority model for pointer files and a
  Phase 1 migration/deprecation decision.
- Tighten the v2.14 implementation plan if the existing pointer-authority
  language leaves implementation ambiguity.

## Required Decision

Decide whether Phase 1 should:

- keep pointer files only as optional compatibility materializations;
- make runtime state and artifact lineage the authoritative record;
- reject noncanonical pointer drift for published relpath artifacts;
- allow noncanonical local sidecar pointers only for unpublished local artifacts;
- defer any broader sidecar-pointer semantics.

## Non-Goals

- Do not remove existing pointer files.
- Do not change runtime behavior.
- Do not implement `materialize_artifacts`.
- Do not implement v2.14 loader/runtime support.
- Do not enable public `version: "2.14"` support.
- Do not translate workflows to `.v214.yaml`.

## Deliverables

- `docs/design/dsl_v214_pointer_authority.md`
- Pointer-use inventory table in the design note or an appendix.
- Updates to
  `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`
  if needed.
- Optional Phase 0 oracle follow-up notes if the audit finds assertions that
  should be added before runtime work proceeds.

## Verification

- `python -m json.tool docs/backlog/roadmap_gate.json`
- `python workflows/library/scripts/build_neurips_backlog_manifest.py --backlog-root docs/backlog/active --output state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json`
- `python workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py --manifest-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json --gate-policy-path docs/backlog/roadmap_gate.json --progress-ledger-path state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --run-state-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --output state/DSL-V214-MATERIALIZATION-VARIANTS/roadmap_gate_check.json`
