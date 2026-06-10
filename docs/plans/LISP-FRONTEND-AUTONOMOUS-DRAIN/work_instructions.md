# Workflow Lisp Post-Foundation Composition Drain Work Instructions

Status: active work instructions

These instructions retarget the existing `LISP-FRONTEND-AUTONOMOUS-DRAIN`
workflow state to the post-foundation composition and stdlib migration body of
work. The state root, progress ledger, artifact roots, and completed design-gap
history are reused on purpose so the drain does not redo already-completed
Workflow Lisp frontend or runtime-foundation implementation gaps.

## Objective

Drain implementation gaps required by
`docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
while preserving the baseline Workflow Lisp frontend contract.

This body of work starts after the runtime migration foundation target. It
focuses on making Workflow Lisp composition and stdlib reuse parent-callable
instead of stopping at compileable leaves. The priority surfaces are:

- nested structured-control composition;
- union-result normalization and variant-scoped output identity;
- private executable context and hidden reusable-call binding;
- imported/std `.orc` and `review-revise-loop` composition inside branches;
- typed projection and selector/bundle materialization;
- certified adapter declarations and resource-transition ownership; and
- parent-callable workflow-family parity evidence.

## Source Material

Use these documents as the primary source material:

- target design: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- unchanged baseline design: `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_runtime_closures_boundary.md`
- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
- `docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/parent_drain_readiness_blockers.md`
- `specs/io.md`
- `specs/dsl.md`
- `specs/providers.md`
- `specs/state.md`
- current run state, progress ledgers, iteration summaries, and repair artifacts

Specs and approved design contracts define correctness. These work instructions
define sequencing and constraints for this body of work.

## Reused State Policy

The existing `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json` is
reused. Its completed design-gap history remains meaningful: those gaps are
already handled under the unchanged baseline or completed runtime-foundation
target and should not be selected again unless the post-foundation composition
target introduces a specific regression or follow-up obligation.

The workflow should select or draft only work that is still relevant to the
post-foundation composition target. Existing completed frontend and foundation
gaps are context, not fresh work.

## Work Order

1. Prefer the P0 gaps called out by the target design: nested structured
   control, private executable context, and run-state/resource-transition
   ownership.
2. Treat the design-delta drain findings report as concrete evidence of what
   blocks parent-callable `.orc` workflow-family migration.
3. Preserve public authored-YAML compatibility unless a versioned spec change
   intentionally widens it.
4. Preserve the unchanged frontend baseline design and the completed runtime
   foundation while adding post-foundation composition support around them.
5. Do not draft a parent drain wrapper before its prerequisites are satisfied:
   nested composition, private context, typed projection, certified adapters or
   resource transitions, and parent-callable parity labels.
6. Keep documentation aligned when completed work changes a user-visible
   Workflow Lisp, runtime, provider, adapter, state/resource, or
   migration-promotion behavior.

## Temporary Reconciliation Gate

- Do not select new gaps that modify Workflow Lisp lowering, WCC, control
  dispatch, match/loop lowering, phase scope, procedure lowering, or workflow
  call lowering until `feat/wcc-middle-end` is integrated with this branch.
- If a selected gap requires those files, stop and select the WCC/post-foundation
  reconciliation work first.
- Orthogonal lanes may continue only when they avoid compiler/lowering files.

## Constraints

- Do not reset or discard completed frontend-drain history merely because the
  target design changed.
- Do not select old completed design gaps unless the post-foundation
  composition target requires a new, distinct follow-up.
- Do not relax normative specs or approved design contracts to make an
  implementation easier.
- Do not treat reports, summaries, ledgers, pointer files, materialized value
  views, or debug YAML as semantic authority unless a contract explicitly says
  so.
- Do not migrate unrelated historical docs or workflows as part of this body of
  work.
- Do not introduce repo-wide enforcement unless a selected work item explicitly
  requires it.
- Do not treat leaf compile success as parent-callable or promotable workflow
  family evidence.
- Keep changes bounded to the selected obligation and its direct documentation,
  spec, fixture, or runtime implications.

## Documentation Expectations

When implementation changes affect user-visible behavior, update the narrowest
lasting documentation surface:

- specs for normative runtime/provider/DSL/state obligations;
- design docs for lasting architecture decisions;
- the Lisp workflow drafting guide for authoring guidance;
- indexes for discoverability;
- run artifacts and ledgers for execution evidence.

Do not paste transient implementation churn into global specs.

## Completion Target

This body of work is complete when the post-foundation composition target has
no remaining implementation gaps under the unchanged baseline frontend design,
completed runtime foundation, and current specs, with compatibility preserved
for existing YAML workflows.

## Out Of Scope

- Reopening completed frontend-drain gaps without a target-design-specific
  reason.
- Rewriting the existing drain workflow mechanics.
- Changing selector routing, resume behavior, terminal-state classification, or
  ledger update semantics unless selected as an explicit post-foundation
  composition gap.
- Reclassifying historical reports as executable work.
