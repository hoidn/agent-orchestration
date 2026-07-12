# Workflow Lisp Runtime-Native Drain Authoring

Status: reference target / regression checklist
Kind: architecture decision / authoring and migration target
Created: 2026-06-15
Scope: Workflow Lisp authoring ergonomics for parent drain workflows; typed
prompt inputs; private runtime context; consumer-side rendering; typed
projection; resource transitions; certified adapter retirement; and a working
Design Delta Drain `.orc` family as the acceptance target.

Current implementation status is tracked in
`docs/capability_status_matrix.md`. This document defines the desired
authoring shape and acceptance/regression checklist; it is not live completion
state.

Authority:

- Normative runtime and DSL behavior remains in `specs/`.
- `docs/design/workflow_lisp_frontend_specification.md` owns the parent
  Workflow Lisp language contract and WCC lowering route.
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  records the incorporated generic-core target for pure projection,
  materialized views, typed transitions, boundary authority classes, adapter
  retirement, and Design Delta cleanup; current contracts live in the frontend
  specification where incorporated.
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
  owns the private-checkpoint and consumer value-flow substrate.
- `docs/design/workflow_lisp_generic_resource_context_core.md` owns the
  simplified generic resource/context model.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  owns parent-callable workflow-family migration and promotion gates.
- `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` owns the
  shared owner-lane prerequisite ledger consumed by Section 9.1.
- `docs/design/workflow_command_adapter_contract.md` owns certified adapter
  boundaries.
- Private binding and provider target binding grammar are owned by the
  frontend/value-flow specs.
- This document does not by itself promote any `.orc` workflow to primary
  surface.

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
- `docs/design/workflow_lisp_consumer_side_rendering.md`
- `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
- `docs/design/workflow_lisp_generic_resource_context_core.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `specs/state.md`

## 1. Purpose

Workflow Lisp has enough typed workflow machinery to express parent drain
workflows, but migrated workflow families can still read like file-oriented
YAML translated into Lisp: long provider input lists, explicit report target
paths, body-level materialized views, public runtime context records, and
adapter calls for deterministic projection or state update.

This document defines the target authoring shape for a runtime-native drain
workflow. The goal is not to remove all files. The goal is to keep authored
workflow logic centered on typed domain values and typed transitions, while the
runtime owns private execution context and while rendering happens only at real
consumer seams.

The concrete acceptance target is the Design Delta Drain workflow family. The
target is complete only when that family has a working `.orc` translation whose
authored shape follows this design: provider calls receive typed prompt-input
records, runtime bookkeeping is private, simple projections are native typed
operations, durable files are boundary views or compatibility bridges, and
remaining Python helpers are certified adapters rather than hidden workflow
semantics.

## 2. Executive Decision

Adopt this authoring model:

```text
public workflow inputs
  -> typed domain request/state/action records
  -> typed provider, command, projection, and resource-transition results
  -> private runtime context supplied by lowering/runtime
  -> consumer-side rendering only at prompt/public/observability/bridge seams
  -> typed terminal result plus boundary views
```

Target-shape sketch:

```lisp
(let* ((action (select-next-action drain-state request))
       (result
         (match action
           ((RUN_BACKLOG_ITEM item)
            (run-work-item item))
           ((DRAFT_DESIGN_GAP gap)
            (draft-and-run-gap gap))
           ((DONE done)
            (finish-drain done))
           ((BLOCKED blocked)
            (block-drain blocked)))))
  result)
```

It should not require authors to thread runtime-owned values through ordinary
parameters:

```lisp
(run-work-item item item-ctx state-root artifact-root summary-path ...)
```

Internally, lowering and runtime may bind private context values such as
`RunCtx`, item/resource identities, checkpoint identities, generated output
targets, and view paths. Those values must be visible in executable contracts,
source maps, and Semantic IR, but not as public authored workflow inputs.

## 3. Problem

Migrated drain families can expose too much non-domain bookkeeping at the
authored surface:

- provider calls often take flat lists of paths and fields rather than a
  typed prompt subject;
- output target paths can appear beside semantic prompt inputs;
- report and summary views are materialized by producers even when the
  consumer is a prompt, public output, observability surface, or legacy
  bridge;
- runtime context records and generated paths can leak into call signatures;
- simple deterministic classification and bundle shaping can require command
  adapters;
- state/resource updates can hide behind scripts unless represented as typed
  transitions or certified adapters; and
- a workflow may compile while still depending on YAML-era pointer and
  path choreography.

This is a design-level issue because local cleanup cannot decide which values
are semantic domain data, which are private runtime mechanics, which are
consumer renderings, and which are compatibility bridges. Those distinctions
must be stable enough for lowering, shared validation, Semantic IR, runtime
resume, migration comparison, and authoring guidance.

## 4. Goals

- Make typed domain values the normal carrier between Workflow Lisp
  procedures.
- Let provider calls accept typed prompt-input records or values instead of
  long positional lists of files and scalar fields.
- Keep private runtime context, generated paths, checkpoint identity, and
  write roots out of public authored boundaries and ordinary user-facing call
  signatures.
- Render typed values at consumer seams: provider prompt injection, public
  workflow publication, or observability.
- Reserve body-level `materialize-view` for justified timed publications and
  low-level compatibility work.
- Replace deterministic Python helpers with pure typed projections where the
  operation is local, typed, and side-effect free.
- Represent durable state/resource mutation as typed resource transitions or
  certified transition adapters.
- Preserve provider/command structured-output authority through runtime-bound
  validated bundles.
- Keep remaining external Python/shell at certified adapter boundaries with
  typed inputs, typed outputs, declared effects, source maps, and a retirement
  condition when temporary.
- Produce a working Design Delta Drain `.orc` family that compiles, validates,
  runs with fake-provider or controlled smoke checks, and preserves the public
  behavior expected for the selected acceptance scope.

## 5. Non-Goals

- Do not remove files from the system. Source docs, provider reports, public
  artifacts, logs, checkpoints, compatibility bridges, and implementation
  agent edits may remain file-backed.
- Do not add arbitrary Lisp file IO, broad JSON manipulation, map/filter/sort
  libraries, or a Python-like scripting surface merely to remove adapters.
- Do not expose private runtime context as public workflow input syntax.
- Do not make rendered prompt text, markdown reports, pointer files, stdout,
  or debug YAML semantic authority.
- Do not weaken provider or command output-bundle validation.
- Do not require all legacy YAML compatibility views to disappear before the
  `.orc` family can be useful.
- Do not claim YAML-primary replacement without the promotion gate required by
  the migration parity design.

## 6. Design Principles

### 6.1 Typed Values First

Internal workflow composition should pass records, unions, enums, resources,
and transition results. A file path should appear in a typed value only when it
is domain data, a public authored input, a declared public output, a source
document, or a labeled compatibility bridge.

### 6.2 Consumer-Side Rendering

Rendering is owned by the consumer that needs bytes:

| Consumer | Authored workflow shape | Lowered/runtime behavior |
| --- | --- | --- |
| typed workflow step | pass typed value | no rendering |
| provider prompt | pass typed value in `:inputs` | prompt composition renders ephemerally |
| public output | declare publication policy | terminal boundary materializes view |
| observability | return typed terminal result | report/dashboard render derived view |
| legacy reader | declare bridge metadata | bridge materializes durable compatibility view |
| timed mid-run artifact | explicit `materialize-view` | durable view at authored point |

The default is no rendering. Rendering is an exception forced by a consumer
that cannot accept typed values directly.

Provider prompt rendering must support consumed-artifact reference views in
addition to full content injection. A provider may need to know that a consumed
artifact exists, where it lives, and what role it plays without paying the
prompt-token cost of embedding the full file. The target consume rendering
surface is therefore:

```yaml
consumes:
  - artifact: baseline_design
    prompt:
      mode: reference
      label: Baseline design
      description: Accepted baseline contract for compatibility checks.
```

Initial prompt modes are `content`, `reference`, and `none`. `content` preserves
the existing full consumed-artifact injection behavior. `reference` renders a
small provider-facing block containing the artifact label, resolved path or
value reference, and optional role metadata, but not the artifact body. `none`
keeps consume lineage and freshness without prompt rendering. This belongs to
the consume/prompt composition contract, not to ad hoc prompt prose or
boilerplate one-off reference artifacts.

### 6.3 Private Runtime Context

Domain functions should not ask users to provide runtime bookkeeping. The
authored call:

```lisp
(run-work-item item)
```

may lower to an executable call that receives a private item/resource context,
but that context is compiler/runtime-owned. It exists for generated path
allocation, checkpoint identity, idempotency, source maps, and resume, not for
domain authoring.

### 6.4 Small Native Operation Set

Adapter retirement should use a deliberately small native operation set:

- field access;
- record construction and update;
- union construction and `match`;
- enum/string/boolean equality and simple boolean operators;
- option/default handling;
- typed pure projection;
- materialized value views at declared seams; and
- typed resource transitions.

Operations outside this set remain candidates for certified adapters or later
designs. The target is workflow-safe expressiveness, not a general scripting
language.

### 6.5 Type-Derived Contract Spine

Runtime-native drain authoring requires a single typed contract spine, not
separate local rules for typechecking, output bundles, source maps, and resume.
The frontend should produce an explicit contract projection from:

```text
.orc type environment
  + WCC refined bindings and join parameters
  + authority-class annotations
  + source-map provenance
  -> typed contract projection
  -> Semantic IR contract entries
  -> Executable IR output/resource/artifact contracts
  -> runtime validators over concrete bundles, files, and resources
  -> source-mapped diagnostics and migration comparison
```

Compile-time typechecking and runtime validation remain different passes:
typechecking validates expressions, lexical scopes, refinements, and calls;
runtime validation checks concrete bundles, active variants, artifact
references, declared targets, resources, and persisted state. They must
consume the same projected contract model rather than rediscovering facts from
generated names, path conventions, or family-specific compiler hooks.

Projected union contracts are variant-scoped. For example, `DrainResult.DONE`
and `DrainResult.BLOCKED` may both expose a logical `summary` field, but the
executable identities, source-map entries, and output bundle fields are scoped
by `(union, variant, field)`. Promoted Workflow Lisp
routes reject unknown or inactive variant fields unless a declared
compatibility bridge or certified adapter policy explicitly normalizes them.

## 7. Target Authoring Shape

The common authoring path is domain-shaped. Authors should primarily write
domain records, unions, provider calls, `match`, named projections, and named
domain transitions. Runtime context, generated paths, renderer choices, bridge
files, checkpoint identity, and provider write targets are inferred, declared
once at boundaries, or hidden behind named library policies. Raw
`resource-transition`, explicit renderer/schema fields, bridge metadata, and
certified adapter declarations are substrate or advanced escape hatches, not the
ordinary drain body style.

### 7.1 Typed Provider Requests

Provider calls should pass named typed request records when the input has more
than a few fields. Prompt-subject records carry semantic facts for the provider;
provider write targets are separate role-classified bindings, not ordinary
prompt facts.

Copy-safe current shape:

```lisp
(defrecord ImplementationRequest
  (target_design TargetDesignDoc)
  (baseline_design BaselineDesignDoc)
  (approved_plan PlanDoc)
  (checks CheckSpec))

(provider-result providers.implementation.execute
  :prompt prompts.implementation.execute
  :inputs request
  :returns ImplementationAttempt)
```

The runtime renders `request` at the provider prompt seam. The provider output
still comes from the declared provider-result contract and runtime-bound
structured-output bundle.

Large stable reference documents should normally be consumed with prompt mode
`reference`, not full prompt content. For example, an implementation provider
can receive the current target design and execution plan as prompt content while
receiving the baseline design as a labeled path/reference to inspect only when
compatibility questions require it.

When a provider needs concrete report or bundle targets, those targets belong to
a provider-result target policy or a separate typed target binding with authority
class `provider_write_target`. They must not be indistinguishable from semantic
prompt inputs.

Flat provider input lists remain valid for small calls, but long lists are not
the target style for parent drain workflows.

### 7.2 Domain Actions

Drain selection should return typed actions:

```lisp
(defunion DrainAction
  (RUN_BACKLOG_ITEM (item WorkItem))
  (DRAFT_DESIGN_GAP (gap DesignGapRequest))
  (DONE (result DrainDone))
  (BLOCKED (result DrainBlocked)))
```

The `WorkItem` is semantic domain data: what work is being done, why it was
selected, and which contract applies. It does not carry raw state roots,
hidden write roots, checkpoint internals, generated temp paths, or generated
artifact bookkeeping.

### 7.3 Native Typed Projection

Deterministic reshaping should be native:

```lisp
(defun make-implementation-request
  ((item WorkItem)
   (plan ApprovedPlan))
  -> ImplementationRequest
  (record ImplementationRequest
    :target_design item.target_design
    :baseline_design item.baseline_design
    :approved_plan plan.plan_doc
    :checks item.checks))
```

This must not require a command step when it only constructs a typed value from
existing typed values.

### 7.4 Resource Transitions

The common authoring shape should be a named domain operation:

```lisp
(complete-work-item item terminal-result)
```

That operation lowers to a declared transition contract. Copy-safe current
substrate shape:

```lisp
(resource-transition
  :transition complete-work-item-transition
  :resource item-resource
  :expect-version item.version
  :request (record CompleteWorkItem
    :item item
    :terminal_result terminal-result))
```

The runtime or certified adapter enforces resource identity, expected version,
declared writes, idempotency, conflict behavior, resume behavior, audit
projection, source-map provenance, and Semantic IR effect visibility. Drain body
code should use raw `resource-transition` only for low-level libraries or
explicit adapter/transition definitions.

Transition contracts must be meaningful, not just present:

- preconditions are non-tautological and tied to request or resource state;
- idempotency fields include enough identity to avoid accidental cross-item or
  cross-run replay;
- closed domain statuses are enums or typed variants rather than free strings
  where the status set is known;
- audit projection records resource identity/version, request digest, result
  digest, source-map origin, and backend kind; and
- runtime-native and certified-adapter backends satisfy the same typed
  transition contract.

### 7.5 Boundary Publication

A workflow returns typed terminal results. Durable reports or summaries are
published by boundary policy:

Accepted entry-boundary policy shape:

```lisp
(defworkflow drain-design-deltas
  ((steering SteeringDoc)
   (target_design TargetDesignDoc)
   (baseline_design BaselineDesignDoc))
  -> DrainResult
  (:publish
    ((DONE.summary :role drain-summary :renderer canonical-json)
     (BLOCKED.summary :role drain-summary :renderer canonical-json)))
  ...)
```

The authored body should not contain terminal `materialize-view` boilerplate
for ordinary public reports.

### 7.6 Legacy Boundary Files

Legacy files should be deleted when no named public or legacy consumer remains.
The workflow body must not hand-author path construction for those files or use
them for internal composition.

For the Design Delta reference family, this specifically requires retiring
internal `*-compat` adapter procedures for selected-item, plan, implementation,
and finalization projection. Work-item routing should call a family-native typed
finalizer or a generic stdlib finalizer protocol directly. Compatibility
projections may remain only at public or legacy file/view boundaries, not
between ordinary `.orc` modules.

Completion also requires removing Design Delta-specific bridge augmentation
hooks from core compiler modules. Core compilation must not branch on
`lisp_frontend_design_delta/*` workflow names to inject runtime summary bridges
or other family-specific compatibility artifacts.

### 7.7 Private Context Parameters In Source

Private context must stay off promoted public entrypoints. Internal reusable
definitions may mention context types when those parameters are supplied by
hidden reusable-call binding or by ordinary internal composition.

Invalid promoted public boundary:

```lisp
(defworkflow drain
  ((run RunCtx)
   (target_design TargetDesignDoc))
  -> DrainResult
  ...)
```

Allowed internal reusable workflow shape:

```lisp
(defworkflow run-work-item
  ((phase_ctx PhaseCtx)
   (item WorkItem))
  -> WorkItemResult
  ...)
```

Preferred high-level caller shape:

```lisp
(run-work-item selected-item)
```

Compilation must distinguish these cases. Public-boundary inspection rejects
`RunCtx`, generated roots, checkpoint paths, and generated targets at promoted
entrypoints. Hidden-binding metadata, source maps, and Semantic IR explain any
private context supplied to internal calls. If a required private binding lacks a
runtime anchor or compile-time default, compilation fails closed.

## 8. Contracts And Interfaces

### 8.1 Frontend

The Workflow Lisp frontend must:

- typecheck provider `:inputs` values as typed prompt subjects;
- emit type-derived contract projections from the `.orc` type environment,
  WCC refinements, authority classes, and source-map provenance;
- derive variant-scoped executable output/resource/artifact contracts from
  projected record and union contracts;
- support typed prompt-input records without forcing materialized prompt files;
- support consumed-artifact prompt rendering modes for content, reference, and
  none;
- infer consumer-slot rendering where a unique renderer and authority class
  exists;
- lower publication policy to materialized-view kernel operations;
- keep private context bindings out of public authored boundaries;
- emit source maps and Semantic IR entries for inferred context, projection,
  rendering, and transition effects; and
- reject ambiguous renderer selection or unclassified path plumbing with
  actionable diagnostics.

### 8.2 Runtime

The runtime must:

- preserve provider and command structured-output authority;
- validate provider and command output bundles, resource transitions, resume
  records, and published views against the projected executable
  contracts rather than generated names or path conventions;
- provide private execution context needed for generated paths and resume;
- render typed prompt inputs at provider prompt composition;
- render consumed artifacts according to their declared prompt mode, including
  reference-only blocks that expose path and role metadata without embedding the
  full artifact body;
- execute or delegate typed resource transitions with version, idempotency,
  conflict, and audit semantics;
- materialize boundary publications from typed values; and
- keep materialized views as views unless a contract explicitly makes them a
  public artifact.

### 8.3 Adapter Registry

Certified adapters remain valid for external tools and legacy protocols. A
retained adapter must declare:

- behavior class;
- typed input and output contracts;
- structured output-bundle contract;
- declared state, resource, artifact, and view effects;
- path-safety rules;
- exit-code taxonomy;
- source-map behavior; and
- owner plus retirement condition when temporary.

### 8.4 Migration Parity

When migration promotion is evaluated, parity must compare public behavior:
typed terminal results, public outputs, declared resource-transition behavior,
and resume/reuse behavior. It must not treat successful compile, dry-run, or a
rendered summary as primary-surface promotion.

Parity is behavioral and contractual, not mechanical. It must not require the
`.orc` implementation to reproduce the YAML workflow's internal state-machine
mechanics, queue-file choreography, helper-script boundaries, checkpoint file
layout, or path-by-path update order. A different implementation shape is valid
when it preserves the public contract, typed terminal outcomes, declared
resource-transition semantics, artifact/public-output obligations, and
resume/reuse contract.

## 9. Dependencies And Sequencing

This target consumes the existing WCC route and post-foundation composition
work. Implementation should proceed in this order:

1. identify path-like and render-like fields in the Design Delta `.orc` family
   that should be replaced by typed values or private runtime context;
2. introduce typed prompt-input request records for provider calls;
3. replace deterministic helper scripts with pure typed projections where the
   closed expression surface is sufficient;
4. move ordinary terminal summaries and reports to boundary publication policy;
5. hide runtime context and generated targets behind private bindings;
6. convert durable state updates to typed transitions or certified transition
   adapters;
7. keep external tools and remaining legacy protocol work behind certified
   adapters; and
8. make the Design Delta Drain `.orc` family work as one parent-callable
   workflow family under the acceptance criteria below.

Work that can proceed independently:

- provider request-record refactors;
- projection replacement for local deterministic reshaping; and
- moving compatibility files to declared public/legacy boundaries when a live
  consumer still requires them.

Work that should wait for substrate support:

- removal of compatibility bridges required by YAML parity;
- defaulting all boundary publications to implicit rendering; and
- deleting certified adapters whose runtime-native replacement has not passed
  positive and negative behavior checks.

### 9.1 Shared Owner-Lane Prerequisites

Imported stdlib adoption claims depend on shared owner-lane capability
contracts that no single family owns. The prerequisite ledger lives in
`docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`; each
prerequisite there states one minimum contract, one minimum behavior check,
and one adoption-claim rule. The lanes are:

- the parent-loop lane for imported `std/drain::backlog-drain`:
  callable-child value return and the terminal responsibility split, parent
  terminal reprojection and branch-local terminal contract alignment, the
  fixed `gap-drafter` callable boundary and generic gap-payload leaf
  carriage, and family gap re-entry convergence;
- the phase-family boundary lane for item-context-first work-item
  composition: the fixed `run-item` workflow-ref shape, generic child-phase
  reuse, called-workflow result branching and terminal reprojection, no
  internal compatibility-carrier lane, and work-item summary ownership over
  imported `finalize-selected-item`; and
- `std/phase` owner-lane self-hosting on the ordinary imported-module
  compile and validation route.

The adoption-claim rule is uniform: a family may adopt request-record,
projection, transition, publication, and cleanup slices that do not depend
on a missing prerequisite, but it must not claim imported stdlib adoption by
re-implementing missing owner-lane behavior in family-local adapters,
wrapper workflows, widened boundaries, or compatibility rereads. When a
slice hits a missing prerequisite, stop the slice and select the
prerequisite gap.

## 10. Invariants And Failure Modes

- Typed values are semantic authority.
- Structured provider and command bundles are authority only after runtime
  validation.
- Rendered prompt text, summaries, pointer files, reports, and debug YAML are
  views unless explicitly contracted otherwise.
- Private runtime context must not appear as public authored input for a
  promoted `.orc` boundary.
- Generated paths must be allocated through `StateLayout` and recorded in
  source maps and Semantic IR.
- A provider input record may contain typed output targets only when those
  targets are explicitly classified as provider write targets, not semantic
  prompt facts.
- Ambiguous renderer selection fails before execution.
- A deterministic projection implemented by Python remains migration debt
  unless certified and justified.
- A resource transition must fail closed on version mismatch, undeclared
  writes, missing audit records, or idempotency conflict.
- Provider/command output bundles must validate through the projected
  variant-scoped executable contract: exactly one active variant is selected,
  active required fields are checked, inactive or unknown fields fail in
  promoted routes unless an explicit compatibility policy allows
  normalization, and diagnostics point back to authored union/record fields.
- Diagnostics for promoted routes must remain traceable from concrete runtime
  failures back to the authored type, variant, field, binder, projection, or
  transition.
- Terminal records, summaries, bridges, audit entries, and resource transitions
  must name a consumer and authority class. They are invalid as hidden
  prerequisites for ordinary typed value return.
- Test fixtures, mirrored fixture trees, checked manifests, and generated
  evidence files are verification vehicles, not architecture. They must not be
  promoted into completion requirements unless the changed source, runtime
  contract, or public boundary actually depends on them.

## 11. Implementation Boundaries

Implementation follows this design only if the default `.orc` authoring and
lowering path provides the behavior. The following do not satisfy the target:

- a test-only path that bypasses provider prompt composition;
- a helper script that writes the desired JSON while the `.orc` source still
  treats the file as state;
- a source-map entry for a generated path without public/private boundary
  inspection;
- a provider prompt that mentions an output target while the runtime lacks the
  corresponding typed binding;
- a report or summary that looks correct but is generated from markdown parsing
  or pointer files; or
- leaf workflow compile success without parent-callable drain execution.

The reference implementation target is the Design Delta Drain `.orc` family,
not an isolated teaching example.

## 12. Compatibility And Migration

Phase 1 migration milestone (evidence snapshot, 2026-07-12): the
`backlog-drain` conversion was proven through the `std/drain` generic procedure
and macro on the ordinary import/specialization/WCC route. At this milestone,
the Design Delta consumer owned the inline `repeat_until` and terminal
reprojection in its parent workflow rather than delegating the loop to a
generated child workflow; consumer parity and the F5 boundary contract passed.
The snapshot did not claim intrinsic retirement: the legacy phase-drain
lowering, form-specific specialization, and name-keyed validation paths still
remained for the gated Phase 2 deletion pass. This dated paragraph is an
immutable evidence record, not live completion state; consult
`docs/capability_status_matrix.md` and
`docs/plans/2026-07-07-drain-migration-g8-retirement.md` for current status.

Existing YAML workflows remain valid. The `.orc` family may keep
compatibility bridges for YAML-era files while parity requires them. Those
bridges must be labeled and generated from typed values, not manually
maintained by workflow body plumbing.

Existing `.orc` forms remain valid:

- explicit provider input lists;
- explicit `materialize-view`;
- raw command boundaries; and
- certified adapters.

The target style narrows which of those are acceptable for new high-level
parent drain code:

- long provider input lists should move to typed request records;
- ordinary terminal reports should move to publication policy;
- deterministic reshaping should move to pure typed projection;
- durable mutation should move to resource transitions; and
- raw command boundaries should remain only for external tools or certified
  legacy behavior.

### 12.1 Transitional Surface Retirement

Compatibility bridges and family-specific compiler checks are acceptable only
as migration scaffolding. They may let the `.orc` family run before the final
authoring shape is complete, but they are not themselves target completion.

Do not measure progress by accumulating compatibility-bridge bookkeeping. Progress
means deleting the bridge, isolating it at a declared public/legacy boundary, or
replacing the caller with typed stdlib/family composition.

This target does not reopen the lexical checkpoint/resume substrate. It
consumes the private checkpoint route and requires remaining resume-only
authored drain plumbing to be removed, hidden, or explicitly classified as
non-semantic compatibility.

Full target completion requires a retirement pass that shows:

- compatibility bridges needed only for YAML-era files have either been removed
  or are isolated at declared public/legacy boundaries with owner, consumer,
  schema, and retirement condition;
- body code no longer constructs compatibility paths, pointer files, or summary
  files by hand;
- `PhaseCtx`, `ItemCtx`, `DrainCtx`, selection, and recovery records are
  library/domain records backed by generic `RunCtx`, resource, transition, and
  `StateLayout` mechanics rather than privileged runtime scope categories; and
- `backlog-drain`, `finalize-selected-item`, and related phase/drain behavior
  are owned by `std/*` or family library modules through ordinary imported
  `.orc` composition, signature/effect checking, and typed transitions, not by
  Design-Delta-specific lowering or typecheck branches.
  The promoted route must not branch on literal compiler names such as
  `std/drain`, `backlog-drain`, `finalize-selected-item`, or `phase_drain`.

If a compiler/runtime hook remains after this target is claimed complete, its
contract must be generic enough to serve other workflow families without naming
phase, item, drain, selection, recovery, or Design Delta concepts.

### 12.2 Phase/Drain Stdlib Conversion Path

The current phase/drain lowering path should be converted by moving domain
contracts upward into stdlib or family `.orc` modules and narrowing compiler
support downward to generic linking, typing, effects, and runtime contracts.

The target ownership split is:

| Concern | Final owner |
| --- | --- |
| `RunCtx`, resource identity/version, transition commit, resume identity, path safety | runtime and generic frontend substrate |
| `Resource<TState>`, `Transition<TRequest, TResult>`, effect summaries, private binding | generic Workflow Lisp contracts |
| `PhaseCtx`, `ItemCtx`, `DrainCtx`, `SelectionResult`, `SelectedItemResult`, `GapResult` | `std/context`, `std/resource`, `std/drain`, or family modules |
| `backlog-drain`, `finalize-selected-item`, `complete-work-item`, selection/gap/item routing helpers | imported `.orc` stdlib/family procedures |
| Design Delta selector, architect, work-item, recovery, and terminal result shapes | `lisp_frontend_design_delta/*` modules |

Conversion should proceed in this order:

1. Define the stdlib/family records, unions, and procedures in `.orc` modules
   with ordinary exported signatures. The source of truth for drain behavior
   becomes imported code, not Python lowering helpers.
2. Replace frontend checks that name `DrainCtx`, `ItemCtx`, selected-item
   variants, or gap variants with generic capability checks: workflow-ref
   signature compatibility, closed union/record types, required effects,
   declared transition contracts, and private-context availability.
3. Lower `backlog-drain` and `finalize-selected-item` through the ordinary
   import/specialization/WCC path. Any ergonomic surface may be a macro or
   stdlib wrapper, but it must expand to ordinary calls, `match`, loops,
   projections, and `resource-transition` operations.
4. Keep any intrinsic lowering branch only as a schema-1 or compatibility
   route while the stdlib route is checked against the public contract and
   declared semantic effects.
5. Delete or quarantine Design-Delta-specific assumptions from compiler
   modules once the stdlib route passes compile, shared validation, and the
   minimal runtime check for its public contract.

The final stdlib route may still use compiler support for generic features such
as imported workflow refs, WCC control lowering, hidden private bindings,
source-map frames, typed resource transitions, and materialized-view kernels.
It must not require a compiler branch that understands "the Design Delta drain"
or exact YAML state-machine mechanics.

## 13. Behavioral Acceptance

### 13.1 Static And Compile-Time Checks

- Compile typed provider request-record examples.
- Compile provider `:inputs request` where `request` is a typed record.
- Reject ambiguous renderer defaults for provider inputs.
- Reject public `RunCtx`, generated write-root, checkpoint path, or
  generated-internal output target at a promoted boundary.
- Reject unexplained body-level `materialize-view` outside timed publication
  or compatibility bridge surfaces.

### 13.2 Runtime Checks

- Provider prompt composition renders typed request records with provenance.
- Provider output remains the declared structured bundle, not prompt evidence.
- Boundary publication materializes terminal summaries from typed terminal
  results.
- Resource transitions validate versions, idempotency keys, write sets, and
  audit projections.
- Resume does not require public authored checkpoint or generated path inputs.

### 13.3 Authoring Ergonomics Gate

Acceptance is based on the authored surface and executable behavior. Work that
only refreshes derived artifacts, without changing behavior or deleting obsolete
mechanics, is out of scope for this target.

### 13.4 Design Delta Drain Acceptance

Reference-family acceptance is demonstrated by the real promoted route. Use the
narrowest runnable checks that exercise the changed behavior; fixture or mirror
updates are incidental test maintenance, not independent target obligations.

The target is complete only when the Design Delta Drain `.orc` family:

- compiles through the WCC route;
- passes shared validation;
- can be dry-run or smoke-run as a parent-callable workflow family;
- uses imported stdlib/family procedures as ordinary typed child calls whose
  returned unions can be matched and projected by the parent;
- reaches selected-item, gap, blocked, exhausted, and terminal routes without
  handwritten family loop/fan-in reimplementation;
- keeps runtime context, generated roots, checkpoint paths, and compatibility
  carriers out of ordinary public and internal call signatures;
- reaches typed terminal return without interior summary-file materialization;
- uses typed provider request records for plan, implementation, selector,
  architect, review, fix, and recovery-classifier provider calls where the
  input is nontrivial, with write targets classified separately from
  prompt-subject data;
- hides runtime context and generated paths from public authored inputs;
- keeps private context parameters limited to internal definitions;
- uses typed projection instead of Python for deterministic local reshaping
  where the closed expression surface is sufficient;
- represents durable drain/work-item/recovery state changes as named domain
  operations that lower to typed transitions or certified transition adapters;
- contains no body-level `materialize-view` except justified timed
  publications or low-level compatibility checks;
- keeps remaining Python helpers only as certified external or legacy adapters;
- retires transitional compatibility surfaces from ordinary internal
  composition;
- represents phase, item, drain, selection, and recovery behavior through
  library/domain records and imported stdlib/family modules over the generic
  resource/context core, not through family-specific compiler branches;
- produces the public terminal outputs expected by the public boundary; and
- distinguishes working parent-callable `.orc` execution from YAML-primary
  promotion.

## 14. Declarative Acceptance Scenario

Initial state: the Design Delta Drain family has a YAML primary and an `.orc`
candidate under `workflows/library/lisp_frontend_design_delta/`.

Compile entrypoint:

```bash
python -m orchestrator compile \
  workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file \
    workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file \
    workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file \
    workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Runtime acceptance additionally requires the equivalent supported `.orc`
dry-run or smoke entrypoint for the Design Delta Drain family, with the
implementation plan recording the exact public inputs used for that smoke.

Expected result:

- the workflow compiles through WCC and passes shared validation;
- public inputs are target design, baseline design, steering/configuration,
  provider aliases, and any explicitly accepted compatibility inputs;
- public inputs do not include `RunCtx`, item context, generated write roots,
  checkpoint paths, internal state roots, or generated bundle targets;
- provider calls receive typed request records or small typed values;
- provider write targets are separate role-classified bindings, not ordinary
  semantic prompt facts;
- prompt composition renders provider input values at the provider seam;
- selection, work-item routing, terminal classification, and summary shaping
  are ordinary typed logic, typed projections, or certified adapters;
- drain/work-item/recovery state changes are named domain operations that lower
  to typed transitions or certified transition adapters;
- public summaries and legacy bundles are produced by publication policy or
  bridge metadata; and
- the run produces public terminal state and artifacts without
  requiring exact replication of YAML's internal state-machine mechanics or
  observability-only writer side effects.

Forbidden result:

- the `.orc` source succeeds only by passing many raw paths through provider
  inputs and call signatures;
- parity requires the `.orc` family to preserve YAML's internal helper-script
  boundaries, queue-file choreography, checkpoint paths, or state update order
  instead of comparing the public contract and declared semantic effects;
- a Python helper performs unclassified deterministic routing or summary
  shaping;
- a rendered report, pointer file, stdout payload, or debug YAML projection
  becomes semantic routing authority;
- runtime context appears as an ordinary public authored input; or
- compile/dry-run success is presented as YAML-primary promotion.

## 15. Success Criteria

This target succeeds when:

- the authoring guidance for runtime-native drain workflows is documented and
  discoverable;
- the Design Delta Drain `.orc` family has a working parent-callable
  translation following this design;
- parent composition consumes child workflow results as ordinary typed values;
  publication, resource transitions, and adapter calls are declared effects over
  those values, not prerequisites for returning them;
- internal compatibility carriers and summary files are absent from ordinary
  stdlib child-call composition, or isolated at declared public/legacy
  boundaries while a live consumer remains;
- the common drain body uses named domain operations rather than exposing
  routine runtime bookkeeping;
- typed provider request records replace long positional provider input lists
  in the reference family;
- provider write targets are separated from semantic prompt-subject records;
- private runtime context and generated paths are hidden from public authored
  boundaries;
- consumer-side rendering handles prompt inputs, ordinary public summaries,
  observability views, and compatibility bridges;
- consumed-artifact prompt rendering supports content, reference-only, and none
  modes, so large stable references can preserve lineage without full prompt
  injection;
- deterministic projection no longer requires Python where the closed
  expression surface is sufficient;
- durable state/resource updates are typed transitions or certified transition
  adapters;
- remaining Python helpers are certified external/legacy boundaries, not hidden
  semantic glue;
- transitional compatibility surfaces are retired from ordinary internal `.orc`
  composition;
- Design Delta selected-item, plan, implementation, and finalization
  `*-compat` adapter procedures are retired from internal work-item routing in
  favor of a family-native typed finalizer or generic stdlib finalizer protocol;
- Design Delta-specific compile-result augmentation hooks are removed from core
  compiler modules;
- phase/drain/item/recovery behavior is implemented as ordinary stdlib or
  family-library Workflow Lisp over generic context/resource mechanics rather
  than as family-specific compiler lowering;
- behavioral changes preserve typed provenance through source maps, Semantic
  IR, and runtime validation for private context, projection, rendering,
  bridge, transition, and output contracts; and
- migration parity can evaluate the `.orc` family without treating rendered
  files, reports, or exact YAML state-machine implementation mechanics as
  semantic authority. YAML-primary replacement remains owned by the separate
  migration parity and promotion gates.

## 16. Stop Or Revise Criteria

Revise this target if implementation requires:

- exposing private runtime context in public `.orc` syntax;
- adding broad arbitrary file IO or general scripting primitives to Workflow
  Lisp;
- treating rendered files as semantic authority;
- weakening provider/command structured-output validation;
- making runtime validation infer typed output, variant, resource, bridge,
  resume, or parity semantics from generated step names, path conventions, or
  family-specific compiler hooks instead of projected executable contracts;
- hiding resource mutation in uncertified adapters;
- working around a missing shared owner-lane prerequisite from
  `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` instead of
  landing the prerequisite gap: for example, re-implementing parent-loop,
  gap-lane, or child-phase behavior in family-local adapters or wrapper
  workflows, widening fixed stdlib workflow-ref shapes, flattening typed
  payloads into public or path-heavy parameters, rereading compatibility
  bundles, forcing selector outcomes to fake convergence, making side effects
  prerequisites for typed value return, or patching missing shared stdlib
  type/export/import resolution inside a family migration slice;
- keeping Design Delta-specific bridge augmentation in core compiler modules;
- preserving compatibility scaffolding or Design-Delta-specific phase/drain
  compiler hooks as the final implementation shape;
- making consumer rendering invisible in Semantic IR or source maps; or
- depending on a special-case drain compiler branch instead of WCC and ordinary
  stdlib composition.

## 17. Documentation Impact

If accepted and implemented, update:

- `docs/design/README.md` to route readers to this target for
  runtime-native drain authoring;
- `docs/index.md` if this becomes a primary reading path;
- `docs/lisp_workflow_drafting_guide.md` with the target authoring shape and
  examples;
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
  to cross-reference this document as the concrete reference-family
  acceptance target; and
- Design Delta Drain migration plans or gap designs that still describe
  body-level rendering, public runtime context, or Python helper routing as
  the desired end state.

## 18. Implementation Handoff

A later implementation plan should be organized around the reference family:

1. identify the internal path, context, rendering, projection, adapter, and
   transition surfaces that must be removed or converted;
2. introduce typed request records;
3. add or finish lowering for implicit provider-input rendering and boundary
   publication;
4. convert deterministic helpers to typed projections;
5. convert state updates to typed transitions or certified adapters;
6. simplify the `.orc` source;
7. run compile, shared validation, and focused dry-run/smoke checks for the
   changed behavior; and
8. remove obsolete follow-up text after the working reference family supports the
   behavior.
