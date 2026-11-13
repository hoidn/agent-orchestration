# Design Documentation Index

This page routes to design documents; it defines no rule. [Specs](../../specs/index.md) govern
runtime and DSL behavior and the documents under "Read first" and "Feature contracts" own their
stated language and architecture contracts. "Tooling, compiler internals and research apparatus"
also lists internal pages and closed migration designs whose rules a later task checks; the
fourth part holds proposals and accepted designs that have not landed. The
[capability matrix](../capability_status_matrix.md) and [workflow catalog](../../workflows/README.md)
say what is available and copy-safe. Admission of source targets is in the
[CLI contract](../../specs/cli.md#executable-support-boundary). Every file of this directory is listed
once, in one of five parts. The [design corpus consolidation plan](../plans/2026-11-13-workflow-lisp-design-corpus-consolidation-plan.md)
moves documents between parts; its [rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md)
shows where the rules of each retired document went.

An author reads the [tutorial](../tutorial_first_pipeline.md), the
[drafting guide](../lisp_workflow_drafting_guide.md), the frontend specification and the
[library reference](../lisp_library_reference.md), in that order.

## Read First

| Document | What it owns | Status |
| --- | --- | --- |
| [workflow_lisp_frontend_specification.md](workflow_lisp_frontend_specification.md) | The Workflow Lisp language reference | Current contract |
| [workflow_lisp_evaluated_execution.md](workflow_lisp_evaluated_execution.md) | The sole workflow runtime: evaluation, effect identity, the memo, resume, command closures, coordinators, parallel map | Current contract |
| [workflow_language_design_principles.md](workflow_language_design_principles.md) | Cross-frontend semantic authority principles | Design guidance |
| [workflow_command_adapter_contract.md](workflow_command_adapter_contract.md) | Command boundaries, static argv, closures, adapters | Current contract |
| [workflow_lisp_executor_retirement.md](workflow_lisp_executor_retirement.md) | The 2.35 source floor, old-executor retirement and recovery policy | Current contract |

## Feature Contracts

Read the one for a feature when you use it.

| Document | What it owns | Status |
| --- | --- | --- |
| [workflow_lisp_durable_host_input.md](workflow_lisp_durable_host_input.md) | Typed host requests, settlement and resume (`request-input`) | Current contract, target 2.40 |
| [workflow_lisp_agent_sessions.md](workflow_lisp_agent_sessions.md) | Run-scoped agent identity and native-session turns (`agent`) | First slice implemented at 2.38 |
| [workflow_lisp_parametric_type_system.md](workflow_lisp_parametric_type_system.md) | Generics, structural constraints, specialization | Partial (tranche one) |
| [workflow_lisp_composition_first.md](workflow_lisp_composition_first.md) | Generic unions and the `std/improve` helper | Implemented |
| [workflow_lisp_phased_contract_delivery.md](workflow_lisp_phased_contract_delivery.md#target-239-evaluated-migration) | Phased provider delivery and its recovery | Accepted 2.39 contract; paid qualification unselected |
| [workflow_lisp_run_ref_expression_environments.md](workflow_lisp_run_ref_expression_environments.md) | Static named-workflow children and command-only confinement | Partial at 2.38; provider confinement dropped |
| [workflow_lisp_provider_call_policy.md](workflow_lisp_provider_call_policy.md) | Provider policy and registry binding | Implemented |
| [workflow_lisp_provider_prompt_dependencies.md](workflow_lisp_provider_prompt_dependencies.md) | `:prompt-dependencies` | Implemented |
| [provider_result_delivery.md](provider_result_delivery.md) | Result type shapes, delivery rendering, the inability channel | Implemented |
| [python_workflow_frontend.md](python_workflow_frontend.md) | Typed Python generation into checked `.orc` | Serial subset implemented; [guide](../python_workflow_drafting_guide.md) |
| [omp_provider_and_native_continuation.md](omp_provider_and_native_continuation.md) | OMP provider calls and native-session continuation | Partial; creation and import routes retired |
| [verified_iteration_drain.md](verified_iteration_drain.md) | The verified-iteration drain workflow | Implemented |
| [workflow_lisp_program_search_boundaries.md](workflow_lisp_program_search_boundaries.md) | Boundary invariants for program search and evolution | Adopted position statement |
| [workflow_lisp_runtime_closures_boundary.md](workflow_lisp_runtime_closures_boundary.md) | The runtime-closure boundary | Deferred acceptance guardrail |
| [workflow_lisp_macro_surface_contract.md](workflow_lisp_macro_surface_contract.md) | `defmacro` | Current contract |
| [workflow_lisp_strict_boolean_control_flow.md](workflow_lisp_strict_boolean_control_flow.md) | Strict `Bool` conditions, `cond`, discriminant proof | Implemented |
| [workflow_lisp_native_transportable_returns.md](workflow_lisp_native_transportable_returns.md) | Native returns and `(result T ...)` guidance | Implemented |
| [workflow_lisp_numeric_surface.md](workflow_lisp_numeric_surface.md) | Decimal literals and arithmetic | Implemented |
| [workflow_lisp_transportable_value_type.md](workflow_lisp_transportable_value_type.md) | The transport type `Value` | Implemented |
| [workflow_lisp_pure_call_composition.md](workflow_lisp_pure_call_composition.md) | Effect-free procedure calls in expressions | Implemented |
| [workflow_lisp_pure_list_traversal.md](workflow_lisp_pure_list_traversal.md) | List construction, mapping, `path/join-under` | Implemented |
| [workflow_lisp_proc_refs_partial_application.md](workflow_lisp_proc_refs_partial_application.md) | `ProcRef` and `bind-proc` | Current contract |
| [workflow_lisp_let_proc_local_proc_refs.md](workflow_lisp_let_proc_local_proc_refs.md) | `let-proc` local procedure bindings | Implemented; W3 at 2.36 |
| [workflow_lisp_write_once.md](workflow_lisp_write_once.md) | W3 local hooks and graph-selected `improve` | W3 implemented at 2.36; other parts unselected or dropped |
| [workflow_lisp_effect_ledger_simplification.md](workflow_lisp_effect_ledger_simplification.md) | Inference-default procedure effects | Implemented at 2.39 |
| [workflow_lisp_procedure_first_reuse_contract.md](workflow_lisp_procedure_first_reuse_contract.md) | Procedure boundary roles, lowering identity, effects | Accepted; adoption gated |
| [workflow_lisp_value_and_continuation_composition.md](workflow_lisp_value_and_continuation_composition.md) | Union prompt inputs, rich loop values, helper composition | Current for Increments 1–3 |
| [workflow_lisp_prompt_calculus.md](workflow_lisp_prompt_calculus.md) | Prompt core, output positions, attempt diagnostics (Q1–Q3) | Implemented |
| [workflow_lisp_prompt_identity_diagnostics.md](workflow_lisp_prompt_identity_diagnostics.md) | Prompt-attempt identity and comparison | Implemented |

## Tooling, Compiler Internals And Research Apparatus

| Document | What it owns | Status |
| --- | --- | --- |
| [workflow_lisp_language_server.md](workflow_lisp_language_server.md) | The `.orc` language server | L0–L5 implemented |
| [workflow_lisp_repl.md](workflow_lisp_repl.md) | The REPL over source and evaluated runs | Implemented |
| [workflow_lisp_repl_introspection.md](workflow_lisp_repl_introspection.md) | REPL module, type and effect queries | Implemented |
| [workflow_lisp_source_site_inspection.md](workflow_lisp_source_site_inspection.md) | Read-only source-site manifest for program search | Implemented offline; unselected for live use |
| [workflow_lisp_core_calculus_middle_end.md](workflow_lisp_core_calculus_middle_end.md) | WCC elaboration, normalization, scope, effect and proof analysis | Accepted architecture |
| [workflow_lisp_effect_graph.md](workflow_lisp_effect_graph.md) | Effect visibility | Current-checkout component contract; rule check pending |
| [workflow_lisp_proof_graph.md](workflow_lisp_proof_graph.md) | Variant proof and value authority | Current typed proof contract; rule check pending |
| [workflow_lisp_type_catalog.md](workflow_lisp_type_catalog.md) | Type catalog | Current shared typed catalog; rule check pending |
| [workflow_lisp_reference_catalog.md](workflow_lisp_reference_catalog.md) | Reference kinds | Current reference-kind contract; rule check pending |
| [workflow_lisp_source_map.md](workflow_lisp_source_map.md) | Source-map provenance | Accepted; rule check pending |
| [workflow_lisp_legacy_adapter.md](workflow_lisp_legacy_adapter.md) | Legacy adapter boundary | Current adapter-quarantine policy; rule check pending |
| [observability_step_visit_summaries.md](observability_step_visit_summaries.md) | Step visit summaries | Partial; dashboard pages removed |
| [orc_effectiveness_comparison_harness.md](orc_effectiveness_comparison_harness.md) | Comparing `.orc` workflows with single agent calls | Implemented apparatus |
| [orc_structural_search_driver.md](orc_structural_search_driver.md) | The structural search driver | Partial apparatus, offline |
| [orc_structural_search_cumulative_campaigns.md](orc_structural_search_cumulative_campaigns.md) | Cumulative multi-generation search campaigns | Partial, offline |
| [orc_reuse_introspection_search_experiment.md](orc_reuse_introspection_search_experiment.md) | Reuse and introspection research axes | Research design; follow-on unselected |
| [workflow_lisp_procedure_migration_identity_compatibility.md](workflow_lisp_procedure_migration_identity_compatibility.md) | Procedure-migration identity compatibility | Durable principles; generator historical; closed migration design, rule check pending |
| [workflow_lisp_consolidation.md](workflow_lisp_consolidation.md) | Ownership after consolidation onto evaluated execution | Extraction implemented; closed migration design, rule check pending |
| [workflow_lisp_runtime_migration_foundation.md](workflow_lisp_runtime_migration_foundation.md) | Command outputs, private values, generated paths | Partial; closed migration design, rule check pending |
| [workflow_lisp_private_runtime_state_and_consumer_value_flow.md](workflow_lisp_private_runtime_state_and_consumer_value_flow.md) | Private runtime checkpoints and consumer-side rendering | Partial; C2–C6 dropped; closed migration design, rule check pending |

## Proposals And Designs Not Yet Landed

| Document | What it proposes | Status |
| --- | --- | --- |
| [workflow_lisp_checked_program_evaluation.md](workflow_lisp_checked_program_evaluation.md) | Generated source checked and evaluated through the existing compiler | Proposed; parked 2026-11-11 |
| [workflow_lisp_progressive_execution.md](workflow_lisp_progressive_execution.md) | Agreed goal, task refinement, replanning | Draft; not implemented |
| [workflow_lisp_typed_program_gates.md](workflow_lisp_typed_program_gates.md) | Typed compiler verdicts and child-run adapters | C2 dropped, C1 and C3 parked |
| [Provider-phase isolation](../superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md) | Information isolation between provider phases | Partial, pre-integration; remaining integration dropped or archived ([roadmap](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#dispositions)) |
| [workflow_lisp_edit_and_continue.md](workflow_lisp_edit_and_continue.md) | Resume under an edited program | Accepted for implementation; evaluated execution and `specs/cli.md` own resume until it lands |
| [workflow_lisp_surface_coherence.md](workflow_lisp_surface_coherence.md) | One rule each for effect placement, iteration forms and callables | Accepted for implementation; the specification describes what compiles today |
| [mlevolve_workflow_lisp_system_architecture.md](mlevolve_workflow_lisp_system_architecture.md) | An MLEvolve-style workflow | Never built; dropped 2026-11-11; stays current until the module-path rule has an owner ([rule ledger 6.6](../reports/2026-11-13-design-corpus-rule-ledger.md#mlevolve_workflow_lisp_system_architecture-not-retired)) |

## Historical

These records preserve decisions and evidence and select no work. Follow the owner each one names.

| Document | What it was | Current owner |
| --- | --- | --- |
| [workflow_lisp_edit_and_continue_spike.md](workflow_lisp_edit_and_continue_spike.md) | Feasibility spike for edit and continue | [Evaluated execution](workflow_lisp_evaluated_execution.md#81-what-the-memo-decides); [State, memo records](../../specs/state.md#memo-records) |
| [workflow_lisp_frontend_deduplication.md](workflow_lisp_frontend_deduplication.md) | Argv, host-input and closure deduplication decisions | [Command adapter contract](workflow_command_adapter_contract.md#static-command-argv); [durable host input](workflow_lisp_durable_host_input.md) |
| [workflow_lisp_refactor_architecture.md](workflow_lisp_refactor_architecture.md) | The June 2026 frontend refactor architecture | [Core calculus](workflow_lisp_core_calculus_middle_end.md#current-ownership-and-invariants); [code map](../../orchestrator/workflow_lisp/README.md#pipeline) |
| [workflow_lisp_shared_owner_lane_prerequisites.md](workflow_lisp_shared_owner_lane_prerequisites.md) | Adoption gates for the removed `std/drain` and `std/resource` | [Frontend specification §6](workflow_lisp_frontend_specification.md#6-name-resolution) and [§11](workflow_lisp_frontend_specification.md#11-pattern-matching) |
| [workflow_lisp_trial_runs.md](workflow_lisp_trial_runs.md) | The removed `trial` platform | [Evaluated execution §1.2](workflow_lisp_evaluated_execution.md#12-ordinary-path-run-reference-placement-at-235); [comparison harness](orc_effectiveness_comparison_harness.md) (reusable decisions: [salvage record](trial_and_adjudication_salvage.md)) |
| [workflow_lisp_judgment_views.md](workflow_lisp_judgment_views.md) | Q4 judgment views, removed | [Observability](../../specs/observability.md#workflow-lisp-judgment-views-historical) |
| [workflow_lisp_lexical_execution_checkpoints.md](workflow_lisp_lexical_execution_checkpoints.md) | The predecessor checkpoint architecture | [State](../../specs/state.md#state-integrity-and-recovery) |
| [workflow_lisp_provider_live_binding.md](workflow_lisp_provider_live_binding.md) | Live provider supervision, removed | [Providers](../../specs/providers.md) (reusable design: [salvage record](live_provider_supervision_and_peers_salvage.md)) |
| [workflow_lisp_provider_peer_messaging.md](workflow_lisp_provider_peer_messaging.md) | Provider peer groups, removed | [Providers](../../specs/providers.md) (reusable design: [salvage record](live_provider_supervision_and_peers_salvage.md)) |
| [workflow_lisp_provider_context_values.md](workflow_lisp_provider_context_values.md) | First-class provider context | Linked in the record |
| [workflow_lisp_provider_prompt_queue.md](workflow_lisp_provider_prompt_queue.md) | Native transport within one queue effect | Linked in the record |
| [workflow_lisp_runtime_native_drain_authoring.md](workflow_lisp_runtime_native_drain_authoring.md) | Drain authoring; its forms removed | Linked in the record |
| [workflow_lisp_stdlib_lowering.md](workflow_lisp_stdlib_lowering.md) | Stdlib lowering; its forms removed | Linked in the record |
| [workflow_lisp_semantic_workflow_ir.md](workflow_lisp_semantic_workflow_ir.md) | Semantic IR; code removed | Linked in the record |
| [workflow_lisp_executable_ir.md](workflow_lisp_executable_ir.md) | Executable IR | Linked in the record |
| [workflow_lisp_state_layout.md](workflow_lisp_state_layout.md) | Generated path and state layout; code removed | Linked in the record |
| [workflow_lisp_core_workflow_ast.md](workflow_lisp_core_workflow_ast.md) | Core Workflow AST; code removed | Linked in the record |
| [workflow_lisp_core_stmt_taxonomy.md](workflow_lisp_core_stmt_taxonomy.md) | Core statement classification; code removed | Linked in the record |
| [workflow_lisp_debug_yaml_renderer.md](workflow_lisp_debug_yaml_renderer.md) | Debug YAML projection | Linked in the record |
| [workflow_lisp_frontend_mvp_specification.md](workflow_lisp_frontend_mvp_specification.md) | MVP tranche boundary | Linked in the record |
| [workflow_lisp_unified_frontend_design.md](workflow_lisp_unified_frontend_design.md) | Deferred frontend surfaces | Linked in the record |
| [workflow_lisp_key_migration_parity_architecture.md](workflow_lisp_key_migration_parity_architecture.md) | YAML-to-`.orc` promotion and parity gates | Linked in the record |
| [workflow_lisp_post_foundation_composition_stdlib_migration.md](workflow_lisp_post_foundation_composition_stdlib_migration.md) | Post-foundation stdlib migration roadmap | Linked in the record |
| [workflow_lisp_generic_resource_context_core.md](workflow_lisp_generic_resource_context_core.md) | Generic resource and context core | Linked in the record |
| [workflow_lisp_generic_core_expression_surface_adapter_retirement.md](workflow_lisp_generic_core_expression_surface_adapter_retirement.md) | Generic runtime core and adapter retirement | Linked in the record |
| [workflow_lisp_lexical_checkpoint_resumability.md](workflow_lisp_lexical_checkpoint_resumability.md) | Early checkpoint resumability target | Linked in the record |
| [workflow_lisp_pure_result_replay.md](workflow_lisp_pure_result_replay.md) | Pure-result replay | Linked in the record |
| [workflow_lisp_consumer_side_rendering.md](workflow_lisp_consumer_side_rendering.md) | Consumer-side rendering | Linked in the record |
| [workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md](workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md) | LSP L4 diagnostic lifecycle | Linked in the record |
| [workflow_lisp_lsp_authored_reference_navigation.md](workflow_lisp_lsp_authored_reference_navigation.md) | LSP L5 reference navigation | Linked in the record |
| [workflow_lisp_compile_time_parametric_specialization.md](workflow_lisp_compile_time_parametric_specialization.md) | Parametric specialization | Linked in the record |
| [workflow_lisp_structural_parametric_constraints.md](workflow_lisp_structural_parametric_constraints.md) | Structural record and union constraints | Linked in the record |
| [workflow_lisp_review_revise_stdlib_parametric_integration.md](workflow_lisp_review_revise_stdlib_parametric_integration.md) | Review/revise stdlib integration | Linked in the record |
| [live_provider_supervision_and_peers_salvage.md](live_provider_supervision_and_peers_salvage.md) | Salvage record of supervision and peer groups | None; an unscheduled future direction |
| [trial_and_adjudication_salvage.md](trial_and_adjudication_salvage.md) | Salvage record of `trial` and adjudication | [Comparison harness](orc_effectiveness_comparison_harness.md) |
| [dashboard_observability_summary_gui.md](dashboard_observability_summary_gui.md) | Dashboard summary GUI | Linked in the record |
| [dashboard_summary_invocation_tabs.md](dashboard_summary_invocation_tabs.md) | Dashboard invocation tabs; never implemented | Linked in the record |
| [resume_projection_integrity_hardening.md](resume_projection_integrity_hardening.md) | Resume projection-integrity auditing | Linked in the record |
| [lisp_frontend_review_fix_loops.md](lisp_frontend_review_fix_loops.md) | Review/fix loop semantics | Linked in the record |
| [dsl_v214_materialization_variants_draft.md](dsl_v214_materialization_variants_draft.md) | v2.14 materialization and variant outputs | Linked in the record |
| [dsl_v214_pointer_authority.md](dsl_v214_pointer_authority.md) | Pointer authority and artifact identity | Linked in the record |
| [dsl_v214_variant_surface_decision.md](dsl_v214_variant_surface_decision.md) | Variant-output surface decision | Linked in the record |
| [dsl_v214_yaml_ergonomics.md](dsl_v214_yaml_ergonomics.md) | YAML ergonomics around v2.14 | Linked in the record |
| [neurips_v214_behavior_matrix.md](neurips_v214_behavior_matrix.md) | NeurIPS v2.14 behavior matrix | Linked in the record |
| [Evolution substrate and feature design](../superpowers/specs/2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md) | Variant substrate and evolution features (outside this directory) | Linked in the record |
| [Type/runtime boundary issues](../reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md) | Diagnostic of the type/runtime boundary (a report) | Dispositioned 2026-07-08 |
