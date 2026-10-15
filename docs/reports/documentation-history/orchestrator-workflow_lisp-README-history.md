# orchestrator/workflow_lisp/README.md: Historical Sections

Status: **Historical.** Original tense, versioned acceptance language, receipts
and commands are preserved as evidence, not current execution or work selection.
Current owner: [README.md](../../../orchestrator/workflow_lisp/README.md).

## Historical operational record 3

Start with these project docs before changing the package:

- [Workflow Lisp Frontend Specification](../../design/workflow_lisp_frontend_specification.md):
  accepted baseline and umbrella language contract. Start here for current
  surface semantics, pure-expression behavior, and frontend/runtime authority
  boundaries.
- [Workflow Lisp Core Calculus Middle-End](../../design/workflow_lisp_core_calculus_middle_end.md):
  accepted WCC middle-end (elaboration, ANF normalization, analysis); its
  flat defunctionalization route is retired.
- [Workflow Lisp Evaluated Execution](../../design/workflow_lisp_evaluated_execution.md):
  accepted design for the checked closed program and the evaluated runtime
  that executes it at targets 2.35 and later.
- [Workflow Lisp Runtime Migration Foundation](../../design/workflow_lisp_runtime_migration_foundation.md):
  completed foundation target for structured output authority, private value
  transport, and generated path allocation; its manifest-driven parity gates
  are historical evidence.
- [Workflow Lisp Post-Foundation Composition And Stdlib Migration](../../design/workflow_lisp_post_foundation_composition_stdlib_migration.md):
  incorporated historical target for nested composition, stdlib reuse,
  private executable context, typed projection, resource transitions, and
  parent-callable parity evidence. Use the frontend and component contracts
  for current behavior; the inventory and parity generator are retired.
- [Workflow Lisp Generic Core, Expression Surface, And Adapter Retirement](../../design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md):
  incorporated historical target for the small runtime core, pure expression surface,
  materialized views, typed transitions, context generalization, and retiring
  workflow-semantics Python adapters.
- [Workflow Lisp Frontend MVP Specification](../../design/workflow_lisp_frontend_mvp_specification.md):
  historical MVP scope and original acceptance story.
- [Workflow Lisp MVP Comparison](../../workflow_lisp_mvp_comparison.md):
  quick side-by-side explanation of why the `.orc` form is more concise than
  the equivalent YAML.
- [Workflow Lisp Stdlib Lowering](../../design/workflow_lisp_stdlib_lowering.md):
  intended lowering contracts for higher-level forms such as `provider-result`,
  `command-result`, `resume-or-start`, `resource-transition`, and
  `backlog-drain`.
- [Workflow Command Adapter Contract](../../design/workflow_command_adapter_contract.md):
  rules for command adapters and why inline Python/shell glue is migration
  debt.
- [Workflow Lisp Unified Design for Unimplemented Surfaces](../../design/workflow_lisp_unified_frontend_design.md):
  incremental future-target design for non-implemented, partial, and deferred
  Workflow Lisp surfaces. Use this when selecting or reviewing missing frontend
  increments that are not already governed by the current target docs above.

## Original flat-owner deletion receipt

`wcc/defunctionalize.py`,
`wcc/lower.py`, `lowering/`, `source_map.py`, and `debug_yaml.py` were
deleted with the flat route (commit `026f2fa4`).
