# Design Documentation Index

Design docs grouped by topic, one line each: what the doc covers and its state.
`specs/` defines runtime and DSL behavior; the
[capability status matrix](../capability_status_matrix.md) says what runs and
whether to use it for new work.

States: *implemented* (the doc describes running behavior), *partial* (some of
it runs; the doc says which parts), *design only* (nothing implemented),
*historical* (kept for context; do not use for new work).

## Principles and language baseline

- [workflow_language_design_principles.md](workflow_language_design_principles.md) — where workflow meaning lives across the DSL, frontends, macros and IRs; some principles are enforced, others are direction. *Partial.*
- [workflow_lisp_frontend_specification.md](workflow_lisp_frontend_specification.md) — umbrella Workflow Lisp language contract that the component docs refine; not every surface it describes exists. *Partial.*
- [workflow_lisp_refactor_architecture.md](workflow_lisp_refactor_architecture.md) — target module boundaries for behavior-preserving frontend refactors. *Partial.*

## Execution profiles

- [workflow_lisp_evaluated_execution.md](workflow_lisp_evaluated_execution.md) — typed 2.35/2.36 closed-program compile, effect memo, resume and suffix invalidation, and the effect classes it refuses. *Implemented.*
- [workflow_lisp_dynamic_core_proposal.md](workflow_lisp_dynamic_core_proposal.md) — native 3.0: ordinary functions and closures, strict boundary schemas, fresh-only runs (§9); other sections are earlier proposal context. *Implemented (§9).*
- [provider_result_delivery.md](provider_result_delivery.md) — composed-provider result delivery shared by 2.35/2.36 and 3.0. *Implemented.*
- [workflow_lisp_write_once.md](workflow_lisp_write_once.md) — stating each fact once; W3 local hooks at 2.36, other rules proposed. *Partial.*

## Language features

- [workflow_lisp_strict_boolean_control_flow.md](workflow_lisp_strict_boolean_control_flow.md) — exact-`Bool` `if`/`cond`, short-circuit effects and `.variant` proof (2.26). *Implemented.*
- [workflow_lisp_numeric_surface.md](workflow_lisp_numeric_surface.md) — decimal literals, float operators and finite boundary values (2.34). *Implemented.*
- [workflow_lisp_pure_call_composition.md](workflow_lisp_pure_call_composition.md) — inline effect-free helper calls inside expressions (2.30). *Implemented.*
- [workflow_lisp_pure_list_traversal.md](workflow_lisp_pure_list_traversal.md) — list construction, `list/map`, serial `list/map-effect`, list loop state (2.18). *Implemented.*
- [workflow_lisp_transportable_value_type.md](workflow_lisp_transportable_value_type.md) — opaque strict-JSON `Value` type (2.19). *Implemented.*
- [workflow_lisp_native_transportable_returns.md](workflow_lisp_native_transportable_returns.md) — direct transportable returns and typed result guidance (2.15). *Implemented.*
- [workflow_lisp_value_and_continuation_composition.md](workflow_lisp_value_and_continuation_composition.md) — whole-union inputs, rich loop state, pure calls, portable context and host input (2.28–2.32). *Implemented.*
- [workflow_lisp_composition_first.md](workflow_lisp_composition_first.md) — generic unions and value-returning `std/improve` (2.33); its effect rules are not implemented. *Partial.*
- [workflow_lisp_parametric_type_system.md](workflow_lisp_parametric_type_system.md) — generics, structural constraints and specialization. *Partial.*
- [workflow_lisp_proc_refs_partial_application.md](workflow_lisp_proc_refs_partial_application.md) — compile-time `ProcRef` and `bind-proc`. *Implemented.*
- [workflow_lisp_let_proc_local_proc_refs.md](workflow_lisp_let_proc_local_proc_refs.md) — local `let-proc` bindings, extended by W3 at 2.36. *Implemented.*
- [workflow_lisp_macro_surface_contract.md](workflow_lisp_macro_surface_contract.md) — current macro surface and provenance rules. *Implemented.*
- [workflow_lisp_procedure_first_reuse_contract.md](workflow_lisp_procedure_first_reuse_contract.md) — procedures for internal reuse, workflows as public boundaries; some adapters remain workflows. *Partial.*
- [workflow_lisp_effect_graph.md](workflow_lisp_effect_graph.md) — keeping imported and procedural effects visible after lowering. *Partial.*
- [workflow_lisp_proof_graph.md](workflow_lisp_proof_graph.md) — why a variant-specific value is available at a use site. *Partial.*
- [workflow_lisp_type_catalog.md](workflow_lisp_type_catalog.md) — mapping frontend types to contracts, bundle schemas and IR values. *Partial.*
- [workflow_lisp_reference_catalog.md](workflow_lisp_reference_catalog.md) — one registry of values that workflow references can address. *Partial.*
- [workflow_lisp_stdlib_lowering.md](workflow_lisp_stdlib_lowering.md) — when a high-level form is stdlib code versus a compiler primitive. *Partial.*
- [workflow_lisp_generic_core_expression_surface_adapter_retirement.md](workflow_lisp_generic_core_expression_surface_adapter_retirement.md) — rationale for pure-expression operators, typed projection, views, typed transitions and adapter retirement. *Implemented.*
- [workflow_lisp_review_revise_stdlib_parametric_integration.md](workflow_lisp_review_revise_stdlib_parametric_integration.md) — `review-revise-loop` as ordinary `std/phase` stdlib code. *Implemented.*
- [workflow_lisp_unified_frontend_design.md](workflow_lisp_unified_frontend_design.md) — future frontend surfaces; its `let-proc` part is implemented, the rest is not. *Partial.*

## Providers and prompts

- [workflow_lisp_prompt_calculus.md](workflow_lisp_prompt_calculus.md) — `defprompt` fragments, `:path :out` output positions and attempt diagnostics (2.20–2.22). *Implemented.*
- [workflow_lisp_prompt_identity_diagnostics.md](workflow_lisp_prompt_identity_diagnostics.md) — content-free prompt-attempt identity and drift reports (2.22). *Implemented.*
- [workflow_lisp_judgment_views.md](workflow_lisp_judgment_views.md) — read-only judgment views for the explicit-composed review panel (2.23). *Implemented.*
- [workflow_lisp_phased_contract_delivery.md](workflow_lisp_phased_contract_delivery.md) — separate task and materialization phases for one prompt (2.23). *Implemented.*
- [workflow_lisp_provider_live_binding.md](workflow_lisp_provider_live_binding.md) — one worker plus one supervisor with turn-boundary steering (2.16). *Implemented.*
- [workflow_lisp_provider_peer_messaging.md](workflow_lisp_provider_peer_messaging.md) — static 2–8 member peer groups with recorded messages (2.17). *Implemented.*
- [workflow_lisp_provider_context_values.md](workflow_lisp_provider_context_values.md) — first-class provider context; portable Codex subset at 2.31, native continuation proposed. *Partial.*
- [workflow_lisp_private_runtime_state_and_consumer_value_flow.md](workflow_lisp_private_runtime_state_and_consumer_value_flow.md) — private checkpoints and typed values rendered at consumers; default resume and basic provider-input rendering run. *Partial.*
- [workflow_lisp_consumer_side_rendering.md](workflow_lisp_consumer_side_rendering.md) — rendering typed values at consumer seams; provider prompt inputs run, other seams do not. *Partial.*

## Commands, state and runtime contracts

- [workflow_command_adapter_contract.md](workflow_command_adapter_contract.md) — certified versus legacy command adapters and inline glue policy. *Partial.*
- [workflow_lisp_legacy_adapter.md](workflow_lisp_legacy_adapter.md) — quarantine boundary for old scripts and pointer conventions. *Partial.*
- [workflow_lisp_runtime_migration_foundation.md](workflow_lisp_runtime_migration_foundation.md) — structured command outputs, typed value transport and generated path allocation. *Implemented.*
- [workflow_lisp_generic_resource_context_core.md](workflow_lisp_generic_resource_context_core.md) — generic runtime core (`RunCtx`, `Resource`, `Transition`) with library contexts on top. *Implemented.*
- [workflow_lisp_state_layout.md](workflow_lisp_state_layout.md) — generated state, bundle and artifact paths from `RunCtx`/`ItemCtx`. *Partial.*
- [workflow_lisp_lexical_execution_checkpoints.md](workflow_lisp_lexical_execution_checkpoints.md) — private lexical checkpoints and resume policy; default resume runs. *Partial.*
- [workflow_lisp_pure_result_replay.md](workflow_lisp_pure_result_replay.md) — transient pure values with persisted completion shells on typed flat runs. *Implemented.*
- [resume_projection_integrity_hardening.md](resume_projection_integrity_hardening.md) — checksum audit of the root and reached callees on resume. *Implemented.*
- [workflow_lisp_procedure_migration_identity_compatibility.md](workflow_lisp_procedure_migration_identity_compatibility.md) — strict checksum identity when a workflow becomes a procedure; the retirement generator it specifies was removed. *Partial.*
- [workflow_lisp_trial_runs.md](workflow_lisp_trial_runs.md) — direct-task control, pinned `run-ref` children and blinded trials; the external-controller method is not built. *Partial.*
- [dsl_v214_materialization_variants_draft.md](dsl_v214_materialization_variants_draft.md) — `materialize_artifacts`, `pre_snapshot` and variant outputs (2.14). *Implemented.*
- [dsl_v214_variant_surface_decision.md](dsl_v214_variant_surface_decision.md) — why `variant_output` is separate from `output_bundle` (2.14). *Implemented.*
- [dsl_v214_pointer_authority.md](dsl_v214_pointer_authority.md) — one canonical pointer per published relpath artifact (2.14). *Implemented.*
- [neurips_v214_behavior_matrix.md](neurips_v214_behavior_matrix.md) — oracle scenarios pinning drain behavior around 2.14, run by `tests/test_v214_primitive_oracle.py`. *Implemented.*

## Compiler internals

- [workflow_lisp_core_calculus_middle_end.md](workflow_lisp_core_calculus_middle_end.md) — WCC core calculus and middle-end; schema 2 for the migrated route subset. *Partial.*
- [workflow_lisp_semantic_workflow_ir.md](workflow_lisp_semantic_workflow_ir.md) — Semantic IR for compiled workflow meaning. *Implemented.*
- [workflow_lisp_executable_ir.md](workflow_lisp_executable_ir.md) — validated executable IR below the frontend. *Implemented.*
- [workflow_lisp_core_workflow_ast.md](workflow_lisp_core_workflow_ast.md) — Core Workflow AST between frontend and validation. *Implemented.*
- [workflow_lisp_core_stmt_taxonomy.md](workflow_lisp_core_stmt_taxonomy.md) — Core statement families and their semantics. *Implemented.*
- [workflow_lisp_source_map.md](workflow_lisp_source_map.md) — source provenance for generated steps, paths and result fields. *Implemented.*
- [workflow_lisp_debug_yaml_renderer.md](workflow_lisp_debug_yaml_renderer.md) — debug YAML view of generated workflows. *Implemented.*

## Tooling and observability

- [workflow_lisp_language_server.md](workflow_lisp_language_server.md) — `.orc` language server: diagnostics, symbols, completion, navigation. *Implemented.*
- [workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md](workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md) — current-only diagnostics and compile progress. *Implemented.*
- [workflow_lisp_lsp_authored_reference_navigation.md](workflow_lisp_lsp_authored_reference_navigation.md) — definition navigation for prompt heads and authored proc-refs. *Implemented.*
- [workflow_lisp_repl.md](workflow_lisp_repl.md) — REPL load, run, attach and pure evaluation for 2.35/2.36 and 3.0. *Implemented.*
- [workflow_lisp_repl_introspection.md](workflow_lisp_repl_introspection.md) — REPL declaration, source and type queries and result-file lookup. *Implemented.*
- [dashboard_observability_summary_gui.md](dashboard_observability_summary_gui.md) — dashboard page for a run's summary hub. *Implemented.*
- [dashboard_summary_invocation_tabs.md](dashboard_summary_invocation_tabs.md) — per-invocation panels in the dashboard summary hub. *Implemented.*
- [observability_step_visit_summaries.md](observability_step_visit_summaries.md) — one summary per executed step visit, not per step name. *Implemented.*

## Workflow families and applications

- [verified_iteration_drain.md](verified_iteration_drain.md) — fused-session select, plan, implement and verify drain (2.15). *Implemented.*
- [workflow_lisp_runtime_native_drain_authoring.md](workflow_lisp_runtime_native_drain_authoring.md) — target shape and regression checklist for runtime-native parent drains (the deprecated Design Delta family). *Partial.*
- [workflow_lisp_shared_owner_lane_prerequisites.md](workflow_lisp_shared_owner_lane_prerequisites.md) — contracts a workflow family needs before relying on imported `std/drain`, `std/phase` or `std/resource`. *Partial.*
- [mlevolve_workflow_lisp_system_architecture.md](mlevolve_workflow_lisp_system_architecture.md) — MLEvolve-style autonomous ML search workflow. *Design only.*
- [workflow_lisp_progressive_execution.md](workflow_lisp_progressive_execution.md) — goal-driven task refinement, workers, checks and replanning in plain `.orc`. *Design only.*
- [orc_reuse_introspection_search_experiment.md](orc_reuse_introspection_search_experiment.md) — research design for programmability, reuse, introspection, self-programming and optimization; some studies have run. *Partial.*

## Designed but not implemented

- [workflow_lisp_typed_program_gates.md](workflow_lisp_typed_program_gates.md) — full-compiler verdicts for generated programs, child-run adapters, eval terminal. *Design only.*
- [workflow_lisp_effect_ledger_simplification.md](workflow_lisp_effect_ledger_simplification.md) — optional, inferred effect restrictions. *Design only.*
- [workflow_lisp_provider_prompt_queue.md](workflow_lisp_provider_prompt_queue.md) — `prompt-queue`: several turns in one native provider session. *Design only.*
- [workflow_lisp_runtime_closures_boundary.md](workflow_lisp_runtime_closures_boundary.md) — conditions for durable runtime closures in typed programs (native 3.0 closures are separate). *Design only.*
- [workflow_lisp_program_search_boundaries.md](workflow_lisp_program_search_boundaries.md) — invariants any future program-search feature must keep. *Design only.*

## History

- [workflow_lisp_frontend_mvp_specification.md](workflow_lisp_frontend_mvp_specification.md) — original MVP scope and deferrals. *Historical.*
- [workflow_lisp_post_foundation_composition_stdlib_migration.md](workflow_lisp_post_foundation_composition_stdlib_migration.md) — post-foundation composition and stdlib migration roadmap. *Historical.*
- [workflow_lisp_key_migration_parity_architecture.md](workflow_lisp_key_migration_parity_architecture.md) — YAML-to-`.orc` parity gates. *Historical.*
- [workflow_lisp_lexical_checkpoint_resumability.md](workflow_lisp_lexical_checkpoint_resumability.md) — early checkpoint note, replaced by the lexical execution checkpoints doc. *Historical.*
- [workflow_lisp_compile_time_parametric_specialization.md](workflow_lisp_compile_time_parametric_specialization.md) — replaced by the parametric type system. *Historical.*
- [workflow_lisp_structural_parametric_constraints.md](workflow_lisp_structural_parametric_constraints.md) — replaced by the parametric type system. *Historical.*
- [lisp_frontend_review_fix_loops.md](lisp_frontend_review_fix_loops.md) — review/fix loops of the retired YAML drain phases. *Historical.*
- [dsl_v214_yaml_ergonomics.md](dsl_v214_yaml_ergonomics.md) — YAML line-count analysis for the retired YAML frontend. *Historical.*
