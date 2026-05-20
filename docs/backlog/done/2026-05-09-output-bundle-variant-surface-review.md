---
priority: -1
plan_path: docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/2026-05-09-output-bundle-variant-surface-review/execution_plan.md
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
  - The v2.14 plan currently proposes a new `variant_output` sibling contract.
  - Extending `output_bundle` with variants may reduce DSL surface area while preserving the same semantics.
  - This decision should be settled before Phase 1 runtime implementation.
blocking_signals:
  - Do not implement runtime semantics in this review item.
  - Do not change `select_variant_output` unless the design note explicitly justifies it.
---

# Backlog Item: Output Bundle Variant Surface Review

## Objective

- Decide whether tagged-union provider/command output validation should be a
  new `variant_output` contract or an extension of existing `output_bundle`.

## Problem

The v2.14 plan introduces `variant_output` because existing `output_bundle`
cannot express conditional output validity. The underlying need is real:
variant-specific required fields, forbidden fields, and branch-safe references.
However, a sibling output contract overlaps with existing provider-step output
surfaces. Extending `output_bundle` with a tagged-union mode may be a smaller
and more discoverable DSL change.

## Scope

- Compare `variant_output` versus `output_bundle.variants` as the authored DSL
  surface for provider/command-produced tagged-union JSON.
- Keep `select_variant_output` separate unless the review finds a concrete
  reason to merge deterministic evidence selection with bundle validation.
- Update the v2.14 plan, Phase 1 backlog item, and draft oracle/design wording
  to match the selected surface.

## Non-Goals

- Do not implement loader/runtime support yet.
- Do not add public v2.14 workflow examples.
- Do not alter current `output_bundle` behavior for fixed-shape bundles.
- Do not expand into recovery, resource-transition, phase-outcome, review-loop,
  mixed-version, or expression-language work.

## Required Evidence

- A design note records the selected surface, tradeoffs, and rejected option.
- The v2.14 implementation plan no longer contains stale surface guidance.
- Phase 1 backlog scope names the selected contract surface.
- Deterministic manifest and gate checks pass.
