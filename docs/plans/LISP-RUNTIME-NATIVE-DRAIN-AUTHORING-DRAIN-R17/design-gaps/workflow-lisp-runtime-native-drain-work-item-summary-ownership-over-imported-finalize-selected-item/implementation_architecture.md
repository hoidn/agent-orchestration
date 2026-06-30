# Work-Item Summary Ownership Over Imported Finalize-Selected-Item Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-work-item-summary-ownership-over-imported-finalize-selected-item`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline design: `docs/design/workflow_lisp_frontend_specification.md`
Command-adapter authority: `docs/design/workflow_command_adapter_contract.md`

## Scope

This slice covers exactly the Section 9.2.5 Design Delta work-item summary
ownership gap:

- imported `std/resource::finalize-selected-item` must return the typed
  selected-item result without requiring `run-work-item` to materialize a
  work-item summary file first;
- `run-work-item` must return typed `WorkItemResult` values whose summary
  value is semantic authority;
- `artifacts/work/item_summary.json` should not be produced by ordinary
  internal composition;
- blocked-recovery summary durability must not depend on
  `record-work-item-blocked-recovery-summary` as the mechanism that permits
  typed finalizer return.

Out of scope:

- redesigning `std/resource::finalize-selected-item` itself;
- changing `std/drain::backlog-drain` loop semantics;
- changing WCC, Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, variant proof, pointer authority, provider output, or command
  structured-output contracts;
- changing unrelated `run_state_path` carriers not needed for this summary
  lane;
- changing plan, implementation, selector, architect, or recovery-classifier
  provider request records;
- deleting genuine external tools or certified adapters unrelated to work-item
  summary durability;
- claiming YAML-primary promotion.

This is an implementation architecture for one family-owned gap. It is not a
replacement product design or a broad runtime-native drain roadmap.

## Problem Statement

The current checkout already has the typed stdlib finalizer route:
`orchestrator/workflow_lisp/stdlib_modules/std/resource.orc` exports
`finalize-selected-item-proc`, which returns `SelectedItemResult` through a
typed match over plan and implementation results plus a runtime-native
`resource-transition`.

The Design Delta work-item route still turns the selected-item result into a
body-owned summary-file prerequisite:

- `workflows/library/lisp_frontend_design_delta/work_item.orc` defines
  `materialize-canonical-work-item-summary`, which renders
  `WorkItemSummaryValue` to `resolved.item_summary_target_path`.
- `run-work-item` repeatedly computes a `PendingWorkItemResult`, projects its
  typed summary, materializes that summary, and then constructs
  `WorkItemResult` with the materialized `summary-path`.
- blocked-recovery branches call
  `record-work-item-blocked-recovery-summary`, which both records a transition
  and materializes a work-item-context view before returning
  `WorkItemSummaryValue`.
- the work-item body still contains the canonical summary materialization that
  Section 9.2.5 says must leave ordinary body composition.

The implementation problem is therefore not to invent a new finalizer. It is to
make typed work-item return independent of summary-file rendering.

## Design Constraints

- Typed `WorkItemSummaryValue` and `WorkItemResult` values are semantic
  authority. Rendered summaries are not internal workflow state.
- Imported `finalize-selected-item` stays the typed stdlib route. This slice
  must not add a Design Delta-specific compiler lowerer, wrapper workflow whose
  only purpose is proof preservation, or command adapter for finalizer
  semantics.
- Resource mutation remains `resource-transition` through declared transitions
  or certified migration adapters. New Python or shell summary writers are
  forbidden by the command-adapter contract.
- Outside consumers of `WorkItemResult.summary-path` must follow the same rule:
  use the returned typed value for workflow meaning, and use `summary-path`
  only outside ordinary internal workflow composition.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- The request's `existing-architecture-index.md` lists no prior architecture
  documents for this R17 slice.
- Adjacent prior context for the same selected gap was reviewed from
  `state/workflow_lisp/calls/20260629T213350Z-jxbmmn/.../work_item_context.md`;
  its referenced R16 architecture file is not present in the checkout.
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-literal-name-stdlib-intrinsic-retirement/implementation_architecture.md`

### Decisions Reused

- From the prior transition finalizer lane: typed terminal return is separate
  from resource mutation and resume checkpoint effects.
- From literal-name stdlib intrinsic retirement: promoted `finalize-selected-item`
  behavior is owned by imported `std/resource` composition, not compiler
  literal-name branches.
- From the command-adapter contract: hidden workflow semantics may be typed
  procedures, typed calls, certified adapters, or runtime-native effects only;
  this slice chooses typed values and adds no scripts.
- From the frontend baseline: `materialize-view` is a representation over a
  typed value, and source maps/effect graphs must expose generated
  materialization.

### New Decisions In This Slice

- Treat `materialize-canonical-work-item-summary` as invalid in ordinary
  `run-work-item` body composition for the promoted route.
- Treat `record-work-item-blocked-recovery-summary` as invalid when it is used
  to make a blocked-recovery typed return possible. A blocked-recovery branch
  may still record durable recovery state through a named transition, but that
  transition must not also be the summary-rendering prerequisite for return.
- Keep `WorkItemResult.summary` as the family-owned typed summary carrier.
  Remove `summary-path` from ordinary internal composition.

### Conflicts Or Revisions

- Existing tests currently tolerate
  `materialize-canonical-work-item-summary` inside `run-work-item` while
  rejecting the same materialization in narrower stdlib subroutes. This slice
  revises that tolerance: the promoted work-item route should no longer
  contain body-owned canonical summary rendering.
- No shared concepts such as spans, diagnostics, Core Workflow AST, Semantic
  Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof are
  redefined here.

## Ownership Boundaries

This slice may change:

- `workflows/library/lisp_frontend_design_delta/work_item.orc`
  - remove body-owned summary materialization from `run-work-item`;
  - construct `WorkItemResult` directly from typed `PendingWorkItemResult` /
    `WorkItemSummaryValue`;
  - keep calls to imported `finalize-selected-item-proc` as typed finalizer
    calls, not as summary renderers.
- `workflows/library/lisp_frontend_design_delta/types.orc`
  - remove or narrow `WorkItemResult.summary-path` when it is only an internal
    carrier.
- `workflows/library/lisp_frontend_design_delta/transitions.orc`
  - split blocked-recovery durable state recording from summary rendering if
    the current helper remains necessary for state mutation;
  - remove or quarantine summary-writer helpers that are no longer referenced
    by the promoted route.
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/`
  - keep fixture modules aligned with the production Design Delta work-item
    route.
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  - assert typed work-item return works without body-owned summary
    materialization.

Shared compiler/runtime modules should be relied on rather than changed. A
compiler change is in scope only if ordinary typed return through the existing
generic route cannot express this slice; such a change must remain generic and
must not name Design Delta, work-item, summary, or finalizer concepts in core
lowering.

## Source Surface Contract

The promoted Design Delta work-item source should have this shape:

- phase and implementation branches produce typed `PendingWorkItemResult`;
- branch-local calls to imported `finalize-selected-item-proc` prove and record
  selected-item outcome where needed;
- typed projection constructs `WorkItemResult` from the pending result without
  rendering the summary first;
- summary rendering is absent from ordinary internal composition;
- blocked-recovery state recording uses a named transition over typed inputs,
  while the returned summary value remains a typed record.

Allowed implementation shapes:

- pure typed projection from `PendingWorkItemResult` to `WorkItemResult`;
- a named transition that records blocked-recovery or terminal state without
  rendering the summary as a hidden prerequisite.

Forbidden implementation shapes:

- body-level `materialize-view` calls in `run-work-item` that create
  `item_summary.json` before `WorkItemResult` can be returned;
- summary writer helpers whose output path is required to construct or route
  typed terminal values;
- report parsing, pointer-file reads, stdout JSON, or bundle rereads to recover
  summary fields;
- new command adapters or scripts for summary shaping;
- widening `run-item`, `run-selected-item-stdlib`, or child phase signatures
  solely to thread summary paths;
- moving `summary-path` into provider prompt subjects or treating it as domain
  semantic data.

## Feasibility Proof

This slice is feasible without a new language feature:

- `WorkItemResult` already carries a typed `summary` field in every variant.
- `project-work-item-result-summary` already proves that summary extraction is
  pure typed projection over `PendingWorkItemResult`.
- `materialize-pending-work-item-result` already centralizes construction of
  `WorkItemResult`; it can be replaced or narrowed to a typed projection that
  does not require `WorkReport` input for semantic return.
- `std/resource::finalize-selected-item-proc` already returns
  `SelectedItemResult` from typed plan/implementation unions and a declared
  transition.

The unproven part that the implementation must demonstrate is simpler: typed
work-item return must not depend on `artifacts/work/item_summary.json`.

## Acceptance Conditions

- `run-work-item` compiles and validates while returning typed `WorkItemResult`
  values without calling `materialize-canonical-work-item-summary` or any
  equivalent body-owned summary materializer.
- `run-selected-item-stdlib` can consume the typed child result and return
  `SelectedItemResult` without requiring the summary file to exist as semantic
  state.
- completed, terminal-blocked, and blocked-recovery routes keep the same
  typed terminal classification and blocker-class behavior as the current
  Design Delta route.
- `artifacts/work/item_summary.json` is absent from ordinary internal
  composition.
- `record-work-item-blocked-recovery-summary` is removed from ordinary
  promoted work-item routing, or reduced to a clearly named state-transition
  helper that does not render or authorize summary files.
- source maps expose imported finalizer calls, typed projections, transitions,
  and source provenance.
- no new scripts, command steps, legacy adapters, report parsers, pointer
  files, or Design Delta-specific compiler branches are introduced.
