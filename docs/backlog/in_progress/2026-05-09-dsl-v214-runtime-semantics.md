---
priority: 1
plan_path: docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/2026-05-09-dsl-v214-runtime-semantics/execution_plan.md
check_commands:
  - pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q
  - pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q
  - python -m json.tool docs/backlog/roadmap_gate.json
  - python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json
prerequisites:
  - 2026-05-09-output-bundle-variant-surface-review
  - 2026-05-09-dsl-v214-pointer-authority-clarification
  - 2026-05-09-roadmap-gate-empty-active-gap
related_roadmap_phases:
  - phase-1-dsl-v214-runtime
signals_for_selection:
  - Phase 0 oracle has frozen current behavior.
  - Variant contract surface, pointer authority, and empty-active gap behavior have been settled.
  - This is the implementation tranche for actual v2.14 runtime semantics.
blocking_signals:
  - Do not translate NeurIPS workflows to public v2.14 YAML in this item.
  - Do not broaden scope to recover_or_run, resource_transition, phase_outcome, review_loop, mixed-version calls, or a general expression language.
---

# Backlog Item: DSL v2.14 Runtime Semantics

## Objective

- Implement the narrow v2.14 runtime semantics tranche after the Phase 0 oracle
  and Phase 1 design-gating items have completed.

## Scope

- Add the loader, IR, runtime, contract, reference, snapshot, variant, pointer,
  observability, and error-taxonomy work required for:
  - `materialize_artifacts`
  - `pre_snapshot`
  - the selected tagged-union output-bundle surface
  - `select_variant_output`
  - `requires_variant`
  - match-based variant proof
- Preserve public exposure gating until the release tranche lands with runtime,
  loader, docs, and tests together.
- Reuse the Phase 0 oracle fixtures as regression coverage and update them only
  when the semantic change is deliberate and documented.
- Update normative docs and acceptance fixtures only as part of the v2.14
  release tranche described in the implementation plan.

## Non-Goals

- Do not create `workflows/library/*.v214.yaml` as public runnable workflows.
- Do not migrate the NeurIPS workflow stack.
- Do not implement deferred primitives:
  - `recover_or_run`
  - `resource_transition`
  - `phase_outcome`
  - `review_loop`
- Do not add mixed-version calls, metadata-only freshness, large-file hash
  caching, a general expression language, or general `if`/`when` variant proof.

## Required Evidence

- Unit and integration tests cover materialization contract inheritance,
  snapshot evidence, variant validation, selector commit atomicity,
  variant-reference proof, prompt contract injection, and public version
  exposure gating.
- Existing Phase 0 oracle tests still pass or are intentionally updated with a
  documented semantic delta.
- Normal loader/CLI behavior remains gated until docs and runtime support are
  released together.
- Deterministic dry-run validation of the local backlog drain still passes.

## Notes

- The design authority is
  `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`.
- Phase 2 depends on this item because workflow translation requires public
  v2.14 support.
