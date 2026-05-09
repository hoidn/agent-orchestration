---
priority: 2
plan_path: docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md
check_commands:
  - pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q
  - python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json
prerequisites:
  - 2026-05-09-dsl-v214-runtime-semantics
related_roadmap_phases:
  - phase-2-dsl-v214-neurips-stack
signals_for_selection:
  - Public v2.14 runtime semantics have landed.
  - The next tranche is workflow translation and equivalence proof.
blocking_signals:
  - Do not start until the Phase 1 runtime semantics item is complete.
  - Do not mix v2.14 caller/callee workflows with older DSL versions.
---

# Backlog Item: DSL v2.14 NeurIPS Stack Translation

## Objective

- Translate the NeurIPS-style backlog workflow stack to same-version v2.14 YAML
  and prove behavioral equivalence against the Phase 0 oracle.

## Scope

- Add v2.14 workflow variants for:
  - `neurips_backlog_implementation_phase.v214.yaml`
  - `neurips_backlog_seeded_plan_phase.v214.yaml`
  - `neurips_backlog_roadmap_sync.v214.yaml`
  - `neurips_selected_backlog_item.v214.yaml`
- Replace hand-authored pointer, snapshot, and tagged-union glue where Phase 1
  semantics now provide first-class runtime support.
- Keep the v2.14 stack same-version only.
- Add differential tests that compare old and v2.14 normalized observations for
  the Phase 0 primitive and minimal NeurIPS scenarios.

## Non-Goals

- Do not implement Phase 1 runtime primitives in this item.
- Do not add mixed-version reusable workflow calls.
- Do not add deferred recovery, resource-transition, phase-outcome, review-loop,
  or frontend abstractions.
- Do not delete the old workflow stack until equivalence is proven and a later
  migration decision is made.

## Required Evidence

- The v2.14 NeurIPS stack calls only v2.14 workflows.
- Old-stack and v2.14-stack normalized observations match for completed,
  blocked, ambiguous, missing-output, fresh-plan, recovered-plan, and
  selected-item scenarios.
- Workflow validation and smoke checks pass under normal CLI/loader support for
  public `version: "2.14"`.
- Documentation explains when to use the v2.14 workflows and which old glue
  patterns they replace.

## Notes

- This item is intentionally blocked behind Phase 1. If selected earlier, the
  correct outcome is a roadmap or prerequisite block, not a partial translation.
