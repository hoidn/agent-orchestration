# Workflow Lisp Runtime Migration Foundation Drain Work Instructions

Status: active work instructions

These instructions retarget the existing `LISP-FRONTEND-AUTONOMOUS-DRAIN`
workflow state to the runtime migration foundation body of work. The state root,
progress ledger, artifact roots, and completed design-gap history are reused on
purpose so the drain does not redo already-completed Workflow Lisp frontend
implementation gaps.

## Objective

Drain implementation gaps required by
`docs/design/workflow_lisp_runtime_migration_foundation.md` while preserving the
baseline Workflow Lisp frontend contract.

This body of work is narrower than the previous autonomous frontend drain. It
focuses on the runtime and migration foundation needed before additional
Workflow Lisp promotion work depends on:

- command structured-output conformance;
- frontend-lowered typed value transport;
- provider structured-output target binding;
- migration promotion gate hardening; and
- generated state/path allocation ownership.

## Source Material

Use these documents as the primary source material:

- target design: `docs/design/workflow_lisp_runtime_migration_foundation.md`
- unchanged baseline design: `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
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
already handled under the unchanged baseline and should not be selected again
unless the new target design introduces a specific regression or follow-up
obligation.

The workflow should select or draft only work that is still relevant to the
runtime migration foundation target. Existing completed frontend gaps are
context, not fresh work.

## Work Order

1. Prefer gaps that unblock the target design's five foundation tranches.
2. Treat runtime/spec/CLI/provider/frontend seams as first-class implementation
   boundaries when the target design requires them.
3. Preserve public authored-YAML compatibility unless a versioned spec change
   intentionally widens it.
4. Preserve the unchanged frontend baseline design while adding runtime
   foundation support around it.
5. Keep documentation aligned when completed work changes a user-visible
   Workflow Lisp, runtime, provider, or migration-promotion behavior.

## Constraints

- Do not reset or discard completed frontend-drain history merely because the
  target design changed.
- Do not select old completed design gaps unless the runtime foundation target
  requires a new, distinct follow-up.
- Do not relax normative specs or approved design contracts to make an
  implementation easier.
- Do not treat reports, summaries, ledgers, pointer files, materialized value
  views, or debug YAML as semantic authority unless a contract explicitly says
  so.
- Do not migrate unrelated historical docs or workflows as part of this body of
  work.
- Do not introduce repo-wide enforcement unless a selected work item explicitly
  requires it.
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

This body of work is complete when the runtime migration foundation target has
no remaining implementation gaps under the unchanged baseline frontend design
and current specs, with compatibility preserved for existing YAML workflows.

## Out Of Scope

- Reopening completed frontend-drain gaps without a target-design-specific
  reason.
- Rewriting the existing drain workflow mechanics.
- Changing selector routing, resume behavior, terminal-state classification, or
  ledger update semantics unless selected as an explicit runtime-foundation gap.
- Reclassifying historical reports as executable work.
