# Design Documentation Index

Status: informative design-doc curator
Normative authority: `specs/` for runtime behavior; current component docs for accepted frontend contracts

This page helps readers distinguish current contracts, migration guidance,
frontend direction, future/deferred work, and historical notes. It is a routing
page, not a replacement for the linked docs.

## Current Component Contracts

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [workflow_language_design_principles.md](workflow_language_design_principles.md) | Cross-frontend semantic authority principles | Yes | Yes | Use for design judgment before changing DSL, Workflow Lisp, or workflow abstractions. |
| [workflow_command_adapter_contract.md](workflow_command_adapter_contract.md) | Command adapter and inline glue policy | Partial | Yes | Use when deciding whether command behavior is a certified adapter, legacy adapter, or runtime-native candidate. |
| [workflow_lisp_frontend_specification.md](workflow_lisp_frontend_specification.md) | Accepted Workflow Lisp frontend baseline | Yes | Yes | Parent contract for `.orc` frontend work. |
| [workflow_lisp_frontend_mvp_specification.md](workflow_lisp_frontend_mvp_specification.md) | MVP Workflow Lisp tranche | Yes | Yes | Useful for minimal implemented surface and MVP boundaries. |
| [workflow_lisp_semantic_workflow_ir.md](workflow_lisp_semantic_workflow_ir.md) | Semantic IR authority surface | Yes | No | Implementation/verification contract, not an authoring guide. |
| [workflow_lisp_executable_ir.md](workflow_lisp_executable_ir.md) | Executable IR authority surface | Yes | No | Implementation/verification contract below the frontend. |
| [workflow_lisp_macro_surface_contract.md](workflow_lisp_macro_surface_contract.md) | Current macro surface and provenance obligations | Yes | Yes | Use for current macro behavior, not future macro ambitions. |
| [workflow_lisp_stdlib_lowering.md](workflow_lisp_stdlib_lowering.md) | Stdlib lowering boundary | Partial | Yes | Explains when high-level forms should be stdlib composition rather than compiler primitives. |
| [workflow_lisp_state_layout.md](workflow_lisp_state_layout.md) | Generated path and state layout ownership | Partial | No | Use when generated paths, loop roots, and resume identities are involved. |
| [workflow_lisp_source_map.md](workflow_lisp_source_map.md) | Source-map provenance | Yes | No | Use when generated steps, fields, or paths need source ownership. |
| [workflow_lisp_debug_yaml_renderer.md](workflow_lisp_debug_yaml_renderer.md) | Debug YAML projection | Yes | No | Debug YAML is a view, not execution authority. |
| [workflow_lisp_effect_graph.md](workflow_lisp_effect_graph.md) | Effect visibility | Partial | No | Use when imported/procedural effects must remain visible after lowering. |
| [workflow_lisp_core_workflow_ast.md](workflow_lisp_core_workflow_ast.md) | Core Workflow AST | Yes | No | Implementation boundary between frontend and validation/runtime layers. |
| [workflow_lisp_core_stmt_taxonomy.md](workflow_lisp_core_stmt_taxonomy.md) | Core statement classification | Yes | No | Helps classify statement ownership and lowering expectations. |
| [workflow_lisp_type_catalog.md](workflow_lisp_type_catalog.md) | Workflow Lisp type catalog | Partial | Yes | Read with the frontend specification for current type forms. |
| [workflow_lisp_reference_catalog.md](workflow_lisp_reference_catalog.md) | Workflow Lisp reference/catalog material | Partial | Yes | Routing/reference aid for implemented and planned language surfaces. |
| [workflow_lisp_proof_graph.md](workflow_lisp_proof_graph.md) | Variant proof and value authority | Partial | No | Use when variant-specific values or proof scopes are changing. |

## Migration Guidance

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [workflow_lisp_key_migration_parity_architecture.md](workflow_lisp_key_migration_parity_architecture.md) | YAML-to-`.orc` promotion and parity gates | Partial | Yes | Promotion requires computed evidence, not just compile/dry-run success. |
| [workflow_lisp_runtime_migration_foundation.md](workflow_lisp_runtime_migration_foundation.md) | Runtime foundation for promotion gates, command outputs, and paths | Implemented foundation | No | Completed foundation target for parity-gate, structured-output, private value transport, prompt extern, and path-allocation work. |
| [workflow_lisp_post_foundation_composition_stdlib_migration.md](workflow_lisp_post_foundation_composition_stdlib_migration.md) | Post-foundation Workflow Lisp composition and stdlib migration | Active target | No | Active roadmap after the runtime foundation; consumes WCC as the accepted nested-control substrate and continues typed result translation, imported/std `.orc` reuse, review/revise stdlib convergence, private executable context, certified adapter/state-transition ownership, and parent-callable parity promotion. |
| [workflow_lisp_generic_resource_context_core.md](workflow_lisp_generic_resource_context_core.md) | Generic resource/context core for post-foundation Workflow Lisp | Draft simplification target | No | Narrows private context and resource-transition work to a small runtime core (`RunCtx`, `Resource<TState>`, `Transition<TRequest, TResult>`) with domain contexts such as `PhaseCtx`, `DrainCtx`, and `RecoveryCtx` expressed as library records. Executable target: `workflow_lisp_generic_core_expression_surface_adapter_retirement.md`. |
| [workflow_lisp_generic_core_expression_surface_adapter_retirement.md](workflow_lisp_generic_core_expression_surface_adapter_retirement.md) | Generic runtime core, pure expression surface, and Python adapter retirement | Draft target | No | Executable target for the generic-core decision: tranches G0-G8 covering the total pure-expression operator set, typed projection, materialized value views, runtime-native typed transitions, `RunCtx`-only context bootstrap with type-driven classification, stdlib migration of phase/drain forms, boundary authority classes, and evidence-gated deletion of name-keyed context tables and workflow-semantics adapters. |
| [workflow_lisp_core_calculus_middle_end.md](workflow_lisp_core_calculus_middle_end.md) | Workflow core calculus and compiler middle-end | Accepted/implemented for migrated subset | No | Accepted compiler substrate for post-foundation Tranche 1: WCC schema 2 is default for new compiles in the migrated subset, with legacy schema 1 retained for compatibility. |
| [workflow_lisp_lexical_execution_checkpoints.md](workflow_lisp_lexical_execution_checkpoints.md) | Lexical execution checkpoints and durable resource resumability | Draft future target | No | Separates execution resumability (private, schema-versioned, digest-checked lexical checkpoints over WCC program identity) from domain durability (typed resources/transitions with idempotency and audit), with effect-boundary resume policies, fail-closed handling of pending non-idempotent effects, and retirement of resume-only authored plumbing from public `.orc` boundaries. |
| [workflow_lisp_consumer_side_rendering.md](workflow_lisp_consumer_side_rendering.md) | Consumer-side rendering over the G4 materialized-view kernel | Draft future target | No | Inverts materialization from producer-authored to consumer-derived: typed values rendered at the prompt-injection seam (ephemeral), observability-derived human summaries, per-variant entry-boundary `:publish` policy, and compatibility bridges maintained from classification metadata — shrinking body-level `materialize-view` to justified timed publications. Gated on generic-core G4 acceptance; no ordering relative to the checkpoints target. |
| [mlevolve_workflow_lisp_system_architecture.md](mlevolve_workflow_lisp_system_architecture.md) | MLEvolve-style Workflow Lisp workflow architecture | Draft design | No | Uses the practical candidate-4 scaffold as the first base and candidate-2 module split as the longer-term target. |
| [workflow_lisp_legacy_adapter.md](workflow_lisp_legacy_adapter.md) | Legacy adapter boundary | Partial/unknown from this index; read the doc and linked evidence | Yes | Use when preserving old mechanics during migration. |
| [dsl_v214_materialization_variants_draft.md](dsl_v214_materialization_variants_draft.md) | v2.14 materialization and variant outputs | Yes | Yes | Read with `specs/dsl.md` for current normative behavior. |
| [dsl_v214_pointer_authority.md](dsl_v214_pointer_authority.md) | Pointer authority and artifact identity | Partial/unknown from this index; read the doc and linked evidence | Yes | Use when pointer files risk becoming hidden semantic authority. |
| [dsl_v214_variant_surface_decision.md](dsl_v214_variant_surface_decision.md) | Variant-output surface decision | Yes | Yes | Historical/design context for v2.14 variant output surfaces. |
| [dsl_v214_yaml_ergonomics.md](dsl_v214_yaml_ergonomics.md) | YAML ergonomics around v2.14 | Partial/unknown from this index; read the doc and linked evidence | Yes | Use for YAML authoring ergonomics, not Workflow Lisp promotion authority. |

## Frontend Design Direction

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [workflow_lisp_unified_frontend_design.md](workflow_lisp_unified_frontend_design.md) | Future/deferred Workflow Lisp surfaces | Designed | No | Use for selecting future increments without treating them as current behavior. |
| [workflow_lisp_proc_refs_partial_application.md](workflow_lisp_proc_refs_partial_application.md) | Compile-time ProcRefs and `bind-proc` | Yes | Yes | Current direction for reusable procedure hooks without runtime procedure values. |
| [workflow_lisp_let_proc_local_proc_refs.md](workflow_lisp_let_proc_local_proc_refs.md) | Local compile-time procedure bindings | Designed | No | Follow-on ergonomics; not normal current authoring unless implemented on branch. |
| [workflow_lisp_compile_time_parametric_specialization.md](workflow_lisp_compile_time_parametric_specialization.md) | Parametric specialization and monomorphic helpers | Partial/designed | No | Type-system direction for generic `.orc` definitions. |
| [workflow_lisp_structural_parametric_constraints.md](workflow_lisp_structural_parametric_constraints.md) | Structural record/union constraints | Designed | No | Type-system direction for caller-owned records/unions. |
| [workflow_lisp_review_revise_stdlib_parametric_integration.md](workflow_lisp_review_revise_stdlib_parametric_integration.md) | Review/revise stdlib integration with refactor and parametric prerequisites | Designed/partial | No | High-quality target design; do not confuse prerequisites with current normal authoring. |
| [workflow_lisp_runtime_closures_boundary.md](workflow_lisp_runtime_closures_boundary.md) | Runtime closure boundary | Future | No | Runtime closures are intentionally deferred. |
| [workflow_lisp_refactor_architecture.md](workflow_lisp_refactor_architecture.md) | Behavior-preserving frontend refactor architecture | Yes | No | Use before module splits or traversal/context/lowering cleanup. |
| [workflow_lisp_legacy_adapter.md](workflow_lisp_legacy_adapter.md) | Legacy adapter containment | Partial/unknown from this index; read the doc and linked evidence | Yes | Also listed under migration because it affects migration policy. |

## Runtime And Observability Direction

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [dashboard_observability_summary_gui.md](dashboard_observability_summary_gui.md) | Dashboard summary GUI | Designed/partial | No | Product/observability design surface. |
| [dashboard_summary_invocation_tabs.md](dashboard_summary_invocation_tabs.md) | Dashboard invocation tabs | Designed/partial | No | Product/observability design surface. |
| [observability_step_visit_summaries.md](observability_step_visit_summaries.md) | Step visit summary observability | Partial/unknown from this index; read the doc and linked evidence | No | Use when changing visit summaries or run reporting. |
| [neurips_v214_behavior_matrix.md](neurips_v214_behavior_matrix.md) | NeurIPS v2.14 behavior matrix | Partial/unknown from this index; read the doc and linked evidence | No | Downstream behavior reference, not a generic authoring entrypoint. |

## Review And Workflow Families

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [lisp_frontend_review_fix_loops.md](lisp_frontend_review_fix_loops.md) | Review/fix loop semantics | Partial/unknown from this index; read the doc and linked evidence | Yes | Use with review/revise stdlib and parity architecture docs. |

## Historical Or Narrow Decision Notes

These docs may still be useful, but they should not override the current
component contracts, normative specs, or active migration designs above.

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [workflow_lisp_unified_frontend_design.md](workflow_lisp_unified_frontend_design.md) | Future authoring direction | Designed | No | Also listed under frontend direction because it is a major future-target doc. |
| [workflow_lisp_review_revise_stdlib_parametric_integration.md](workflow_lisp_review_revise_stdlib_parametric_integration.md) | Review/revise migration target | Designed/partial | No | Also listed under frontend direction because it is a major target design. |
