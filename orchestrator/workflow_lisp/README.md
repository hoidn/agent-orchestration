# Workflow Lisp Code Map

This package implements the current Workflow Lisp frontend. It is not a
separate runtime. It parses `.orc` source, typechecks it, lowers it to ordinary
workflow dictionaries, and then sends those dictionaries through the existing
workflow loader and runtime pipeline.

Start with these project docs before changing the package:

- [Workflow Lisp Unified Design for Unimplemented Surfaces](../../docs/design/workflow_lisp_unified_frontend_design.md):
  incremental future-target design for non-implemented, partial, and deferred
  Workflow Lisp surfaces. Use this when selecting or reviewing the next missing
  frontend increment.
- [Workflow Lisp Frontend Specification](../../docs/design/workflow_lisp_frontend_specification.md):
  parent baseline and north-star frontend design, diagrams, terminology, and
  long-term architecture.
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

## Pipeline

The code path is:

```text
reader.py
  -> syntax.py
  -> macros.py
  -> definitions.py
  -> type_env.py
  -> expressions.py
  -> typecheck.py
  -> workflows.py / procedures.py
  -> compiler.py
  -> lowering.py
  -> existing workflow loader/runtime
```

`compiler.py` coordinates the pipeline. `lowering.py` is the boundary where
typed frontend expressions become ordinary workflow dictionaries.

## Main Data Shapes

- `sexpr.py`: raw source parse nodes.
- `syntax.py`: source-mapped syntax nodes used by macros and diagnostics.
- `definitions.py`: type-definition records for enums, paths, records, and
  tagged unions.
- `type_env.py`: resolved type references used by expression typechecking.
- `expressions.py`: supported `.orc` expression forms.
- `workflows.py`: `defworkflow` definitions, call signatures, extern bindings,
  and command-boundary bindings.
- `procedures.py`: `defproc` definitions and lowering policy.
- `procedure_refs.py`: compile-time `ProcRef[...]` resolution, `bind-proc`
  partial application, specialization naming, and residual-signature
  validation. ProcRef remains compile-time-only; runtime ProcRef transport and
  dynamic dispatch are still unsupported.
- `contracts.py`: conversion from frontend record/union types to runtime
  `output_bundle`, `variant_output`, input, and output contracts.
- `lowering.py`: generated steps, generated inputs, source maps, and calls into
  the existing workflow validation path.

## Component Design Docs

The larger design split these internal concepts into separate documents:

- [Core Workflow AST](../../docs/design/workflow_lisp_core_workflow_ast.md)
- [Core Statement Taxonomy](../../docs/design/workflow_lisp_core_stmt_taxonomy.md)
- [Semantic Workflow IR](../../docs/design/workflow_lisp_semantic_workflow_ir.md)
- [Reference Catalog](../../docs/design/workflow_lisp_reference_catalog.md)
- [Type Catalog](../../docs/design/workflow_lisp_type_catalog.md)
- [Effect Graph](../../docs/design/workflow_lisp_effect_graph.md)
- [Proof Graph](../../docs/design/workflow_lisp_proof_graph.md)
- [State Layout](../../docs/design/workflow_lisp_state_layout.md)
- [Source Map](../../docs/design/workflow_lisp_source_map.md)
- [Legacy Adapter](../../docs/design/workflow_lisp_legacy_adapter.md)
- [Debug YAML Renderer](../../docs/design/workflow_lisp_debug_yaml_renderer.md)

Some of those docs describe intended future architecture more broadly than the
current code implements. When code and docs differ, current source and tests
determine implemented behavior. Use the unified design for future-target gaps
and the parent specification for baseline design constraints.

Runtime closures remain deferred. `runtime_closure_design_fixtures.py` is a
test-only rejection harness for disabled/design-fixture closure cases; it must
not participate in ordinary compilation, and normal Workflow Lisp artifacts
must not emit runtime-closure payloads, registries, or invocation nodes.
`let-proc` remains compile-time-only.
