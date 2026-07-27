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
| [../plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md](../plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md) | Workflow Lisp provider prompt dependencies | Implemented functional contract | Yes | Typed required/optional exact relpaths lower through a compiler side table into one immutable per-attempt snapshot. Runtime plan remains topology-only and evidence remains non-authoritative; family port parity is separate. |
| [workflow_lisp_procedure_first_reuse_contract.md](workflow_lisp_procedure_first_reuse_contract.md) | Procedure-first boundary roles, lowering identity, effects, and migration rules | Accepted contract / adoption gated | No | Focused decision and migration companion; the frontend specification remains durable semantic authority, and Stage 5 substrate plus pilot evidence gates migration guidance. |
| [workflow_lisp_procedure_migration_identity_compatibility.md](workflow_lisp_procedure_migration_identity_compatibility.md) | Strict-default procedure-migration identity compatibility and bounded internal retirement | Accepted / generic prerequisites plus one reviewed internal pilot complete | No | The evidence-only exception remains narrow. The tracked-plan pilot completed at `0769e837`; this does not generalize cross-source compatibility, family waves, promotion, or YAML retirement. |
| [workflow_lisp_frontend_mvp_specification.md](workflow_lisp_frontend_mvp_specification.md) | MVP Workflow Lisp tranche | Yes | Yes | Useful for minimal implemented surface and MVP boundaries. |
| [workflow_lisp_semantic_workflow_ir.md](workflow_lisp_semantic_workflow_ir.md) | Semantic IR authority surface | Yes | No | Implementation/verification contract, not an authoring guide. |
| [workflow_lisp_executable_ir.md](workflow_lisp_executable_ir.md) | Executable IR authority surface | Yes | No | Implementation/verification contract below the frontend. |
| [workflow_lisp_macro_surface_contract.md](workflow_lisp_macro_surface_contract.md) | Current macro surface and provenance obligations | Yes | Yes | Use for current macro behavior, not future macro ambitions. |
| [workflow_lisp_stdlib_lowering.md](workflow_lisp_stdlib_lowering.md) | Stdlib lowering boundary | Partial | Yes | Explains when high-level forms should be stdlib composition rather than compiler primitives. |
| [workflow_lisp_state_layout.md](workflow_lisp_state_layout.md) | Generated path and state layout ownership | Partial | No | Use when generated paths, loop roots, and resume identities are involved. |
| [workflow_lisp_source_map.md](workflow_lisp_source_map.md) | Source-map provenance, including runtime structured-result field lineage | Partial | No | Current step/node provenance plus the accepted contract-field lineage extension; use when generated steps, fields, paths, or runtime violations need source ownership. |
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
| [workflow_lisp_key_migration_parity_architecture.md](workflow_lisp_key_migration_parity_architecture.md) | YAML-to-`.orc` promotion and parity gates | Partial | Yes | Promotion requires computed evidence, not just compile/dry-run success. The live surface is the generic two-target parity kernel; Design-Delta-only lanes are retired and its historical promotion report is preserved. |
| [workflow_lisp_runtime_migration_foundation.md](workflow_lisp_runtime_migration_foundation.md) | Runtime foundation for promotion gates, command outputs, and paths | Implemented foundation | No | Completed foundation target for parity-gate, structured-output, private value transport, prompt extern, and path-allocation work. |
| [workflow_lisp_post_foundation_composition_stdlib_migration.md](workflow_lisp_post_foundation_composition_stdlib_migration.md) | Post-foundation Workflow Lisp composition and stdlib migration | Active target | No | Active roadmap after the runtime foundation; consumes WCC as the accepted nested-control substrate and continues typed result translation, imported/std `.orc` reuse, review/revise stdlib convergence, private executable context, certified adapter/state-transition ownership, and parent-callable parity promotion. |
| [workflow_lisp_generic_resource_context_core.md](workflow_lisp_generic_resource_context_core.md) | Generic resource/context core for post-foundation Workflow Lisp | Incorporated direction | No | Decision record for the small runtime core now reflected in the frontend baseline: `RunCtx`, `Resource<TState>`, `Transition<TRequest, TResult>`, structural private context classification, and stdlib/domain contexts over the generic core. |
| [workflow_lisp_generic_core_expression_surface_adapter_retirement.md](workflow_lisp_generic_core_expression_surface_adapter_retirement.md) | Generic runtime core, pure expression surface, and Python adapter retirement | Incorporated target | No | Historical target design for the generic-core work now merged into the frontend baseline: closed pure-expression operators, generated typed projection, materialized value views, runtime-native typed transitions, boundary authority classes, stdlib phase/drain forms, and adapter-retirement policy. Use the frontend specification for the current contract. |
| [workflow_lisp_core_calculus_middle_end.md](workflow_lisp_core_calculus_middle_end.md) | Workflow core calculus and compiler middle-end | Accepted/implemented for migrated subset | No | Accepted compiler substrate for post-foundation Tranche 1: WCC schema 2 is default for new compiles in the migrated subset, with legacy schema 1 retained for compatibility. |
| [workflow_lisp_private_runtime_state_and_consumer_value_flow.md](workflow_lisp_private_runtime_state_and_consumer_value_flow.md) | Private runtime checkpoints and consumer-side typed-value rendering | Partial: Track R default resume plus narrow C1/C6 provider-input carriage implemented; broader cleanup remains future | No | Governing umbrella for two independent tracks. Scalar, record, and relpath `provider-result :inputs` now use consumer-seam rendering with deterministic implicit defaults and structured evidence. C2-C5, remaining C6 ergonomics, and remaining resume-only cleanup retain target status. |
| [workflow_lisp_runtime_native_drain_authoring.md](workflow_lisp_runtime_native_drain_authoring.md) | Runtime-native Workflow Lisp drain authoring | Historical reference target / regression checklist | No | Concrete acceptance target for the working Design Delta Drain `.orc` family. Its family-specific compile certification bundle is retired; use direct owner tests, route readiness, production compile/runtime evidence, and the preserved historical promotion report for current claims. |
| [workflow_lisp_shared_owner_lane_prerequisites.md](workflow_lisp_shared_owner_lane_prerequisites.md) | Shared owner-lane prerequisites for imported stdlib adoption | Reference target / prerequisite ledger | No | Prerequisite ledger split out of the runtime-native drain authoring target's Section 9: parent-loop, phase-family boundary, and `std/phase` self-hosting capability contracts, each with a minimum contract, minimum behavior check, and adoption-claim rule. Includes the former-section mapping table. |
| [workflow_lisp_lexical_execution_checkpoints.md](workflow_lisp_lexical_execution_checkpoints.md) | Lexical execution checkpoints and durable resource resumability | Detailed Track R source note; default-resume prerequisite implemented | No | Detailed source note for the umbrella target's Track R, including node-local primacy, positive record-absence proof, unique-nearest prior selection, and the prohibition on automatic scans past an invalid nearest checkpoint. Use the umbrella target for next-work routing. |
| [workflow_lisp_lexical_checkpoint_resumability.md](workflow_lisp_lexical_checkpoint_resumability.md) | Early lexical checkpoint resumability target | Predecessor draft | No | Earlier checkpoint/resume note; use `workflow_lisp_private_runtime_state_and_consumer_value_flow.md` for next-work routing and `workflow_lisp_lexical_execution_checkpoints.md` for the detailed Track R source note. |
| [workflow_lisp_consumer_side_rendering.md](workflow_lisp_consumer_side_rendering.md) | Consumer-side rendering over the materialized-view kernel | Predecessor draft | No | Detailed source note for the umbrella target's Track C. Use the umbrella target for next-work routing. |
| [mlevolve_workflow_lisp_system_architecture.md](mlevolve_workflow_lisp_system_architecture.md) | MLEvolve-style Workflow Lisp workflow architecture | Draft design | No | Uses the practical candidate-4 scaffold as the first base and candidate-2 module split as the longer-term target. |
| [workflow_lisp_legacy_adapter.md](workflow_lisp_legacy_adapter.md) | Legacy adapter boundary | Partial/unknown from this index; read the doc and linked evidence | Yes | Use when preserving old mechanics during migration. |
| [dsl_v214_materialization_variants_draft.md](dsl_v214_materialization_variants_draft.md) | v2.14 materialization and variant outputs | Yes | Yes | Read with `specs/dsl.md` for current normative behavior. |
| [dsl_v214_pointer_authority.md](dsl_v214_pointer_authority.md) | Pointer authority and artifact identity | Partial/unknown from this index; read the doc and linked evidence | Yes | Use when pointer files risk becoming hidden semantic authority. |
| [dsl_v214_variant_surface_decision.md](dsl_v214_variant_surface_decision.md) | Variant-output surface decision | Yes | Yes | Historical/design context for v2.14 variant output surfaces. |
| [dsl_v214_yaml_ergonomics.md](dsl_v214_yaml_ergonomics.md) | Historical YAML ergonomics around v2.14 | Retired historical design note | No | Preserves the pre-retirement YAML LOC analysis; use the Workflow Lisp drafting guide for current `.orc` authoring. |

## Frontend Design Direction

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [workflow_lisp_unified_frontend_design.md](workflow_lisp_unified_frontend_design.md) | Future/deferred Workflow Lisp surfaces | Designed | No | Use for selecting future increments without treating them as current behavior. |
| [Workflow Lisp evolution substrate and feature design](../superpowers/specs/2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md) | Compiler-certified immutable variants, context-stratified subject adjudication, inert fragment archives, role-separated prompt environments, prompt/code evolution, and the substrate/feature boundary | Parked; not a selector | No | Owner decision `8aeb2949` parks this design and the related effectiveness experiment plans. Any future revival must satisfy `workflow_lisp_program_search_boundaries.md`. The slimmed E0 probe remains unselected; the salvaged E4P diagnostic delta is now owned only by active successor Stage Q3. |
| [workflow_lisp_native_transportable_returns.md](workflow_lisp_native_transportable_returns.md) | Uniform native returns and optional typed result guidance | Implemented | Yes in DSL v2.15 | Native direct-root carriage and typed root/payload guidance are implemented across classic/WCC lowering, shared IR, prompts, runtime neutrality, and ordinary loader paths. |
| [workflow_lisp_transportable_value_type.md](workflow_lisp_transportable_value_type.md) | Opt-in transport-contract top `Value`, strict JSON wire validation, exact source compatibility, and target-gated public `type: value` / `kind: value` | Implemented | Yes at target 2.19+ | Q0 implements the accepted prompt-calculus prerequisite. `Value` is exact and opaque in source typing, distinct from non-transportable `Json`, and uses existing direct-root `__result__` carriage without an envelope across classic/WCC execution and resume. |
| [workflow_lisp_provider_prompt_queue.md](workflow_lisp_provider_prompt_queue.md) | Multi-turn `prompt-queue` over one provider session | Proposed (design review pending) | No | Atomic provider step driving N same-session turns; output contract on the final turn only. Not roadmap-scheduled; implementation gated behind drain S3/P4 and the native-return waves. |
| [workflow_lisp_prompt_calculus.md](workflow_lisp_prompt_calculus.md) | Target-2.20 prompt core plus accepted target-2.21 output-position design | Implemented | Yes for the bounded Q1 surface only | Q1 is implemented through the real `review-design-docs` consumer with classic/WCC parity, schema-2.1 fragment snapshots, fail-closed identity carriage, and compatible completed-boundary resume. Q2's `:path :out` design and implementation plan are accepted after ordered reviews, but Q2 behavior is not implemented; Task 1 is next under `docs/plans/2026-07-26-workflow-lisp-prompt-output-positions-implementation-plan.md`. Q3–Q4 retain their separate ownership. |
| [workflow_lisp_pure_list_traversal.md](workflow_lisp_pure_list_traversal.md) | Target-2.18 list construction/traversal, pure and bounded-effectful mapping, list loop state, and rooted path joining | Implemented | Yes, within the exact target-2.18 tranche | The interstage is complete. Principle-29-compatible runtime-cardinality fan-out is available over whole-list-contract-expressible types; record/union elements, higher-order mapping, and broader effect bodies remain deferred. The maintained deterministic-provider fixture proves ordered rooted-path production, synthesis, and clean/resume equivalence without replay or duplication. |
| [workflow_lisp_program_search_boundaries.md](workflow_lisp_program_search_boundaries.md) | Permanent boundary invariants for any future program-search/evolution feature | Adopted position statement | No | Owner-directed 2026-07-24 extraction from the parked evolution follow-on roadmap: immutable generation boundaries, untrusted provider output, neutral substrate vs feature, whole-candidate fitness authority, evidence separation, honest security boundary, no kind erasure, role-separated prompt identity. Constrains future designs; schedules no work. |
| [workflow_lisp_provider_live_binding.md](workflow_lisp_provider_live_binding.md) | Live provider supervision through observation panes and one bounded provider-session correction | v1 implemented through `4d4f05c7` | Yes for the exact v1 target-2.16 form | Adverse T3a retired *same-turn* `send-keys` steering. Implemented v1 composes one worker and one supervisor with a validated directive and one fail-closed turn-boundary resume under a single-writer coordinator. |
| [workflow_lisp_provider_peer_messaging.md](workflow_lisp_provider_peer_messaging.md) | Recorded turn-boundary peer messaging and static provider-peer groups | Implemented through `b08c04a6` | Yes for the exact target-2.17 static-group form | Target-2.17 `with-live-provider-peers` lowers through WCC to `provider_peer_group.v1` with 2..8 members, exact attempt-bound ingress, append-before-offer receiver ledgers, cooperative receipts/natural close, and no forcing edge. Target 2.16 and `provider_supervision.v1` remain unchanged. |
| [workflow_lisp_language_server.md](workflow_lisp_language_server.md) | `.orc` LSP server (editor diagnostics and navigation) | Implemented | No; use the setup guide for current editor configuration | Pure consumer of existing compile entry points per frontend spec §76.1. V1 remains read-only clean-open/save diagnostics plus closed navigation under one canonical root; completed L0 adds content-keyed pure-projection export reuse, one-probe no-watcher reverse invalidation, structured initialization failures, and visible compiler notes/expansion roles. L1 authored symbols/signatures and their implementation plan are accepted after ordered reviews, but L1 behavior is not implemented; Task 1 is next under `docs/plans/2026-07-26-workflow-lisp-language-server-l1-implementation-plan.md`, followed by L2–L4. Tolerance, hover, overlay, general compile caching, runtime debugging, and other P1–P5 prerequisites remain deferred. See [the setup guide](../workflow_lisp_language_server_setup.md) for shipped behavior. |
| [workflow_lisp_proc_refs_partial_application.md](workflow_lisp_proc_refs_partial_application.md) | Compile-time ProcRefs and `bind-proc` | Yes | Yes | Current direction for reusable procedure hooks without runtime procedure values. |
| [workflow_lisp_let_proc_local_proc_refs.md](workflow_lisp_let_proc_local_proc_refs.md) | Local compile-time procedure bindings | Designed | No | Follow-on ergonomics; not normal current authoring unless implemented on branch. |
| [workflow_lisp_parametric_type_system.md](workflow_lisp_parametric_type_system.md) | Parametric type system: generics, structural constraints, specialization, form-migration policy | Partial (tranche one landed) | No | Single owner of the parametric direction; supersedes the two 2026-06-02 drafts below. |
| [2026-06-19-workflow-lisp-type-runtime-boundary-issues.md](../reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md) | Historical diagnostic of the type/runtime contract-projection boundary | Historical (dispositioned 2026-07-08) | No | Read its "Disposition Of Recommendations" table for what is absorbed, actionable, or gated; pointers there govern. |
| [workflow_lisp_compile_time_parametric_specialization.md](workflow_lisp_compile_time_parametric_specialization.md) | Parametric specialization and monomorphic helpers | Superseded | No | Historical record; superseded by workflow_lisp_parametric_type_system.md. |
| [workflow_lisp_structural_parametric_constraints.md](workflow_lisp_structural_parametric_constraints.md) | Structural record/union constraints | Superseded | No | Historical record; superseded by workflow_lisp_parametric_type_system.md. |
| [workflow_lisp_review_revise_stdlib_parametric_integration.md](workflow_lisp_review_revise_stdlib_parametric_integration.md) | Review/revise stdlib integration with refactor and parametric prerequisites | Designed/partial | No | High-quality target design; do not confuse prerequisites with current normal authoring. |
| [workflow_lisp_runtime_closures_boundary.md](workflow_lisp_runtime_closures_boundary.md) | Runtime closure boundary | Future | No | Runtime closures are intentionally deferred. |
| [workflow_lisp_refactor_architecture.md](workflow_lisp_refactor_architecture.md) | Behavior-preserving frontend refactor architecture | Yes | No | Use before module splits or traversal/context/lowering cleanup. |
| [workflow_lisp_legacy_adapter.md](workflow_lisp_legacy_adapter.md) | Legacy adapter containment | Partial/unknown from this index; read the doc and linked evidence | Yes | Also listed under migration because it affects migration policy. |

## Runtime And Observability Direction

Provider-phase information isolation is a partial, pre-integration runtime
surface. Use the
[governing design](../superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md)
and
[active implementation plan](../superpowers/plans/2026-07-23-provider-phase-information-isolation.md);
the sealed environment, exact reviewed rootless
[`I0G` evidence](../reports/provider-isolation-rootless-launch-feasibility/README.md)
and independently reviewed standalone production
[`I0` evidence](../reports/provider-isolation-backend-feasibility/README.md)
exist. The broker, run/resume integration, attestation, public `G0` rerun, and
live smoke remain. The backend launches fixed `/usr/bin/bwrap` as the ordinary
controller user, but is not yet a public provider path. Separate clones are
experiment hygiene, not a substitute for the OS boundary.

The [resume projection-integrity hardening design-and-planning plan](../plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md)
has completed its characterization, accepted-design, normative-contract, and
reviewed-plan artifacts, holistic routing reviews, and fresh routing
validation. The exact reviewed
[resume projection-integrity hardening implementation plan](../plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md)
then completed at `fdf1e06b` with focused acceptance evidence, deterministic
public CLI smoke, broad baseline equivalence, and independent specification and
quality reviews. It is now historical implementation evidence; the current
roadmap records Stage 6 complete in the
[Procedure-First Roadmap Execution Sequence](../plans/2026-07-09-procedure-first-roadmap-execution-sequence.md).
Stage 7 provider-live-binding v1 is complete through Task 15 and Gate S7-v1.
The owner-amended v1.1 recorded-peer-messaging revision in
`workflow_lisp_provider_peer_messaging.md` received independent specification
and ordered quality approval after its initial review returned
`CHANGES_REQUIRED`. Its reviewed structural capability, runtime, target-2.17
frontend/projections, deterministic integration, and real one-, two-, and
three-member gates (one-member adapter, two-/three-member groups) landed
through `b08c04a6`; final Stage-7 gate and roadmap routing status remain owned
by the execution-sequence roadmap.
The target-2.18 list-traversal interstage and Stage-8 Workflow Lisp language
server v1 are also complete. The execution-sequence roadmap is now historical;
its post-Stage-8 handoff remains an input list, not a selector.

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [resume_projection_integrity_hardening.md](resume_projection_integrity_hardening.md) | Checksum-compatible scoped resume projection-integrity auditing | Implemented | No | Accepted design authority for the implemented two-pass root audit (CLI preflight plus structurally-root executor revalidation), distinct checksum envelopes, actual reached-call ordering, typed Workflow Lisp retry lineages, four loop-progress forms, schema-based optional step-result IDs, sticky parent-scope diagnostic promotion, duplicate-import rejection, diagnostics, and schema decision. The reviewed implementation completed at `fdf1e06b`; migration-wave execution remains separate. |
| [dashboard_observability_summary_gui.md](dashboard_observability_summary_gui.md) | Dashboard summary GUI | Designed/partial | No | Product/observability design surface. |
| [dashboard_summary_invocation_tabs.md](dashboard_summary_invocation_tabs.md) | Dashboard invocation tabs | Designed/partial | No | Product/observability design surface. |
| [observability_step_visit_summaries.md](observability_step_visit_summaries.md) | Step visit summary observability | Partial/unknown from this index; read the doc and linked evidence | No | Use when changing visit summaries or run reporting. |
| [neurips_v214_behavior_matrix.md](neurips_v214_behavior_matrix.md) | NeurIPS v2.14 behavior matrix | Partial/unknown from this index; read the doc and linked evidence | No | Downstream behavior reference, not a generic authoring entrypoint. |

## Review And Workflow Families

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [lisp_frontend_review_fix_loops.md](lisp_frontend_review_fix_loops.md) | Review/fix loop semantics | Partial/unknown from this index; read the doc and linked evidence | Yes | Use with review/revise stdlib and parity architecture docs. |
| [verified_iteration_drain.md](verified_iteration_drain.md) | Verified-iteration drain: single fused-session select/plan/implement/verify loop | Implemented; Workflow Lisp primary | Yes | Promoted `.orc` route alongside, not replacing, the `lisp_frontend_*` drain family; treats the repo, git history, and check exit codes as the sole authority instead of a second typed state copy. New launches use `workflows/library/verified_iteration_drain/drain.orc`; its retired YAML twin remains only in history and parity evidence. |

## Historical Or Narrow Decision Notes

These docs may still be useful, but they should not override the current
component contracts, normative specs, or active migration designs above.

| Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
| --- | --- | ---: | ---: | --- |
| [workflow_lisp_unified_frontend_design.md](workflow_lisp_unified_frontend_design.md) | Future authoring direction | Designed | No | Also listed under frontend direction because it is a major future-target doc. |
| [workflow_lisp_review_revise_stdlib_parametric_integration.md](workflow_lisp_review_revise_stdlib_parametric_integration.md) | Review/revise migration target | Designed/partial | No | Also listed under frontend direction because it is a major target design. |
