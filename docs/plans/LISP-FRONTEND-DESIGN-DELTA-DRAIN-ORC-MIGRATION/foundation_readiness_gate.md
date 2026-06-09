# Runtime Foundation Readiness Gate

Status: complete for first pass
Created: 2026-06-09
Plan: `../2026-06-09-lisp-frontend-design-delta-drain-orc-migration-plan.md`

## Decision

The runtime foundation gate is satisfied for starting the next migration slice
of the design-delta drain `.orc` candidate.

This does not promote any `.orc` workflow and does not make YAML non-primary.
It means the prerequisite runtime/frontend surfaces named by Task 0 have fresh
focused evidence or a fixed proof-path bug with regression coverage.

## Fix Applied During Gate

The imported `resume-or-start` managed-write-root proof initially failed before
reaching allocator assertions:

```text
phase_context_invalid: `with-phase` requires a `PhaseCtx` value or the bounded legacy implementation bridge
```

Root cause: imported type refs are canonicalized to module-qualified binding
names, while `with-phase` and generic phase stdlib checks recognized only the
short ref name `PhaseCtx`. The patch makes phase context recognition use the
authored record definition name and then keep the existing structural field
validation. This accepts imported `PhaseCtx`/`RunCtx` definitions without
accepting arbitrary records.

Changed files:

- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`

## Evidence

### Command Structured Output

```bash
pytest tests/test_workflow_output_contract_integration.py \
  -k "command_output_bundle_runtime_env_overrides_authored_env or command_output_bundle_parent_is_created_before_launch or command_output_bundle_stdout_json_does_not_satisfy_missing_bundle or command_variant_output_receives_runtime_bundle_env or command_variant_output_parent_is_created_before_launch or command_variant_output_stdout_json_does_not_satisfy_missing_bundle" -q
```

Result:

```text
6 passed, 17 deselected
```

### Provider Structured Output And Collection Prompt Rendering

```bash
pytest tests/test_prompt_contract_injection.py tests/test_managed_provider_execution.py \
  -k "provider_variant_output_receives_runtime_bundle_env or provider_variant_output_wrong_bundle_path_fails_contract or provider_output_bundle_receives_runtime_bundle_env or provider_prompt_injection_renders_collection_consumed_value or prompt_consumes_subset_renders_collection_value or structured_output_binding_survives_guard_wrap" -q
```

Result:

```text
7 passed, 28 deselected
```

### Private Collection Artifact/Dataflow Lane And Migration Gates

```bash
pytest tests/test_dataflow.py tests/test_state_manager.py tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_migration_parity.py \
  -k "private_collection or private_artifact or migration_parity_cli_returns_one_for_require_non_regressive_failure or migration_parity_cli_returns_one_for_require_promotable_ineligible_target or migration_parity_cli_returns_two_for_stale_reused_report or migration_parity_cli_rejects_manifest_override or gate_evaluation_distinguishes_non_regressive_from_promotable or non_regressive_recomputation_mismatch or load_parity_targets_rejects_hidden_managed_write_root_input" -q
```

Result:

```text
13 passed, 114 deselected
```

### StateLayout / PathAllocator, Hidden Write Roots, Source Map, Semantic IR

```bash
pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_phase_stdlib.py tests/test_resume_command.py tests/test_workflow_lisp_cli.py \
  -k "workflow_boundary_projection_emits_generated_path_allocations or source_map_emits_generated_path_allocations or semantic_ir_emits_generated_path_allocations or build_artifacts_emit_entrypoint_managed_write_root_allocations or generated_path_allocations_map_to_frontend_origins or formatting_only_source_changes_preserve_allocation_identity or run_provider_phase_generated_bundle_paths_use_allocator_metadata or resume_or_start_workflow_call_uses_shared_managed_write_root_bundle_path or resume_or_start_imported_workflow_call_uses_shared_managed_write_root_bundle_path or entry_managed_write_root_bindings_are_run_isolated_and_resume_stable or entry_managed_write_root_paths_do_not_collide_across_runs or run_workflow_orc_public_binding_excludes_managed_write_roots" -q
```

Result:

```text
12 passed, 243 deselected
```

### Design Delta Feasibility And Private Collection Runtime

```bash
pytest tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  -k "review_revise_design_docs_runtime_private_collection_lane or design_delta" -q
```

Result:

```text
7 passed, 8 deselected
```

### CLI Dry Run And Artifact Emission

Dry run:

```bash
python -m orchestrator run workflows/examples/cycle_guard_demo.orc \
  --dry-run \
  --entry-workflow cycle-guard-demo \
  --source-root workflows/examples \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/cycle_guard_demo.commands.json \
  --input terminal_status=FAILED_CLOSED_BY_GUARD \
  --input guard_cycles=2
```

Result:

```text
[DRY RUN] Workflow validation successful
```

The run emitted one lint warning for a generated managed write-root input that
redundantly declares `kind: relpath` alongside `type: relpath`. The workflow
still validated successfully, and the public-input exclusion selector above
passed.

Artifact emission:

```bash
python -m orchestrator compile workflows/examples/cycle_guard_demo.orc \
  --entry-workflow cycle-guard-demo \
  --source-root workflows/examples \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/cycle_guard_demo.commands.json \
  --emit-source-map .orchestrate/tmp/design-delta-drain-gate/source_map.json \
  --emit-semantic-ir .orchestrate/tmp/design-delta-drain-gate/semantic_ir.json \
  --emit-runtime-plan .orchestrate/tmp/design-delta-drain-gate/runtime_plan.json
```

Result:

```text
diagnostic_count: 0
entry_workflow: cycle_guard_demo::cycle-guard-demo
fingerprint: 48b2e2abdce5c28f
```

Exported artifact inspection:

```text
source_map_schema workflow_lisp_source_map.v1
source_map_generated_paths cycle_guard_demo::cycle-guard-demo 2 generated paths, 2 generated allocations, 1 generated internal input
semantic_ir_schema workflow_semantic_ir.v1
semantic_ir state_layout entries include command_result_bundle and entrypoint_managed_write_root allocation ids
runtime_plan_schema workflow_runtime_plan.v1
```

## Residual Notes

- The gate verifies focused prerequisites for beginning the next migration
  slice. It is not full promotion parity evidence.
- The cycle-guard dry run lint warning should remain visible, but it does not
  block the design-delta drain plan phase candidate.
- YAML remains authoritative for `lisp_frontend_design_delta_drain` until the
  later migration parity tasks compute non-regression and `--require-promotable`
  succeeds.
