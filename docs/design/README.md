# Design Documentation Index

Use this page to find component ownership. [Specs](../../specs/index.md) govern
runtime behavior; accepted component designs govern their stated language and
architecture boundaries. [Capability status](../capability_status_matrix.md)
and the [workflow catalog](../../workflows/README.md) determine availability and
copy safety. Implementation evidence and pending work live in each owner's
linked plan/report, rather than in this index.

[Evaluated execution](workflow_lisp_evaluated_execution.md) is the sole workflow
runtime. Current compilation, typed imports and REPL/LSP analysis require
registered source targets 2.35–2.39 throughout the dependency graph, including
retained typed-program capsules. Historical
feature-introduction versions do not restore old-source admission; retained
data readers remain independent of source compilation.
Targets 2.35/2.36 are admitted for their supported classes; 2.37 parallelism has
bounded qualification. The bounded 2.38 [Agent Sessions](workflow_lisp_agent_sessions.md)
and [command-only confined children](workflow_lisp_run_ref_expression_environments.md)
do not open public confined providers. See [CLI admission](../../specs/cli.md#executable-support-boundary)
and [retirement](workflow_lisp_executor_retirement.md). Target 2.39 adds
[inference-default procedure contracts](workflow_lisp_effect_ledger_simplification.md),
caller-owned composition and finite source admission; it changes no runtime
profile or qualification gate.

## Current Component Contracts

| Document | Purpose | Scope | Authoring use |
| --- | --- | --- | --- |
| [workflow_language_design_principles.md](workflow_language_design_principles.md) | Cross-frontend semantic authority principles | Current contract | Yes |
| [workflow_command_adapter_contract.md](workflow_command_adapter_contract.md) | Command adapter and inline glue policy | Partial; the command closure declaration (C1–C5) is enforced at run time at target 2.35 | Yes |
| [workflow_lisp_frontend_specification.md](workflow_lisp_frontend_specification.md) | Accepted Workflow Lisp frontend baseline | Current contract | Yes |
| [workflow_lisp_repl.md](workflow_lisp_repl.md) | Pure interactive inspection of admitted 2.35–2.39 source and evaluated runs | Current contract | No |
| [workflow_lisp_provider_prompt_dependencies.md](workflow_lisp_provider_prompt_dependencies.md) | Workflow Lisp provider prompt dependencies | Implemented functional contract | Yes |
| [workflow_lisp_provider_call_policy.md](workflow_lisp_provider_call_policy.md) | Explicit provider policy and registry binding | Implemented contract for admitted evaluated calls | Yes |
| [omp_provider_and_native_continuation.md](omp_provider_and_native_continuation.md) | OMP provider calls and existing native-session continuation | Partial; creation/import routes retired, OMP-I2 unselected | Within retained scope |
| [workflow_lisp_procedure_first_reuse_contract.md](workflow_lisp_procedure_first_reuse_contract.md) | Procedure-first boundary roles, lowering identity, effects, and migration rules | Accepted contract / adoption gated | No |
| [workflow_lisp_procedure_migration_identity_compatibility.md](workflow_lisp_procedure_migration_identity_compatibility.md) | Strict-default procedure-migration identity compatibility and bounded internal retirement | Accepted durable contract / historical generator and pilot evidence | No |
| [workflow_lisp_semantic_workflow_ir.md](workflow_lisp_semantic_workflow_ir.md) | Semantic IR authority surface | Partial: retained typed/shared-service scope | Only within evaluated admission |
| [workflow_lisp_macro_surface_contract.md](workflow_lisp_macro_surface_contract.md) | Current macro surface and provenance obligations | Current contract | Yes |
| [workflow_lisp_stdlib_lowering.md](workflow_lisp_stdlib_lowering.md) | Stdlib lowering boundary | Partial: retained typed/shared-service scope | Only within evaluated admission |
| [workflow_lisp_state_layout.md](workflow_lisp_state_layout.md) | Generated path and state layout ownership | Partial: retained typed/shared-service scope | Only within evaluated admission |
| [workflow_lisp_source_map.md](workflow_lisp_source_map.md) | Source-map provenance, including runtime structured-result field lineage | Partial: retained typed/shared-service scope | Only within evaluated admission |
| [workflow_lisp_effect_graph.md](workflow_lisp_effect_graph.md) | Effect visibility | Partial: retained typed/shared-service scope | Only within evaluated admission |
| [workflow_lisp_core_workflow_ast.md](workflow_lisp_core_workflow_ast.md) | Core Workflow AST | Partial: retained typed/shared-service scope | Only within evaluated admission |
| [workflow_lisp_core_stmt_taxonomy.md](workflow_lisp_core_stmt_taxonomy.md) | Core statement classification | Partial: retained typed/shared-service scope | Only within evaluated admission |
| [workflow_lisp_type_catalog.md](workflow_lisp_type_catalog.md) | Workflow Lisp type catalog | Partial | Yes |
| [workflow_lisp_reference_catalog.md](workflow_lisp_reference_catalog.md) | Workflow Lisp reference/catalog material | Partial | Yes |
| [workflow_lisp_proof_graph.md](workflow_lisp_proof_graph.md) | Variant proof and value authority | Partial | No |

## Migration Guidance

| Document | Purpose | Scope | Authoring use |
| --- | --- | --- | --- |
| [workflow_lisp_consolidation.md](workflow_lisp_consolidation.md) | Consolidation onto evaluated execution, shared contract extraction and old-route retirement | Implemented extraction and retired flat route; later capability gates remain separate | No new authoring surface |
| [workflow_lisp_executor_retirement.md](workflow_lisp_executor_retirement.md) | Complete serial best-of-N migration and delete old executors | Selected retirement complete; current execution and read-only historical scope | Use existing evaluated recipes |
| [provider_result_delivery.md](provider_result_delivery.md) | Output-contract delivery rendering on the evaluated route, the rendering replayed as recorded, the missing-result diagnostic, a typed inability channel | Yes for evaluated 2.35/2.36 runs | Yes; prompts carry no transport instructions |
| [workflow_lisp_runtime_migration_foundation.md](workflow_lisp_runtime_migration_foundation.md) | Runtime foundation for command outputs, private values, and generated paths | Partial: retained typed/shared-service scope | Only within evaluated admission |
| [workflow_lisp_core_calculus_middle_end.md](workflow_lisp_core_calculus_middle_end.md) | Workflow core calculus and compiler middle-end | Typed WCC, mandatory executable preparation and semantic closure; flat execution through 2.34 retired | No |
| [workflow_lisp_private_runtime_state_and_consumer_value_flow.md](workflow_lisp_private_runtime_state_and_consumer_value_flow.md) | Private runtime checkpoints and consumer-side typed-value rendering | Partial: narrow C1/C6 input carriage; C2–C5 and remaining C6 future; Track R historical | No |
| [workflow_lisp_runtime_native_drain_authoring.md](workflow_lisp_runtime_native_drain_authoring.md) | Runtime-native Workflow Lisp drain authoring | Historical reference target / regression checklist | No |
| [workflow_lisp_shared_owner_lane_prerequisites.md](workflow_lisp_shared_owner_lane_prerequisites.md) | Shared owner-lane prerequisites for imported stdlib adoption | Reference target / prerequisite ledger | No |
| [workflow_lisp_lexical_execution_checkpoints.md](workflow_lisp_lexical_execution_checkpoints.md) | Lexical execution checkpoints and durable resource resumability | Retained safety distinctions; historical checkpoint/resume architecture | No old-profile resume |
| [mlevolve_workflow_lisp_system_architecture.md](mlevolve_workflow_lisp_system_architecture.md) | MLEvolve-style Workflow Lisp workflow architecture | Draft design | No |
| [workflow_lisp_legacy_adapter.md](workflow_lisp_legacy_adapter.md) | Legacy adapter boundary | Partial: retained typed/shared-service scope | Only within evaluated admission |

## Frontend Design Direction

| Document | Purpose | Scope | Authoring use |
| --- | --- | --- | --- |
| [workflow_lisp_run_ref_expression_environments.md](workflow_lisp_run_ref_expression_environments.md) | Static named-workflow children, prepared clones and a Bubblewrap confinement profile | Partial at 2.38: command/recovery/export delivery accepted; private provider transport integrated; real qualification blocked | Bounded [command-only recipe](../lisp_workflow_drafting_guide.md#confined-workflow-children-target-238-command-only); full provider example not copy-safe |
| [workflow_lisp_checked_program_evaluation.md](workflow_lisp_checked_program_evaluation.md) | Generated source checked and evaluated through the existing compiler, evaluator and memo | Proposed; unselected, after 2.35 | No |
| [workflow_lisp_value_and_continuation_composition.md](workflow_lisp_value_and_continuation_composition.md) | Incremental union prompt inputs, rich loop values, helper composition, provider context, and human input | Current Increments 1–3; provider capture and host-input Increments 4–5 retired | Admitted evaluated union/loop/pure-helper forms |
| [workflow_lisp_progressive_execution.md](workflow_lisp_progressive_execution.md) | Agreed goal, just-in-time task refinement, tool-enabled workers, checks, and replanning | Draft design | No |
| [workflow_lisp_strict_boolean_control_flow.md](workflow_lisp_strict_boolean_control_flow.md) | Target-2.26 arbitrary strict-`Bool` `if` conditions, `cond`, effectful short-circuit normalization, and discriminant-derived union proof | Implemented strict Boolean/proof contract | Admitted 2.35–2.39 source; introduced at 2.26 |
| [workflow_lisp_effect_ledger_simplification.md](workflow_lisp_effect_ledger_simplification.md) | Target-2.39 inference-default optional identity-aware restrictions, explicit-empty specialization/import migration and inferred inspection | Implemented at 2.39 over the existing inferred summary; old definition origins retain their contracts | [2.39 procedure guide](../lisp_workflow_drafting_guide.md#procedure-contracts-at-target-239) and bounded maintained consumers |
| [workflow_lisp_write_once.md](workflow_lisp_write_once.md) | W3 local hooks, lexical captures/expected signatures and graph-selected no-context `improve`; other write-once proposals remain separate | W3 implemented at 2.36; W2 optional effects delivered by EL-1 at 2.39; W1/W4 and further trials remain unselected with their existing gates | Bounded proposal/reviewed-change recipes; evidence limits in closeout |
| [workflow_lisp_evaluated_execution.md](workflow_lisp_evaluated_execution.md) | Execution by evaluation of the compiled program: values in an environment, effect identity from site and activation path, an append-only memo of effects, resume by evaluation, declared command closures, a coordinator protocol, views derived from the memo, typed effect inputs, parallel map | Implemented admitted 2.35/2.36 classes; 2.37 parallel workers bounded, full public qualification pending | Use the drafting guide; later classes require their own admission |
| [workflow_lisp_numeric_surface.md](workflow_lisp_numeric_surface.md) | Decimal literals in expressions, closed decimal arithmetic, explicit conversion, finite values at every boundary | Implemented numeric contract; N4 runtime location and full-position test coverage remain limited | Admitted 2.35–2.39 source; introduced at 2.34 |
| [workflow_lisp_pure_call_composition.md](workflow_lisp_pure_call_composition.md) | Effect-free procedure expression composition through resolved inline normalization; effects, representation, and sequencing kept distinct | Implemented resolved-inline subset | Admitted 2.35–2.39 source; introduced at 2.30 |
| [workflow_lisp_composition_first.md](workflow_lisp_composition_first.md) | Value-returning procedures through first-order generic unions; ordinary `std/improve` helper and domain-owned migration adapters | Generic unions and value-returning std/improve implemented; consumer migration separate | Current 2.39 caller with W3 hooks and retained 2.35 library definitions; 2.33 source contract is historical |
| [workflow_lisp_native_transportable_returns.md](workflow_lisp_native_transportable_returns.md) | Uniform native returns and optional typed result guidance | Implemented typed return contract | Admitted 2.35–2.39 source; introduced at 2.15 |
| [workflow_lisp_transportable_value_type.md](workflow_lisp_transportable_value_type.md) | Opt-in transport-contract top `Value`, strict JSON wire validation, exact source compatibility, and target-gated public `type: value` / `kind: value` | Implemented | Yes in admitted 2.35–2.39 source; introduced at 2.19 |
| [workflow_lisp_agent_sessions.md](workflow_lisp_agent_sessions.md) | Stable run-scoped agent identity and interleaved native-session turns | First slice implemented at 2.38; PQ-1a evidence recorded; PQ-1c pending | Opt-in bounded first slice |
| [workflow_lisp_prompt_calculus.md](workflow_lisp_prompt_calculus.md) | Target-2.20 prompt core, target-2.21 output positions, and target-2.22 attempt diagnostics | Implemented | Yes for admitted evaluated bounded Q1–Q3 surfaces; old-profile diagnostic readers remain historical |
| [workflow_lisp_prompt_identity_diagnostics.md](workflow_lisp_prompt_identity_diagnostics.md) | Target-2.22 attempt-scoped, role-separated prompt identity and comparison diagnostics | Implemented | Yes for direct fragment-backed provider calls |
| [workflow_lisp_pure_list_traversal.md](workflow_lisp_pure_list_traversal.md) | Target-2.18 list construction/traversal, pure and bounded-effectful mapping, list loop state, and rooted path joining | Implemented | Yes in admitted 2.35–2.39 source; the 2.18 runtime recipe is history |
| [workflow_lisp_program_search_boundaries.md](workflow_lisp_program_search_boundaries.md) | Permanent boundary invariants for any future program-search/evolution feature | Adopted position statement | No |
| [workflow_lisp_trial_runs.md](workflow_lisp_trial_runs.md) | Canonical direct control, pinned child runs, blinded trials, and external-controller methodology | Partial: retained typed/shared-service scope | E0's evaluated bounded direct task and admitted path-mode run-ref only |
| [orc_reuse_introspection_search_experiment.md](orc_reuse_introspection_search_experiment.md) | Five independent axes, including ergonomic reuse of `.orc` | Research design; assisted C1 and qualitative assessment recorded, follow-on repair unselected | Normal coding-agent sessions for authoring; qualitative reuse assessment, not a portfolio-test proxy |
| [workflow_lisp_typed_program_gates.md](workflow_lisp_typed_program_gates.md) | C1 typed full-compiler verdicts, deferred C2 child-run adapters, and parked C3 eval terminal | Accepted; no implementation selected | No |
| [workflow_lisp_language_server.md](workflow_lisp_language_server.md) | `.orc` LSP server (editor diagnostics and navigation) | L0–L5 implemented; evaluated F2 OPEN_NOT_WAIVED; L6 unselected | Use the LSP setup guide |
| [workflow_lisp_proc_refs_partial_application.md](workflow_lisp_proc_refs_partial_application.md) | Compile-time ProcRefs and `bind-proc` | Current contract | Yes |
| [workflow_lisp_let_proc_local_proc_refs.md](workflow_lisp_let_proc_local_proc_refs.md) | Local compile-time procedure bindings | V1 implemented through 2.35; W3 implemented at 2.36 | Within the versioned contract and demonstrated W3 recipes |
| [workflow_lisp_parametric_type_system.md](workflow_lisp_parametric_type_system.md) | Parametric type system: generics, structural constraints, specialization, form-migration policy | Partial (tranche one landed) | No |
| [2026-06-19-workflow-lisp-type-runtime-boundary-issues.md](../reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md) | Historical diagnostic of the type/runtime contract-projection boundary | Historical (dispositioned 2026-07-08) | No |
| [workflow_lisp_runtime_closures_boundary.md](workflow_lisp_runtime_closures_boundary.md) | Runtime closure boundary | Future | No |
| [workflow_lisp_refactor_architecture.md](workflow_lisp_refactor_architecture.md) | Behavior-preserving frontend refactor architecture | Current contract | No |

## Runtime And Observability Direction

[REPL introspection](workflow_lisp_repl_introspection.md) owns module/source
inspection and static type/effect queries; use the [REPL recipe](../lisp_workflow_drafting_guide.md#inspect-a-run-with-the-workflow-lisp-repl).
[Provider-phase isolation](../superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md)
remains partial and pre-integration: standalone backend evidence does not provide
public run/resume, attestation or live qualification. Its [implementation plan](../superpowers/plans/2026-07-23-provider-phase-information-isolation.md)
owns those gates. Separate clones are experiment hygiene, not an OS boundary.

| Document | Purpose | Scope | Authoring use |
| --- | --- | --- | --- |
| [dashboard_observability_summary_gui.md](dashboard_observability_summary_gui.md) | Dashboard summary GUI | Designed/partial | No |
| [dashboard_summary_invocation_tabs.md](dashboard_summary_invocation_tabs.md) | Dashboard invocation tabs | Designed/partial | No |
| [observability_step_visit_summaries.md](observability_step_visit_summaries.md) | Step visit summary observability | Partial/unknown from this index; read the doc and linked evidence | No |

## Review And Workflow Families

| Document | Purpose | Scope | Authoring use |
| --- | --- | --- | --- |
| [verified_iteration_drain.md](verified_iteration_drain.md) | Verified-iteration drain: single fused-session select/plan/implement/verify loop | Implemented; Workflow Lisp primary | Yes |
| [orc_effectiveness_comparison_harness.md](orc_effectiveness_comparison_harness.md) | Comparing maintained `.orc` workflows with single agent calls (`experiments/compare/`) | Implemented (experiment apparatus) | No (not an authoring surface) |

## Historical Or Narrow Decision Notes

These records preserve decisions and evidence. Follow their current-owner
pointers; their original commands and status do not select work.

| Document | Purpose | Scope | Authoring use |
| --- | --- | --- | --- |
| [workflow_lisp_frontend_mvp_specification.md](workflow_lisp_frontend_mvp_specification.md) | Historical MVP tranche boundary | Historical; current owner linked in the record | No |
| [workflow_lisp_executable_ir.md](workflow_lisp_executable_ir.md) | Executable IR authority surface | Historical; current owner linked in the record | No |
| [workflow_lisp_debug_yaml_renderer.md](workflow_lisp_debug_yaml_renderer.md) | Debug YAML projection | Historical; current owner linked in the record | No |
| [workflow_lisp_key_migration_parity_architecture.md](workflow_lisp_key_migration_parity_architecture.md) | Historical YAML-to-`.orc` promotion and parity-gate design | Historical; current owner linked in the record | No |
| [workflow_lisp_post_foundation_composition_stdlib_migration.md](workflow_lisp_post_foundation_composition_stdlib_migration.md) | Historical post-foundation composition and stdlib migration roadmap | Historical; current owner linked in the record | No |
| [workflow_lisp_generic_resource_context_core.md](workflow_lisp_generic_resource_context_core.md) | Generic resource/context core for post-foundation Workflow Lisp | Historical; current owner linked in the record | No |
| [workflow_lisp_generic_core_expression_surface_adapter_retirement.md](workflow_lisp_generic_core_expression_surface_adapter_retirement.md) | Generic runtime core, pure expression surface, and Python adapter retirement | Historical; current owner linked in the record | No |
| [workflow_lisp_lexical_checkpoint_resumability.md](workflow_lisp_lexical_checkpoint_resumability.md) | Early lexical checkpoint resumability target | Historical; current owner linked in the record | No |
| [workflow_lisp_pure_result_replay.md](workflow_lisp_pure_result_replay.md) | M2 component-(a) value-free completion shells and deterministic pure-result replay | Historical; current owner linked in the record | No |
| [workflow_lisp_consumer_side_rendering.md](workflow_lisp_consumer_side_rendering.md) | Consumer-side rendering over the materialized-view kernel | Historical; current owner linked in the record | No |
| [dsl_v214_materialization_variants_draft.md](dsl_v214_materialization_variants_draft.md) | v2.14 materialization and variant outputs | Historical; current owner linked in the record | No |
| [dsl_v214_pointer_authority.md](dsl_v214_pointer_authority.md) | Pointer authority and artifact identity | Historical; current owner linked in the record | No |
| [dsl_v214_variant_surface_decision.md](dsl_v214_variant_surface_decision.md) | Variant-output surface decision | Historical; current owner linked in the record | No |
| [dsl_v214_yaml_ergonomics.md](dsl_v214_yaml_ergonomics.md) | Historical YAML ergonomics around v2.14 | Historical; current owner linked in the record | No |
| [workflow_lisp_unified_frontend_design.md](workflow_lisp_unified_frontend_design.md) | Future/deferred Workflow Lisp surfaces | Historical; current owner linked in the record | No |
| [Workflow Lisp evolution substrate and feature design](../superpowers/specs/2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md) | Compiler-certified immutable variants, context-stratified subject adjudication, inert fragment archives, role-separated prompt environments, prompt/code evolution, and the substrate/feature boundary | Historical; current owner linked in the record | No |
| [workflow_lisp_provider_prompt_queue.md](workflow_lisp_provider_prompt_queue.md) | Historical analysis of native transport and recovery within one queue effect | Historical; current owner linked in the record | No |
| [workflow_lisp_provider_context_values.md](workflow_lisp_provider_context_values.md) | First-class context, explicit transformations and rebinding | Historical execution; retained reader/shared-service scope only | No |
| [workflow_lisp_phased_contract_delivery.md](workflow_lisp_phased_contract_delivery.md) | Target-2.23 opt-in task/materialization delivery for one canonical fragment prompt | Historical execution; retained reader/shared-service scope only | No |
| [workflow_lisp_judgment_views.md](workflow_lisp_judgment_views.md) | Q4 read-only result-plus-Q3-provenance inspection and deterministic judgment views | Historical execution; retained reader/shared-service scope only | No |
| [workflow_lisp_provider_live_binding.md](workflow_lisp_provider_live_binding.md) | Live provider supervision through observation panes and one bounded provider-session correction | Historical execution; retained reader/shared-service scope only | No |
| [workflow_lisp_provider_peer_messaging.md](workflow_lisp_provider_peer_messaging.md) | Recorded turn-boundary peer messaging and static provider-peer groups | Historical execution; retained reader/shared-service scope only | No |
| [workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md](workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md) | L4 current-only diagnostic presentation and serialized compile progress | Historical; current owner linked in the record | No |
| [workflow_lisp_lsp_authored_reference_navigation.md](workflow_lisp_lsp_authored_reference_navigation.md) | L5 authored-to-authored definition navigation for prompt application heads plus the feasibility-admitted narrow direct-retained `proc-ref` shape | Historical; current owner linked in the record | No |
| [workflow_lisp_compile_time_parametric_specialization.md](workflow_lisp_compile_time_parametric_specialization.md) | Parametric specialization and monomorphic helpers | Historical; current owner linked in the record | No |
| [workflow_lisp_structural_parametric_constraints.md](workflow_lisp_structural_parametric_constraints.md) | Structural record/union constraints | Historical; current owner linked in the record | No |
| [workflow_lisp_review_revise_stdlib_parametric_integration.md](workflow_lisp_review_revise_stdlib_parametric_integration.md) | Review/revise stdlib integration with refactor and parametric prerequisites | Historical; current owner linked in the record | No |
| [resume_projection_integrity_hardening.md](resume_projection_integrity_hardening.md) | Checksum-compatible scoped resume projection-integrity auditing | Historical; current owner linked in the record | No |
| [neurips_v214_behavior_matrix.md](neurips_v214_behavior_matrix.md) | NeurIPS v2.14 behavior matrix | Historical; current owner linked in the record | No |
| [lisp_frontend_review_fix_loops.md](lisp_frontend_review_fix_loops.md) | Review/fix loop semantics | Historical; current owner linked in the record | No |
