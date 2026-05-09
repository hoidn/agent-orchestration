# Output Bundle Variant Surface Review Plan

## Objective

Decide whether v2.14 should introduce a sibling `variant_output` contract or
extend `output_bundle` with tagged-union variant semantics.

## Scope

- Review current `output_bundle`, `expected_outputs`, provider output capture,
  prompt injection, and artifact publication semantics.
- Compare two DSL surface options:
  - new sibling contract: `variant_output`;
  - extended contract: `output_bundle.variants`.
- Preserve the underlying semantic requirements:
  - discriminant enum;
  - variant-specific required fields;
  - variant-specific forbidden fields;
  - selected-field artifact exposure;
  - branch proof through `match` or `requires_variant`;
  - runtime guard for unavailable variant fields.
- Determine how this decision affects Phase 1 implementation tasks, tests,
  specs, docs, and the Phase 0 oracle expectations.

## Non-Goals

- Do not implement the runtime semantics in this item.
- Do not change `select_variant_output`; it remains a distinct deterministic
  execution form unless this review finds a stronger reason to merge it.
- Do not broaden into deferred recovery, resource-transition, phase-outcome, or
  review-loop abstractions.

## Required Evidence

- A short design note records the selected surface and rejects the alternative
  with concrete reasons.
- The v2.14 implementation plan is updated if the selected surface differs from
  its current `variant_output` wording.
- Phase 1 backlog scope is updated so implementation does not proceed with a
  stale contract name.
- Any affected tests or oracle descriptions are updated at the planning level,
  without changing runtime behavior yet.

## Verification

- `python -m json.tool docs/backlog/roadmap_gate.json`
- `python workflows/library/scripts/build_neurips_backlog_manifest.py --backlog-root docs/backlog/active --output state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json`
- `python workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py --manifest-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json --gate-policy-path docs/backlog/roadmap_gate.json --progress-ledger-path state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --run-state-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --output state/DSL-V214-MATERIALIZATION-VARIANTS/roadmap_gate_check.json`
