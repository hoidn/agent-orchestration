# Workflow Lisp Code Map

This package implements the current Workflow Lisp frontend. It is not a
separate runtime. It parses `.orc` source, typechecks it, lowers supported
forms through the WCC/schema-2 middle-end into Core AST / Semantic IR /
Executable IR, and then sends the validated executable workflow through the
existing workflow loader and runtime pipeline. Legacy schema-1/direct lowering
surfaces remain compatibility paths, not the preferred route for new migrated
evidence.

Start with these project docs before changing the package:

- [Workflow Lisp Frontend Specification](../../docs/design/workflow_lisp_frontend_specification.md):
  accepted baseline and umbrella language contract. Start here for current
  surface semantics, pure-expression behavior, and frontend/runtime authority
  boundaries.
- [Workflow Lisp Core Calculus Middle-End](../../docs/design/workflow_lisp_core_calculus_middle_end.md):
  accepted WCC/schema-2 compiler substrate for migrated Workflow Lisp routes.
- [Workflow Lisp Runtime Migration Foundation](../../docs/design/workflow_lisp_runtime_migration_foundation.md):
  completed foundation target for structured output authority, private value
  transport, strict parity gates, and generated path allocation.
- [Workflow Lisp Post-Foundation Composition And Stdlib Migration](../../docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md):
  active migration target for nested composition, stdlib reuse, private
  executable context, typed projection, resource transitions, and parent
  callable parity evidence.
- [Workflow Lisp Generic Core, Expression Surface, And Adapter Retirement](../../docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md):
  target design for the small runtime core, pure expression surface,
  materialized views, typed transitions, context generalization, and retiring
  workflow-semantics Python adapters.
- [Workflow Lisp Frontend MVP Specification](../../docs/design/workflow_lisp_frontend_mvp_specification.md):
  historical MVP scope and original acceptance story.
- [Workflow Lisp MVP Comparison](../../docs/workflow_lisp_mvp_comparison.md):
  quick side-by-side explanation of why the `.orc` form is more concise than
  the equivalent YAML.
- [Workflow Lisp Stdlib Lowering](../../docs/design/workflow_lisp_stdlib_lowering.md):
  intended lowering contracts for higher-level forms such as `provider-result`,
  `command-result`, `resume-or-start`, `resource-transition`, and
  `backlog-drain`.
- [Workflow Command Adapter Contract](../../docs/design/workflow_command_adapter_contract.md):
  rules for command adapters and why inline Python/shell glue is migration
  debt.
- [Workflow Lisp Unified Design for Unimplemented Surfaces](../../docs/design/workflow_lisp_unified_frontend_design.md):
  incremental future-target design for non-implemented, partial, and deferred
  Workflow Lisp surfaces. Use this when selecting or reviewing missing frontend
  increments that are not already governed by the current target docs above.

## Pipeline

The default code path for supported migrated routes is:

```text
reader.py
  -> syntax.py
  -> macros.py
  -> modules.py
  -> definitions.py
  -> type_env.py
  -> expressions.py
  -> functions.py
  -> typecheck.py
  -> typecheck_context.py / typecheck_dispatch.py
  -> typecheck_proofs.py / typecheck_effects.py / typecheck_calls.py /
     typecheck_pure_ops.py
  -> procedure_typecheck.py
  -> workflows.py / procedures.py
  -> procedure_specialization.py
  -> wcc/elaborate.py
  -> wcc/anf.py
  -> wcc/analysis.py
  -> wcc/defunctionalize.py
  -> wcc/lower.py
  -> compiler.py
  -> lowering/__init__.py
  -> lowering/core.py / lowering/* owner modules
  -> shared validation
  -> Semantic IR / Executable IR
  -> existing workflow loader/runtime pipeline
```

`compiler.py` is the compile coordinator facade. The `wcc/` package owns the
accepted schema-2 middle-end route: elaboration, ANF normalization,
scope/effect/proof analysis, defunctionalization, and lowering into the
validated flat model. `lowering/__init__.py` preserves the public lowering
import path while the `lowering/` owner modules handle Core projection,
source-map/provenance, generated paths, pure projections, procedures, calls,
control, effects, values, and stdlib bridge surfaces.

Use [../../docs/workflow_lisp_route_readiness_registry.json](../../docs/workflow_lisp_route_readiness_registry.json)
and `route_readiness.py` when deciding whether an example, fixture, or
migration target is current `wcc_default` evidence or legacy compatibility
evidence.

## Main Data Shapes

- `sexpr.py`: raw source parse nodes.
- `syntax.py`: source-mapped syntax nodes used by macros and diagnostics.
- `definitions.py`: type-definition records for enums, paths, records, and
  tagged unions.
- `type_env.py`: resolved type references used by expression typechecking.
- `expressions.py`: supported `.orc` expression forms.
- `typecheck_pure_ops.py`: pure-expression operator typing, including
  equality, comparison, boolean, arithmetic, string, option, and record-update
  checks over the closed implemented operator set.
- `workflows.py`: `defworkflow` definitions, call signatures, extern bindings,
  and command-boundary bindings.
- `procedures.py`: `defproc` definitions and lowering policy.
- `functions.py`: pure `defun` surface and helper typing.
- `stdlib_modules/std/phase.orc`: imported phase stdlib module that owns the
  public `review-revise-loop` protocol and body, including typed review
  decisions, typed loop results, and the explicit
  `validate_review_findings_v1` command boundary.
- `procedure_typecheck.py`: procedure-call typing, generated helper procedure
  typing, and procedure-definition typing ownership behind the `typecheck.py`
  and `compiler.py` compatibility facades.
- `procedure_specialization.py`: compile-time ProcRef / WorkflowRef
  specialization discovery, request materialization, deterministic naming,
  private-workflow eligibility for specialized procedures, and
  specialization-aware procedure catalog augmentation.
- `procedure_refs.py`: compile-time `ProcRef[...]` resolution, `bind-proc`
  partial application, specialization naming, and residual-signature
  validation. ProcRef remains compile-time-only; runtime ProcRef transport and
  dynamic dispatch are still unsupported.
- `contracts.py`: conversion from frontend record/union types to runtime
  `output_bundle`, `variant_output`, input, and output contracts.
- `stdlib_contracts.py`: compile-time lowering-contract inventory for supported
  stdlib forms, including helper ownership and certified adapter bindings such
  as `validate_review_findings_v1` for `review-revise-loop`.
- `resource.py` / `resource_stdlib.py`: current resource/context helpers and
  bridge surfaces used while the generic `RunCtx` / `Resource<TState>` /
  `Transition<TRequest, TResult>` target is implemented.
- `drain_stdlib.py`: drain-family stdlib helper support for current migrated
  routes and compatibility bridges.
- `route_readiness.py`: validation and lookup for
  `docs/workflow_lisp_route_readiness_registry.json`, including route labels,
  schema identity, and target/example readiness checks.
- `post_wcc_inventory.py`: post-WCC current-state inventory validation and
  generated reconciliation index support.
- `compiler.py`: compile-stage coordinator facade and compatibility surface for
  procedure typing/specialization entrypoints.
- `typecheck.py`: stable compatibility facade for callers and tests. Keep
  imports here stable even when family ownership moves.
- `typecheck_context.py`: shared `TypedExpr`, recursive typecheck context,
  diagnostics helpers, and mutable pass-session state seams.
- `typecheck_dispatch.py`: recursive expression dispatcher and coordinator for
  the family owners below.
- `typecheck_proofs.py`: proof-scope data shapes plus variant-proof and
  field-access typing helpers.
- `typecheck_effects.py`: provider-result and command-result typing helpers,
  extern-operand validation, and effect-visibility checks.
- `typecheck_calls.py`: workflow, workflow-ref, proc-ref, and function-call
  typing helpers outside `procedure_typecheck.py`.
- `wcc/model.py`: WCC expression, continuation, effect, route, and schema data
  shapes.
- `wcc/elaborate.py`: elaboration from typed Workflow Lisp expressions into
  WCC.
- `wcc/anf.py`: ANF normalization and join-point shaping.
- `wcc/analysis.py`: scope, effect, proof, and route-analysis helpers.
- `wcc/defunctionalize.py`: conversion from WCC structure to the existing flat
  executable model without runtime closures.
- `wcc/lower.py` / `wcc/route.py`: route orchestration, default-route policy,
  and schema metadata.
- `lowering/__init__.py`: stable lowering facade for callers and tests.
- `lowering/core.py`: lowering coordinator and compatibility surface for the
  shared validation handoff; family ownership now lives in the dedicated owner
  modules below rather than in one mixed lowering sink.
- `lowering/context.py`: shared lowering context and state passed across owner
  modules.
- `lowering/composition_graph.py`: composition-normalized control/effect graph
  support for nested WCC lowering.
- `lowering/generated_paths.py`: generated path and write-root ownership before
  shared validation/runtime consumption.
- `lowering/origins.py`: generated statement and source-map origin helpers.
- `lowering/procedures.py`: procedure call-site lowering analysis, actual
  procedure lowering, provenance-note ownership, generated private-workflow
  synthesis, and runtime-erasure guards for compile-time-only procedure
  metadata.
- `lowering/control.py`: stable control-family facade.
- `lowering/control_dispatch.py`: expression dispatch plus `let*` and `if`
  lowering ownership.
- `lowering/control_dispatch_impl.py` / `lowering/control_impl.py`: implementation
  helpers behind the stable control facades.
- `lowering/control_match.py`: match lowering, branch projection, and
  match-bound local-value ownership.
- `lowering/control_match_impl.py`: implementation helpers behind match
  lowering.
- `lowering/control_loops.py`: bounded `loop/recur` lowering ownership.
- `lowering/values.py`: record/union projection, inline value resolution, and
  step-backed return materialization ownership.
- `lowering/pure_projection.py`: generated `pure_projection` step ownership for
  pure input-derived runtime-visible values.
- `lowering/workflow_calls.py`: workflow-call lowering, call-binding rendering,
  and managed write-root helper ownership.
- `lowering/effects.py`: primitive `provider-result` / `command-result`
  lowering ownership.
- `lowering/phase_stdlib.py`: stable phase/resource/drain facade plus the
  residual review-loop result-contract shaping helpers used by the ordinary
  stdlib route.
- `lowering/phase_scope.py`: `with-phase` scope and prompt-input prelude
  ownership.
- `lowering/phase_flow.py`: `run-provider-phase`, `produce-one-of`, and
  `resume-or-start` lowering ownership.
- `lowering/phase_helpers.py` / `lowering/phase_impl.py`: implementation
  helpers behind the current phase/std-resource compatibility surfaces.
- `lowering/phase_resource.py`: `resource-transition` and
  `finalize-selected-item` lowering ownership.
- `lowering/phase_drain.py`: `backlog-drain` lowering ownership.

## Component Design Docs

The larger design split these internal concepts into separate documents:

- [Core Workflow AST](../../docs/design/workflow_lisp_core_workflow_ast.md)
- [Workflow Core Calculus Middle-End](../../docs/design/workflow_lisp_core_calculus_middle_end.md)
- [Core Statement Taxonomy](../../docs/design/workflow_lisp_core_stmt_taxonomy.md)
- [Semantic Workflow IR](../../docs/design/workflow_lisp_semantic_workflow_ir.md)
- [Executable IR](../../docs/design/workflow_lisp_executable_ir.md)
- [Reference Catalog](../../docs/design/workflow_lisp_reference_catalog.md)
- [Type Catalog](../../docs/design/workflow_lisp_type_catalog.md)
- [Effect Graph](../../docs/design/workflow_lisp_effect_graph.md)
- [Proof Graph](../../docs/design/workflow_lisp_proof_graph.md)
- [State Layout](../../docs/design/workflow_lisp_state_layout.md)
- [Source Map](../../docs/design/workflow_lisp_source_map.md)
- [Runtime Migration Foundation](../../docs/design/workflow_lisp_runtime_migration_foundation.md)
- [Post-Foundation Composition And Stdlib Migration](../../docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md)
- [Generic Core, Expression Surface, And Adapter Retirement](../../docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md)
- [Legacy Adapter](../../docs/design/workflow_lisp_legacy_adapter.md)
- [Debug YAML Renderer](../../docs/design/workflow_lisp_debug_yaml_renderer.md)

Some of those docs describe intended future architecture more broadly than the
current code implements. When code and docs differ, current source and tests
determine implemented behavior. Use the capability status matrix and route
readiness registry to classify current, partial, future, and legacy surfaces
before copying examples or claiming migration evidence.

Pure expressions are implemented for the closed operator set documented in the
frontend specification and checked by `typecheck_pure_ops.py`. Runtime-visible
pure input-derived outputs lower as generated `pure_projection` steps; they are
not a separate authored YAML surface and must remain visible in source maps,
Semantic IR, generated path metadata, and runtime validation.

The generic-core target is not fully implemented. Current code still contains
compatibility surfaces for named contexts, phase/resource lowering hooks, and
adapter-backed resource behavior. New work should move toward the small runtime
core (`RunCtx`, `Resource<TState>`, `Transition<TRequest, TResult>`), stdlib
domain contexts, typed projections, materialized views, and certified adapters
as described in the target design.

Runtime closures remain deferred. `runtime_closure_design_fixtures.py` is a
test-only rejection harness for disabled/design-fixture closure cases; it must
not participate in ordinary compilation, and normal Workflow Lisp artifacts
must not emit runtime-closure payloads, registries, or invocation nodes.
`let-proc` remains compile-time-only.

Future structural-constraint, imported-`.orc`, and review-loop follow-on work
should target the dedicated typecheck owner files above instead of adding more
family logic directly to `typecheck.py`.
