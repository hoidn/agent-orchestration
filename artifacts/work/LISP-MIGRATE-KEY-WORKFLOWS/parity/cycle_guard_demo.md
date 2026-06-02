# Parity Report: cycle_guard_demo

- Candidate: `workflows/examples/cycle_guard_demo.orc`
- YAML primary: `workflows/examples/cycle_guard_demo.yaml`
- Generated at: `2026-06-02T13:53:48Z`
- Non-regressive: `true`
- Promotion eligible: `false`
- Primary surface: `yaml`

## Baseline Characterization
- Inputs: `terminal_status`, `guard_cycles`
- Outputs: `terminal_status`, `guard_cycles`
- Terminal states: `completed with structured guard summary`
- Artifacts: `runtime-owned command-result bundle path`
- Resume behavior: `single-step command bridge with no reusable phase-state promotion`

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
- `required.core_workflow_ast`: `pass` (`.orchestrate/build/48b2e2abdce5c28f/core_workflow_ast.json`)
- `required.semantic_ir`: `pass` (`.orchestrate/build/48b2e2abdce5c28f/semantic_ir.json`)
- `required.source_map`: `pass` (`.orchestrate/build/48b2e2abdce5c28f/source_map.json`)
- `optional.expanded_debug_yaml`: `not_implemented`

## Deprecated YAML Mechanics
- `manual markdown parity summary` -> `machine-readable parity JSON report`
