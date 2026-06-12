# Workflow Lisp Generic Core / Adapter Retirement Drain Work Instructions

Status: active work instructions

## Objective

Drain implementation gaps required by
`docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
while preserving the accepted Workflow Lisp baseline and completed runtime
foundation.

This body of work focuses on the generic runtime core, pure expression surface,
typed projection, materialized value views, typed transitions, boundary
authority classes, stdlib-owned domain contexts, and retirement of workflow
semantics currently hidden in Python or shell adapters.

## Source Material

Use these documents as primary source material:

- target design:
  `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- baseline design:
  `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_generic_resource_context_core.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/lisp_workflow_drafting_guide.md`
- current run state, progress ledgers, route-readiness registry, and relevant
  implementation/test evidence

## Work Order

1. Start with the G0 census and boundary-authority classification unless a
   concrete prerequisite blocks it.
2. Prefer P0 substrate gaps from the target design: pure expression core and
   generic resource/transition runtime core.
3. Preserve WCC/schema-2 as the compiler route for expression/projection work.
4. Treat adapter retirement as evidence-gated: classify first, replace with
   typed projection/materialized view/resource transition only when the
   replacement has tests and provenance.
5. Do not delete adapters, ontology tables, or raw semantic argv surfaces until
   the target's deletion evidence is satisfied.

## Constraints

- Do not reopen completed runtime-foundation or WCC work unless the selected
  gap identifies a regression.
- Do not weaken specs or accepted design contracts to make implementation
  easier.
- Do not treat reports, pointer files, summaries, debug YAML, or provider prose
  as semantic authority.
- Keep domain nouns such as `PhaseCtx`, `ItemCtx`, `DrainCtx`, `SelectionCtx`,
  and `RecoveryCtx` in Workflow Lisp libraries unless the generic runtime core
  explicitly requires a smaller primitive.
- Keep changes bounded to the selected obligation and its direct docs, specs,
  fixtures, runtime code, or migration evidence.

## Completion Target

This body of work is complete when the target design has no remaining
implementation gaps under the accepted Workflow Lisp baseline, WCC/schema-2
route, completed runtime foundation, and current specs, and semantic adapters
covered by the target have been retired or explicitly retained as certified
external boundaries.
