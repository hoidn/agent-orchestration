---
priority: 2
plan_path: docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/2026-05-09-dsl-v214-yaml-ergonomics-loc-reduction/execution_plan.md
check_commands:
  - pytest tests/test_loader_validation.py -k 'variant_output or materialize' -q
  - pytest tests/test_output_contract.py -k 'variant' -q
  - pytest tests/test_prompt_contract_injection.py -k 'variant_output' -q
  - pytest tests/test_v214_runtime_semantics.py -q
  - pytest tests/test_workflow_loc_comparison.py -q
  - pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q
  - >-
    python workflows/library/scripts/compare_workflow_loc.py
    --old workflows/library/neurips_backlog_implementation_phase.yaml
    --old workflows/library/neurips_backlog_seeded_plan_phase.yaml
    --old workflows/library/neurips_backlog_roadmap_sync_phase.yaml
    --old workflows/library/neurips_selected_backlog_item.yaml
    --new workflows/library/neurips_backlog_implementation_phase.v214.yaml
    --new workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml
    --new workflows/library/neurips_backlog_roadmap_sync.v214.yaml
    --new workflows/library/neurips_selected_backlog_item.v214.yaml
    --require-total-reduction-pct 1
  - >-
    python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run
    --input steering_path=docs/steering.md
    --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md
    --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md
    --input backlog_root=docs/backlog/active
    --input roadmap_gate_path=docs/backlog/roadmap_gate.json
    --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json
    --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain
    --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json
    --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json
prerequisites:
  - 2026-05-09-dsl-v214-neurips-stack-translation
related_roadmap_phases:
  - phase-2-dsl-v214-neurips-stack
signals_for_selection:
  - The first v2.14 NeurIPS stack translation proved equivalence but increased YAML LOC.
  - The selected-item v2.14 workflow exploded JSON bundle fields into per-field text files.
  - v2.14 should reduce brittle YAML authoring, not merely preserve behavior with more verbose contracts.
blocking_signals:
  - Do not reopen the public v2.14 release decision.
  - Do not delete the legacy workflow stack.
  - Do not weaken old-stack versus v2.14 behavioral equivalence.
  - Do not add mixed-version reusable workflow calls.
---

# Backlog Item: DSL v2.14 YAML Ergonomics LOC Reduction

## Objective

Correct the v2.14 NeurIPS workflow translation so it delivers the intended
authoring simplification. The current v2.14 stack is behaviorally equivalent to
the old stack, but it is longer. This item must make the v2.14 production stack
shorter than the legacy stack while preserving the equivalence tests.

## Background

The first Phase 2 translation grew the production stack from 2331 lines to 2646
lines. The largest regression was `neurips_selected_backlog_item.v214.yaml`,
which grew from 966 to 1257 lines after a compact JSON bundle was split into
many per-field text files and `expected_outputs` entries.

That result is not acceptable as the final v2.14 authoring pattern. The DSL
should keep deterministic contracts explicit while validating native JSON
bundles directly.

Design authority:

- `docs/design/dsl_v214_yaml_ergonomics.md`

Implementation plan:

- `docs/plans/2026-05-09-dsl-v214-yaml-ergonomics-loc-reduction-plan.md`

## Scope

- Add `variant_output.shared_fields` so common tagged-union fields are declared
  once.
- Add `materialize_artifacts.input_values` so repeated input-to-pointer
  materialization can be declared compactly.
- Rewrite `workflows/library/neurips_selected_backlog_item.v214.yaml` to
  validate `selected-item-inputs.json` directly.
- Keep `output_bundle` for fixed-shape JSON outputs.
- Add a deterministic LOC comparison script and test.
- Update specs and workflow docs for the compact v2.14 authoring pattern.

## Non-Goals

- Do not remove `variant_output`, `select_variant_output`, or
  `materialize_artifacts`.
- Do not delete the legacy workflow stack.
- Do not add a general expression language.
- Do not add deferred workflow abstractions such as `recover_or_run`,
  `resource_transition`, `phase_outcome`, or review-loop macros.
- Do not change provider prompt semantics except for rendering
  `variant_output.shared_fields`.

## Required Evidence

- The v2.14 production stack is shorter than the legacy four-file stack.
- The selected-item v2.14 workflow no longer splits
  `selected-item-inputs.json` into per-field text files.
- Old-stack versus v2.14 NeurIPS equivalence tests pass.
- Primitive v2.14 runtime tests pass for shared fields and batch
  materialization.
- Prompt-contract injection includes shared fields exactly once.
- The workflow dry-run in `check_commands` passes.
- No literal `${inputs.*}` directories are created.

## Acceptance Criteria

- `variant_output.shared_fields` is implemented, documented, and tested.
- `materialize_artifacts.input_values` is implemented, documented, and tested.
- The v2.14 NeurIPS stack retains same-version v2.14 calls only.
- LOC regression is enforced by a repeatable script rather than manual `wc -l`
  inspection.
- The execution report records old LOC, new LOC, absolute delta, and percent
  delta.

## Notes

This item follows the completed Phase 2 equivalence work. It should be selected
under the same `phase-2-dsl-v214-neurips-stack` roadmap gate because it repairs
the authoring-quality failure discovered by that translation.
