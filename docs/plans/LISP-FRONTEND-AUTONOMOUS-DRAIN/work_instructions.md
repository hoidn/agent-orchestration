# Workflow Lisp Autonomous Drain Work Instructions

Status: active work instructions

These instructions define procedural prescriptions for the Workflow Lisp
autonomous drain body of work. They apply while this body of work is active.
After completion, they are historical context unless a later body of work
explicitly reuses them.

## Objective

Implement the full approved Workflow Lisp frontend design, not only the MVP
subset, while preserving compatibility with existing YAML workflows and the
current runtime substrate.

## Source Material

Use these documents as the primary source material:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- active and in-progress Workflow Lisp backlog or design-gap items
- current run state, progress ledgers, iteration summaries, and repair artifacts

Specs and approved design contracts define correctness. These work instructions
define sequencing and constraints for this body of work.

## Work Order

1. Close implementation gaps against the full Workflow Lisp frontend design.
2. Prefer work that improves typed authoring, structured results, source mapping,
   lowering correctness, validation, and reusable procedure support.
3. Keep the frontend connected to the existing Core DSL, shared validation,
   semantic IR, executable IR, and runtime contracts.
4. Preserve existing YAML workflow compatibility while adding or refining Lisp
   frontend behavior.
5. Keep documentation aligned when a completed change affects author-facing
   Workflow Lisp behavior.

## Constraints

- Do not relax normative specs or approved design contracts to make an
  implementation easier.
- Do not treat reports, summaries, ledgers, or pointer files as semantic
  authority unless a contract explicitly says so.
- Do not migrate unrelated historical docs or workflows as part of this body of
  work.
- Do not introduce repo-wide enforcement for this body of work unless a selected
  work item explicitly requires it.
- Do not build a Lisp frontend that is merely YAML syntax with parentheses.
- Keep changes bounded to the selected obligation and its direct documentation or
  fixture implications.

## Documentation Expectations

When implementation changes affect user-visible Workflow Lisp behavior, update
the narrowest lasting documentation surface:

- specs or design docs for semantic contracts and lasting design decisions;
- the Lisp workflow drafting guide for authoring guidance;
- indexes for discoverability;
- run artifacts and ledgers for execution evidence.

Do not paste transient implementation churn into global specs.

## Completion Target

This body of work is complete when the full approved Workflow Lisp frontend
design has no remaining implementation gaps under the current specs and accepted
design documents, with compatibility preserved for existing YAML workflows.

## Out Of Scope

- General repo-wide documentation rules.
- Rewriting existing active drain workflows for this conceptual cleanup.
- Changing workflow management mechanics such as selector routing, resume
  behavior, terminal-state classification, or ledger update semantics.
- Reclassifying historical reports as executable work.
