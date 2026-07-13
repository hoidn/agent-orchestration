# Parity Report: design_delta_parent_drain

- Candidate: `workflows/library/lisp_frontend_design_delta/drain.orc`
- YAML primary: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Generated at: `2026-07-13T06:59:27Z`
- Non-regressive: `true`
- Promotion eligible: `true`
- Primary surface: `orc`

## Baseline Characterization
- Inputs: `steering`, `target_design`, `baseline_design`, `manifest`, `progress_ledger`, `run_state`
- Outputs: `drain_terminal_variant`, `run_state`, `drain_summary`
- Terminal states: `selected item completed`, `selected item blocked recovery`, `blocked`, `exhausted`
- Artifacts: `selection bundle view`, `work item summary`, `drain summary`
- Resume behavior: `parent-callable family evidence covers resume and reuse behavior on the production route`

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
- `required.adapter_census`: `pass` (`.orchestrate/build/c5cf03b2755308a3/adapter_census.json`)
- `required.boundary_authority_report`: `pass` (`.orchestrate/build/c5cf03b2755308a3/boundary_authority_report.json`)
- `required.compatibility_bridge_report`: `pass` (`.orchestrate/build/c5cf03b2755308a3/compatibility_bridge_report.json`)
- `required.consumer_rendering_census_report`: `pass` (`.orchestrate/build/c5cf03b2755308a3/consumer_rendering_census_report.json`)
- `required.core_workflow_ast`: `pass` (`.orchestrate/build/c5cf03b2755308a3/core_workflow_ast.json`)
- `required.entry_publication_report`: `pass` (`.orchestrate/build/c5cf03b2755308a3/entry_publication_report.json`)
- `required.g8_deletion_evidence`: `pass` (`.orchestrate/build/c5cf03b2755308a3/g8_deletion_evidence.json`)
- `required.rendering_cleanup_report`: `pass` (`.orchestrate/build/c5cf03b2755308a3/rendering_cleanup_report.json`)
- `required.rendering_ergonomics_report`: `pass` (`.orchestrate/build/c5cf03b2755308a3/rendering_ergonomics_report.json`)
- `required.semantic_ir`: `pass` (`.orchestrate/build/c5cf03b2755308a3/semantic_ir.json`)
- `required.source_map`: `pass` (`.orchestrate/build/c5cf03b2755308a3/source_map.json`)
- `required.transition_authoring_report`: `pass` (`.orchestrate/build/c5cf03b2755308a3/transition_authoring_report.json`)
- `required.typed_prompt_input_report`: `pass` (`.orchestrate/build/c5cf03b2755308a3/typed_prompt_input_report.json`)
- `required.value_flow_census_report`: `pass` (`.orchestrate/build/c5cf03b2755308a3/value_flow_census_report.json`)
- `required.workflow_boundary_projection`: `pass` (`.orchestrate/build/c5cf03b2755308a3/workflow_boundary_projection.json`)
- `optional.expanded_debug_yaml`: `not_implemented`

## Deprecated YAML Mechanics
- `leaf-only compile/smoke evidence used as family proof` -> `parent-callable compile, smoke, boundary, route, and resource-transition evidence`
- `manual parent-drain parity conclusion` -> `machine-readable migration-parity report with required family evidence roles`
