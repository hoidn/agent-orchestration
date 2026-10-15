# Workflow Lisp Code Map

This package implements the current Workflow Lisp frontend. It is not a
separate runtime. It parses `.orc` source, typechecks it, elaborates supported
forms through the WCC middle-end (elaboration, ANF normalization), builds a
checked closed program (`closed/`, checked by
`orchestrator/contracts/closed_program/`), and the evaluated runtime
(`orchestrator/workflow/evaluated/`) executes that program. The flat route
(defunctionalization into flat steps and the step runtime that executed them;
targets through 2.34) was retired on 2026-10-13 and executable entries
through 2.34 are refused. `LoweringRoute` (`wcc/route.py`) still records the
legacy schema-1 and WCC schema-2 compile routes for typed analysis and
persisted-run metadata; neither selects an executable backend. Evaluated
targets are 2.35 and 2.36, with bounded 2.37 (parallel map) and 2.38 (agent
sessions, confined run references) extensions. At 2.36, source-graph
selection supplies one W3 `std/improve` API and existing generated local
procedures. The [Phase 4c plan](../../docs/plans/2026-10-07-evaluated-execution-phase-4c-w3-plan.md)
records qualification and delivery evidence.

Start with these project docs before changing the package:

- [Workflow Lisp Frontend Specification](../../docs/design/workflow_lisp_frontend_specification.md):
  accepted baseline and umbrella language contract. Start here for current
  surface semantics, pure-expression behavior, and frontend/runtime authority
  boundaries.
- [Workflow Lisp Core Calculus Middle-End](../../docs/design/workflow_lisp_core_calculus_middle_end.md):
  accepted WCC middle-end (elaboration, ANF normalization, analysis); its
  flat defunctionalization route is retired.
- [Workflow Lisp Evaluated Execution](../../docs/design/workflow_lisp_evaluated_execution.md):
  accepted design for the checked closed program and the evaluated runtime
  that executes it at targets 2.35 and later.
- [Workflow Lisp Runtime Migration Foundation](../../docs/design/workflow_lisp_runtime_migration_foundation.md):
  completed foundation target for structured output authority, private value
  transport, and generated path allocation; its manifest-driven parity gates
  are historical evidence.
- [Workflow Lisp Post-Foundation Composition And Stdlib Migration](../../docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md):
  incorporated historical target for nested composition, stdlib reuse,
  private executable context, typed projection, resource transitions, and
  parent-callable parity evidence. Use the frontend and component contracts
  for current behavior; the inventory and parity generator are retired.
- [Workflow Lisp Generic Core, Expression Surface, And Adapter Retirement](../../docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md):
  incorporated historical target for the small runtime core, pure expression surface,
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

The compile and execution path is:

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
  -> compiler.py
  -> closed/frontend.py (typed program)
  -> wcc/elaborate.py (scope hygiene: wcc/hygiene.py)
  -> wcc/anf.py
  -> closed/build.py (checked closed-program tree; closed/values.py,
     closed/effects.py, closed/agent_effects.py, closed/command_templates.py,
     closed/command_interfaces.py)
  -> orchestrator/contracts/closed_program/ (sites.py, check.py, program.py)
  -> closed/artifact.py (content-addressed build)
  -> orchestrator/workflow/evaluated/ (runtime.py, machine.py)
```

`compiler.py` is the compile coordinator facade. The `wcc/` package owns the
retained middle-end: the calculus model, elaboration, scope hygiene, ANF
normalization, and scope analysis. The `closed/` package turns the typed
program into the checked closed program; `orchestrator/contracts/closed_program/`
assigns effect sites and validates the program without source access; and
`orchestrator/workflow/evaluated/` executes it. `wcc/defunctionalize.py`,
`wcc/lower.py`, `lowering/`, `source_map.py`, and `debug_yaml.py` were
deleted with the flat route (commit `026f2fa4`).

Use [../../docs/workflow_lisp_route_readiness_registry.json](../../docs/workflow_lisp_route_readiness_registry.json)
and `route_readiness.py` when deciding whether an example, fixture, or
migration target is `evaluated_execution` closed-program evidence or
`historical_negative` retained source/type history; the registry carries no
`wcc_default` flat rows. Evaluated rows omit flat
lowering route/schema fields and use public CLI evidence; the registry does
not select compiler/runtime behavior or certify evaluated LSP support.

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
- `stdlib_contracts.py`: certified command adapter bindings retained for
  stdlib forms, such as `validate_review_findings_v1` for `review-revise-loop`.
- `resource.py` / `resource_stdlib.py`: current resource/context helpers and
  bridge surfaces used while the generic `RunCtx` / `Resource<TState>` /
  `Transition<TRequest, TResult>` target is implemented.
- `stdlib_modules/std/drain.orc`: imported generic `backlog-drain` procedure
  and macro ownership; ordinary specialization and WCC lowering handle the
  expanded parent-owned loop without a drain-specific Python helper module.
- `route_readiness.py`: validation and lookup for
  `docs/workflow_lisp_route_readiness_registry.json`, including route labels,
  schema identity, and target/example readiness checks.
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
- `wcc/analysis.py`: scope and live-out analysis helpers for WCC control
  nodes.
- `wcc/hygiene.py`: scope hygiene (fresh names, renaming) for bindings the
  elaborator hoists or generates.
- `wcc/use_site_scope.py`: renames binders that would capture a name a pure
  binding reads where it is used.
- `wcc/route.py`: `LoweringRoute` enum, default-route policy, and persisted
  lowering-schema metadata.
- `closed/target.py`: entry `:target-dsl` selection and evaluated-target
  availability checks, including refusal of retired entry targets.
- `closed/frontend.py`: typed source programs (`TypedProgram`) captured from
  the compiler for evaluated execution, including import admission.
- `closed/build.py`: builds one checked closed-program tree from an admitted
  typed program (WCC elaboration and ANF, then closed forms).
- `closed/values.py`: WCC and retained surface values into checked JSON values.
- `closed/effects.py`: closed forms for command effects and located gaps for
  the remaining effects.
- `closed/agent_effects.py`: closed forms for `agent` allocation and
  `agent_turn` (target 2.38).
- `closed/command_templates.py` / `closed/command_interfaces.py`: command
  scopes and finite command decisions projected from one prepared WCC owner.
- `closed/context.py`, `closed/names.py`, `closed/program.py`,
  `closed/preparation_check.py`: hidden-context defaults, pure identities,
  command-configuration projection, and the preparation equality guard.
- `closed/artifact.py`: content-addressed on-disk builds for checked closed
  programs; the `compile` CLI entry.
- `orchestrator/contracts/closed_program/`: source-free closed-program
  contract: `sites.py` assigns effect sites and call frames, `check.py`
  validates the tree, `program.py` loads it and computes its digest, and
  `targets.py` holds target admission constants.
- `orchestrator/workflow/evaluated/`: the evaluated runtime (`runtime.py`,
  `machine.py`, `values.py`, memo, attempts, replay, provider IO, agent
  sessions).

## Component Design Docs

The larger design split these internal concepts into separate documents:

- [Core Workflow AST](../../docs/design/workflow_lisp_core_workflow_ast.md)
- [Workflow Core Calculus Middle-End](../../docs/design/workflow_lisp_core_calculus_middle_end.md)
- [Core Statement Taxonomy](../../docs/design/workflow_lisp_core_stmt_taxonomy.md)
- [Semantic Workflow IR](../../docs/design/workflow_lisp_semantic_workflow_ir.md)
- [Executable IR](../../docs/design/workflow_lisp_executable_ir.md) (retired with the flat route)
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
- [Debug YAML Renderer](../../docs/design/workflow_lisp_debug_yaml_renderer.md) (retired with the flat route)

Some of those docs describe intended future architecture more broadly than the
current code implements. When code and docs differ, current source and tests
determine implemented behavior. Use the capability status matrix and route
readiness registry to classify current, partial, future, and legacy surfaces
before copying examples or claiming migration evidence.

Pure expressions are implemented for the closed operator set documented in the
frontend specification and checked by `typecheck_pure_ops.py`. Runtime-visible
pure input-derived values are compiler-generated pure projections, not a
separate authored surface; the closed program carries them as checked pure
value nodes that `orchestrator/workflow/evaluated/values.py` evaluates.

The generic-core target is not fully implemented. Current code still contains
compatibility surfaces for named contexts, phase/resource helper modules, and
adapter-backed resource behavior. New work should move toward the small runtime
core (`RunCtx`, `Resource<TState>`, `Transition<TRequest, TResult>`), stdlib
domain contexts, typed projections, materialized views, and certified adapters
as described in the target design.

Runtime closures remain deferred. Normal Workflow Lisp artifacts must not emit
runtime-closure payloads, registries, or invocation nodes. `let-proc` remains
compile-time-only.

Future structural-constraint, imported-`.orc`, and review-loop follow-on work
should target the dedicated typecheck owner files above instead of adding more
family logic directly to `typecheck.py`.
