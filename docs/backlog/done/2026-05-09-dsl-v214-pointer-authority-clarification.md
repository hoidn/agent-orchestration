---
priority: 0
plan_path: docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/2026-05-09-dsl-v214-pointer-authority-clarification/execution_plan.md
check_commands:
  - python -m json.tool docs/backlog/roadmap_gate.json
  - >-
    python workflows/library/scripts/build_neurips_backlog_manifest.py
    --backlog-root docs/backlog/active
    --output state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json
  - >-
    python workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py
    --manifest-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json
    --gate-policy-path docs/backlog/roadmap_gate.json
    --progress-ledger-path state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json
    --run-state-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json
    --output state/DSL-V214-MATERIALIZATION-VARIANTS/roadmap_gate_check.json
prerequisites:
  - 2026-05-08-dsl-v214-phase0-oracle
related_roadmap_phases:
  - phase-1-dsl-v214-runtime
signals_for_selection:
  - Pointer files are a cross-cutting authority surface for materialization, publishing, consumes, relpath artifacts, prompts, and legacy helper scripts.
  - The v2.14 plan relies on a strict distinction between artifact value, pointer file, and published artifact.
  - Phase 1 runtime work should not begin until pointer authority and migration boundaries are explicit.
blocking_signals:
  - Do not implement Phase 1 runtime surfaces as part of this item.
  - Do not enable public version 2.14 support.
  - Do not remove existing pointer files or change current workflow behavior.
  - Do not add public v214 workflow files.
---

# Backlog Item: DSL v2.14 Pointer Authority Clarification

## Objective

- Clarify the role of pointer files in the current DSL and v2.14
  materialization plan, then produce a decision record for whether pointer files
  remain canonical, become optional compatibility materializations, or are
  deprecated in favor of direct artifact refs.

## Problem

Current relpath artifact workflows use pointer files as workspace-visible
representations of artifact values. This is useful for file-oriented prompts
and helper scripts, but it creates extra authority surfaces:

```text
runtime artifact value
pointer file contents
top-level artifact pointer path
local step pointer path
```

The v2.14 plan depends on separating these roles:

- artifact value: typed value recorded in state;
- pointer file: text file containing that value;
- published artifact: top-level artifact version whose value is the artifact
  value, not the pointer-file path.

This item audits whether existing workflows, scripts, docs, and tests follow
that model closely enough for Phase 1 implementation to proceed.

## Scope

- Inventory pointer-file uses in:
  - `specs/dsl.md`
  - `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`
  - `workflows/library/*.yaml`
  - `workflows/examples/*.yaml`
  - `workflows/library/scripts/*.py`
  - tests that read or write `state/*_path.txt`
- Classify each pointer use as:
  - canonical top-level artifact pointer;
  - local step materialization pointer;
  - prompt/script compatibility input;
  - stale compatibility shim;
  - ambiguous authority surface.
- Identify cases where pointer-file path, artifact value, and published
  artifact name can drift.
- Define the Phase 1 rule for published relpath artifacts:
  - local pointer omitted, or
  - local pointer exactly equals the top-level canonical pointer.
- Decide whether noncanonical sidecar pointer files are forbidden in Phase 1,
  allowed only for unpublished local artifacts, or deferred pending explicit
  sidecar semantics.
- Draft a migration/deprecation policy:
  - keep pointer files as compatibility layer;
  - reduce pointer-file use in new v2.14 workflows;
  - prefer direct structured refs where available;
  - deprecate noncanonical local pointer files if they duplicate published
    artifact pointers.

## Non-Goals

- Do not remove existing pointer files.
- Do not change runtime behavior.
- Do not implement `materialize_artifacts`.
- Do not implement v2.14 loader/runtime support.
- Do not modify public DSL version support.
- Do not translate NeurIPS workflows to `.v214.yaml`.
- Do not introduce sidecar-pointer semantics beyond documenting whether they
  are deferred.

## Deliverables

- `docs/design/dsl_v214_pointer_authority.md`
- Pointer-use inventory table, either in the design note or as an appendix.
- Updates to the v2.14 implementation plan if the current pointer-authority
  section needs tightening.
- Optional Phase 0 oracle additions or follow-up notes that assert:
  - published artifact value is not the pointer-file path;
  - canonical pointer contents equal the artifact value;
  - duplicate local pointer surfaces are compatibility-only or rejected in the
    future plan.
- A clear Phase 1 recommendation:
  - keep pointer files as optional materialization only;
  - make runtime state and artifact lineage authoritative;
  - reject noncanonical pointer drift for published relpath artifacts.

## Acceptance Criteria

- A local inventory lists current pointer-file uses relevant to v2.14
  materialization.
- The inventory distinguishes artifact values from pointer-file paths.
- The design note states exactly which pointer surfaces are authoritative.
- The design note states which pointer patterns are allowed, rejected, or
  deferred in Phase 1.
- Published artifact lineage is explicitly defined as storing artifact values,
  not pointer-file paths.
- No runtime or public DSL behavior changes are made by this item.
