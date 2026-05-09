---
priority: 1
plan_path: docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md
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
  - >-
    python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml
    --dry-run
    --input steering_path=docs/steering.md
    --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md
    --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md
    --input backlog_root=docs/backlog/active
    --input roadmap_gate_path=docs/backlog/roadmap_gate.json
    --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json
    --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain
    --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json
    --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json
prerequisites: []
related_roadmap_phases:
  - phase-0-dsl-v214-oracle
signals_for_selection:
  - First runnable tranche in the DSL v2.14 materialization and variant-output roadmap.
  - Freezes behavior before any public v2.14 runtime semantics are enabled.
blocking_signals:
  - Do not implement Phase 1 runtime surfaces as part of this item.
  - Do not add public v2.14 workflow examples or supported-version declarations.
---

# Backlog Item: DSL v2.14 Phase 0 Oracle

## Objective

- Implement the Phase 0 behavior oracle for DSL v2.14 materialization,
  snapshot, and variant-output semantics before changing public DSL behavior.

## Scope

- Create draft, non-normative design and behavior-matrix documents if the
  existing implementation plan needs a split artifact for runtime consumers.
- Add primitive fixtures that emulate future `materialize_artifacts`,
  `pre_snapshot`, `variant_output`, and `select_variant_output` behavior using
  currently supported DSL surfaces.
- Add a minimal NeurIPS-style fixture workspace that captures steering, design,
  roadmap, backlog, queue, progress-ledger, and run-state shapes without copying
  a full external project.
- Add a fake provider that deterministically produces completed, blocked,
  ambiguous, missing-output, review-approve, and review-revise scenarios.
- Add a golden observation normalizer and regression tests that freeze current
  behavior before v2.14 semantics are implemented.

## Non-Goals

- Do not enable `version: "2.14"` in the normal loader or CLI.
- Do not add public `*.v214.yaml` workflows.
- Do not implement Phase 1 runtime surfaces.
- Do not translate the NeurIPS workflow stack to v2.14.
- Do not add recovery, resource-transition, phase-outcome, or review-loop macro
  abstractions.

## Required Evidence

- The primitive oracle and minimal NeurIPS oracle tests pass without network
  access or real provider calls.
- A test or fixture proves public `version: "2.14"` remains rejected.
- Golden observations normalize volatile run IDs, absolute temp paths,
  timestamps, durations, and incidental ordering while preserving final outputs,
  artifact values, selected variants, file hashes, queue state, and failure
  classes.
- The deterministic checks listed in the frontmatter pass.

## Notes

- The implementation plan remains the design authority:
  `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`.
- Phase 1 and Phase 2 are intentionally represented in the roadmap but are not
  selectable under the current gate.
