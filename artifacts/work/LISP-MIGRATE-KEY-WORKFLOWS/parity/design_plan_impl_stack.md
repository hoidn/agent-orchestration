# Parity Report: design_plan_impl_stack

- Candidate: `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- YAML primary: `workflows/examples/design_plan_impl_review_stack_v2_call.yaml`
- Generated at: `2026-07-16T04:39:17Z`
- Non-regressive: `true`
- Promotion eligible: `true`
- Primary surface: `orc`

## Baseline Characterization
- Inputs: `brief_path`, `design_target_path`, `design_review_report_target_path`, `plan_target_path`, `plan_review_report_target_path`, `execution_report_target_path`, `implementation_review_report_target_path`
- Outputs: `design_path`, `design_review_report_path`, `design_review_decision`, `plan_path`, `plan_review_report_path`, `plan_review_decision`, `execution_report_path`, `implementation_review_report_path`, `implementation_review_decision`
- Terminal states: `design review decision surfaced`, `plan review decision surfaced`, `implementation review decision surfaced`
- Artifacts: `design report target`, `plan report target`, `implementation execution report target`, `implementation review report target`
- Resume behavior: `same-ID post-plan-draft default resume restores the validated prior boundary, reuses design.draft, design.review, and plan.draft exactly once, and executes plan.review, implementation.execute, and implementation.review exactly once`

## Evidence
- `compile`: `pass`
- `shared_validation`: `pass`
- `dry_run`: `pass`
- `smoke_or_integration`: `pass`
- `baseline_characterization`: `pass`
- `output_contract_parity`: `pass`
- `terminal_state_parity`: `pass`
- `artifact_parity`: `pass`
- `resume_parity`: `pass`

## Compile Artifacts
- `required.core_workflow_ast`: `pass` (`.orchestrate/build/cb23d16e3c26d7f7/core_workflow_ast.json`)
- `required.semantic_ir`: `pass` (`.orchestrate/build/cb23d16e3c26d7f7/semantic_ir.json`)
- `required.source_map`: `pass` (`.orchestrate/build/cb23d16e3c26d7f7/source_map.json`)
- `optional.expanded_debug_yaml`: `not_implemented`

## Deprecated YAML Mechanics
- `manual markdown parity summary` -> `machine-readable parity JSON report`
- `full YAML review-revise loop with carried findings extraction` -> `family-specific .orc design_plan_impl_stack parity route with typed review decisions, validated artifacts, and reusable phase-state evidence`
