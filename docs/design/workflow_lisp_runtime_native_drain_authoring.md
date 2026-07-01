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
selected, which contracts apply, and which typed artifacts are expected. It
does not carry raw state roots, hidden write roots, checkpoint internals, or
generated temp paths.

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
code should use raw `resource-transition` only for low-level libraries,
fixtures, or explicit adapter/transition definitions.

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
- positive and negative fixtures;
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
8. keep external tools and remaining legacy protocol work behind certified
   adapters; and
9. make the Design Delta Drain `.orc` family work as one parent-callable
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
  positive and negative fixtures.

### 9.1 Shared Parent-Loop Prerequisite

For any parent-callable family that intends to replace a handwritten
select/run/gap/repeat loop with imported `std/drain/backlog-drain`, the shared
stdlib owner lane must already support the parent's required routing semantics.
The minimum contract is:

- `SelectedItemResult.CONTINUE` may re-enter selection instead of forcing
  immediate terminal completion;
- direct selector-blocked outcomes are representable as typed terminal routing;
- gap work or blocked-recovery work may return control to selection when the
  family semantics require it; and
- typed iteration/accounting remains valid across repeated selected-item passes
  and authored exhaustion.

Until that shared contract exists, a family may still adopt request-record,
projection, transition, and publication slices, but it must not
claim imported `backlog-drain` adoption by re-implementing missing parent-loop
behavior in family-local adapters or handwritten compatibility wrappers.

#### 9.1.0 Callable-Child Value Return Over Imported `backlog-drain`

For families whose promoted route preserves imported `std/drain::backlog-drain`
as a callable owner boundary, the shared parent/drain owner lane must first
support ordinary typed child value return. A simple call to imported
`backlog-drain` should return `DrainResult<TSummary>` to the parent without
requiring terminal publication, summary materialization, run-state-file
mutation, or drain-outcome recording as part of value return.

The minimum contract is:

- the parent workflow may preserve loop delegation as one call to imported
  `backlog-drain` while the child owner boundary still owns the `repeat_until`
  loop and its typed accumulator;
- the child route may materialize terminal classification from carried loop
  state and return the typed terminal `DrainResult` without falling back
  to stale direct `EmitDrain*`-style normalization or caller-owned terminal
  fan-in;
- optional terminal effects such as `record-drain-outcome`, public
  publication, audit projection, or external resource mutation are expressed as
  explicit boundary/resource forms outside the core `backlog-drain`
  value-return contract;
- shared validation accepts the loop-frame refs, nested-step refs, and
  exhaustion-carried terminal fields required by that route, with authored
  exhaustion staying within the accepted `repeat_until` output constraints
  rather than reopening ad hoc non-scalar terminal overrides; and
- the route does not depend on family-local wrappers, same-file-only special
  cases, compiler-name allowlists, rereading compatibility bundles, or
  compatibility-only marker steps to manufacture the returned value.

The minimum behavior check for this contract is:

- one compile/shared-validation fixture where the parent route lowers to one
  call to imported `backlog-drain` and the child owner boundary both owns the
  loop and returns a typed `DrainResult`;
- one runtime or smoke fixture showing that empty, completed, blocked, and
  exhausted callable-child terminals return the same typed result shape through
  ordinary child-call value return; and
- a positive check that the accepted route works for both imported and
  same-file promoted-callable `backlog-drain` authoring shapes without
  reopening handwritten terminal normalization.

If a family still needs durable terminal effects, those effects are separate:

- `:publish` materializes public terminal summaries from the returned typed
  value;
- a named domain transition records external resource state when there is a
  real external resource to mutate; and
- helpers such as `record-drain-outcome` are not prerequisites for returning
  `DrainResult<TSummary>`.

Until that route works, a family may still adopt request-record, projection,
transition, and publication slices, but it must not claim full
imported `backlog-drain` adoption on the callable owner-boundary route when the
child terminal value path still depends on compatibility-only normalization,
run-state-file side effects, or family-local repair wrappers.

##### 9.1.0.1 Terminal Responsibility Split

Do not use "terminal finalization" as a bundled mechanism. The target model
separates four lanes:

- child-call value return: imported `backlog-drain` returns
  `DrainResult<TSummary>` as an ordinary typed child-workflow value;
- variant/provenance preservation: refined match binders, `requires_variant`
  provenance, source maps, and variant-scoped contracts survive child calls and
  terminal reprojection;
- declared terminal effects: publication, resource transition, adapter calls,
  or external audit events run only when explicitly declared by a
  boundary/resource contract; and
- migration checks compare public behavior, typed terminal results, declared
  resource effects, artifacts, and resume/reuse behavior without becoming
  internal authoring semantics.

Pure helpers, effectful procedures, and workflow entrypoints share the same
typed return-value model. A `defworkflow` is special because it is an
executable/resumable boundary with declared effects and runtime state, not
because return values are transported through publication or
terminal-finalization machinery.

Any proposed `record-drain-outcome`-style helper must first answer which
consumer it serves:

- parent workflow: use the returned typed value directly;
- public report or dashboard: use publication policy;
- legacy YAML-era reader: use bridge metadata with owner, schema, consumer, and
  retirement condition;
- durable domain/resource state: use a typed resource transition; or
- resume: use runtime-owned checkpoint state, not authored drain bookkeeping.

If no consumer fits one of those cases, the helper is migration debt and must
not be required for `DrainResult<TSummary>` return.

#### 9.1.1 Parent Terminal Reprojection Over Imported `backlog-drain`

For families whose public or parity-constrained terminal boundary still differs
from stdlib `DrainResult`, the shared parent-loop lane must also support one
accepted terminal reprojection route. When the family/public boundary also
omits or renames a child terminal field that exists on the imported stdlib
result, Section 9.1.1.1 is a separate narrower prerequisite inside this lane.
The minimum contract is:

- a parent workflow may place imported `backlog-drain` either as the terminal
  workflow body expression or as the input to one ordinary typed terminal
  projection step that remains on the supported WCC/schema-2 route;
- that projection may inspect the returned stdlib union through ordinary
  refined `match` and construct the family/public terminal union without
  reintroducing a handwritten select/run/gap loop, handwritten terminal fan-in,
  or compatibility-script routing;
- source maps and variant provenance remain attached to both the imported
  `backlog-drain` result and the projected terminal result; and
- the accepted route does not depend on nesting imported `backlog-drain`
  inside unsupported local-control positions whose only purpose is terminal
  post-projection.

The minimum behavior check for this contract is a compile/shared-validation
fixture that exercises this exact shape:

- imported `backlog-drain` on the parent route;
- ordinary typed terminal reprojection to a family/public union or boundary
  publication policy;
- no handwritten parent loop or handwritten drain-terminal compatibility path;
  and
- preserved source-map provenance for the projected terminal result.

Until that route works, a family may still adopt request-record, projection,
transition, and publication slices, but it must not claim full
imported `backlog-drain` adoption when the only remaining route depends on
unsupported local-control nesting or a restored handwritten terminal fan-in.

##### 9.1.1.1 Branch-Local Terminal Contract Alignment

For families whose public or parity-constrained terminal boundary omits,
renames, or otherwise does not preserve every imported stdlib terminal field
verbatim, the shared parent/drain owner lane must also support one accepted
branch-local contract-alignment route before the broader parent terminal
reprojection claim counts as satisfied.

The minimum contract is:

- a parent workflow may `match` the imported stdlib `DrainResult`, consume a
  branch-local child field such as `blocker-class`, carried typed data, or a
  stdlib-only classification payload, and then construct the family/public
  terminal result without re-exporting that field verbatim;
- the family/public terminal union does not need to mirror every stdlib child
  field name or carry every child-only field as a public output, provided the
  projection uses those fields through ordinary typed/proved bindings while the
  imported variant scope is still active;
- source maps, `requires_variant` provenance, and executable contract lineage
  remain attached from the imported stdlib result
  through that branch-local field consumption and into the projected terminal
  value or boundary publication; and
- the accepted route does not depend on widening the family/public boundary
  solely to echo stdlib child fields, on same-file-only terminal
  normalization, on family-local wrapper workflows, on handwritten
  drain-terminal fan-in, or on compatibility-bundle rereads to recover a
  dropped field.

The minimum behavior check for this contract is:

- one compile/shared-validation fixture where imported `backlog-drain` reaches
  a nontrivial terminal variant whose payload includes at least one field not
  preserved verbatim by the family/public boundary;
- one ordinary typed `match` route where the parent consumes that field and
  produces the family/public terminal union or publication policy result
  without adding the child field to the public boundary just for transport; and
- preserved source-map provenance for both the imported child result and the
  projected parent terminal value.

Until that route works, a family may not treat a simpler terminal
reprojection fixture as sufficient when its actual public/parity boundary still
depends on consuming a stdlib child field that is omitted or renamed at the
family boundary.

#### 9.1.2 Gap-Drafter Callable-Boundary Over Imported `backlog-drain`

For families whose imported `backlog-drain` route can reach the selector
`GAP` branch, the shared parent/drain owner lane must also support one accepted
callable-boundary route for the fixed `gap-drafter` workflow-ref surface. The
minimum contract is:

- imported `backlog-drain` keeps the `gap-drafter` boundary fixed to
  `DrainCtx` plus the stdlib selector gap payload;
- a family must not satisfy that boundary by widening the imported
  `gap-drafter` arity, by flattening the typed gap payload into public or
  path-heavy parameters, or by reopening handwritten parent routing around the
  gap lane;
- when selector output or loop-frame state carries a typed gap payload, the
  `gap-drafter` child call may bind that payload through the ordinary
  WCC/schema-2 callable-boundary route using workflow inputs or prior outputs
  from the imported route, rather than requiring family-local rereads or
  compatibility bundles to reconstruct the payload;
- selector and `gap-drafter` failures diagnose the authored call boundary rather
  than a generated branch name; and
- the accepted route does not depend on family-local wrapper or projector
  workflows whose only purpose is to smuggle selector-produced gap fields
  across the fixed `gap-drafter` boundary, nor on fabricated placeholder
  carriers.

The minimum behavior check for this contract is a compile/shared-validation
fixture that exercises this exact shape:

- imported `backlog-drain` on the parent route;
- selector `GAP` output with a typed gap payload whose carried fields flow from
  selector output or loop-frame outputs on the imported route;
- a `gap-drafter` child workflow call through the fixed stdlib signature;
- no widened `gap-drafter` arity, public path threading,
  compatibility-bundle reread, or placeholder-carrier fabrication; and
- diagnostics identify selector and `gap-drafter` child-call failures at the
  authored call boundary.

Until that route works, a family may still adopt request-record, transition,
publication, and other parent/work-item cleanup slices that do not
depend on reachable imported-gap execution, but it must not claim full
imported `backlog-drain` adoption when the reachable `GAP` lane still depends
on family-local payload-smuggling wrappers or reopened call boundaries.

##### 9.1.2.1 Generic Gap-Payload Leaf Carriage

For families whose reachable selector `GAP` payload is a typed record with
multiple semantic fields, the shared callable-boundary prerequisite in Section
9.1.2 also requires one narrower behavior check: imported
`backlog-drain` must carry that record across the fixed `gap-drafter`
boundary by the declared record-leaf shape, not by a one-field surrogate.

The minimum contract is:

- child-call binding derives every declared leaf of the selector `GAP` record
  from selector outputs or loop-frame outputs on the imported route;
- the shared lowering preserves the authored record shape rather than
  substituting a special one-field protocol such as `gap-id`;
- the fixed `gap-drafter` boundary remains exactly `DrainCtx` plus one record
  payload parameter, and richer payloads are expressed only by the fields of
  that record, not by widened arity or family-local recomposition; and
- the accepted route uses the same generic record-leaf call-binding model
  expected of other typed workflow-call boundaries, so later families can rely
  on shared lowering rather than local wrapper transport.

The minimum behavior check for this narrower contract is:

- one compile/shared-validation fixture whose selector `GAP` variant carries a
  record payload with more than one semantic field;
- positive assertions that the imported `gap-drafter` child call binds each
  leaf from prior outputs on the imported route rather than from family-local
  wrapper projection; and
- one negative check that a non-record `gap-drafter` payload still fails the
  fixed callable-boundary contract.

Until that route works, a family may not treat one-field `gap-id` carriage as
showing that the reachable imported `GAP` lane is ready for richer typed gap
payloads.

#### 9.1.3 Family Gap Re-Entry Convergence Over Imported `backlog-drain`

For families whose real imported `backlog-drain` route can return `GAP` and
whose `gap-drafter` may return `CONTINUE`, there is a separate family-owned
prerequisite after the shared callable-boundary and payload-carriage checks:
the next selector pass must observe typed progress from the completed gap work
rather than reselecting the same gap until authored exhaustion.

The minimum contract is:

- a valid gap draft or validation pass records selector-visible typed progress
  before returning `GapResult.CONTINUE`;
- the next selector pass reads that progress through inputs it already
  consumes, such as typed run-state or progress-ledger state, rather than
  through hidden in-memory flags, forced fake-provider tuple sequencing,
  reread reports, or pointer files;
- authored `max_iterations_exhausted` remains the terminal result when the
  selector truly keeps returning non-terminal work without new progress
  state; and
- the accepted route does not change shared `std/drain` parent-loop semantics,
  widen `gap-drafter` arity, or reopen handwritten parent routing.

The minimum behavior check for this contract is:

- one real-route smoke or fixture where the selector returns `GAP`, the
  `gap-drafter` returns `CONTINUE` after recording typed progress, and the
  next selector pass reaches the family's intended terminal route because of
  that recorded progress;
- one negative or exhaustion check where absent progress still yields
  `max_iterations_exhausted`; and
- preserved source-map provenance for the recorded progress state.

For the Design Delta reference family, this prerequisite is separate from the
shared `gap-drafter` callable-boundary check: fixed `DrainCtx + gap payload`
transport may already be green while the real `DRAFT_DESIGN_GAP` lane still
needs a family-owned progress transition so selector re-entry converges.

Until that route works, a family may still adopt request-record, transition,
publication, and shared gap-transport cleanup slices, but it must not claim
imported `backlog-drain` adoption on reachable gap routes that still exhaust
on unchanged selector inputs after a valid gap draft.

### 9.2 Shared Phase-Family Boundary Prerequisite

For any parent-callable family that intends to simplify ordinary work-item
authoring to an `item-ctx` plus typed-selection surface while still reusing
existing child phase workflows, the shared post-foundation phase-family
boundary lane must already support hidden private-context transport and
matched-union validation on the WCC route. The minimum contract is:

- internal reusable-call binding supplies phase/item context without exposing
  synthetic `PhaseCtx`, state roots, generated write roots, or checkpoint
  paths as public authored inputs;
- a high-level work-item workflow may `match` imported child-workflow union
  results and project them into family or stdlib terminal unions without
  `workflow_boundary_type_invalid` or lost `requires_variant` provenance;
- any generated helper/private workflow boundaries preserve producing-step
  identity, source maps, and private/compatibility boundary labeling needed by
  shared validation; and
- the route does not regain path-heavy `phase-ctx`-first signatures, bundle
  rereads, or family-local wrapper shapes whose only purpose is to bypass
  missing refinement/context transport.

This prerequisite decomposes into three shared capability contracts that must be
checked together for families adopting imported `backlog-drain` plus reused child
phase workflows:

#### 9.2.1 Fixed `run-item` Workflow-Ref Shape

The imported `std/drain/backlog-drain` owner lane keeps the `run-item`
workflow-reference boundary fixed to the stdlib selected-item call shape:

- `ItemCtx`; and
- the stdlib selection payload.

If a family still needs additional authored domain inputs to reuse existing
child phase workflows, those inputs must reach the child workflows through one
of these shared routes:

- a typed selection/bootstrap payload already carried through that fixed
  `run-item` boundary; or
- hidden private reusable-call/context binding derived from `ItemCtx`,
  `RunCtx`, or other accepted runtime-owned anchors.

The family must not satisfy this prerequisite by widening the imported
`run-item` workflow-ref arity, by reintroducing public path-threading
parameters, or by adding family-local wrappers whose only purpose is to smuggle
extra authored inputs around the fixed stdlib call shape.

#### 9.2.2 Generic Child-Phase Reuse For Item-Context-First Families

The shared phase-family route must support child-phase reuse for general
item-context-first workflow families, not only for one dedicated fixture
or caller-specific allowlist. The minimum behavior check for this contract shows
that:

- a work-item workflow entered through the fixed `run-item` stdlib shape may
  derive or reuse child phase workflows without exposing new public `PhaseCtx`
  or state-root inputs;
- family-authored typed domain inputs needed by those child phase workflows
  remain available through the accepted typed payload or hidden private-binding
  route rather than through reopened path-heavy signatures;
- matched child-workflow unions still preserve `requires_variant` provenance,
  source maps, and shared-validation boundary labeling on the WCC route; and
- the generalized route is owned by shared compiler/runtime contracts rather
  than by a family-specific caller name or one-off Design Delta branch.

Until that shared contract exists, a family may still adopt request-record,
projection, transition, publication, and shared parent-loop cleanup
slices, but it must not claim the simplified internal-signature plus
imported-child stdlib route for ordinary work-item composition.

#### 9.2.3 Called-Workflow Result Branching And Terminal Reprojection

The shared phase-family route must also support the ordinary work-item branch
shape that imported `backlog-drain` families actually need after the fixed
`run-item` entrypoint is in place. The minimum contract is:

- the authored surface is ordinary refined pattern matching: inside
  `((BLOCKED blocked) ...)`, `blocked` has the `BLOCKED` payload type;
- a work-item workflow may call an imported child phase workflow, bind the
  returned union result, and immediately `match` that binding on the ordinary
  WCC/schema-2 route;
- inside a proved branch of that child-workflow result, the workflow may call a
  family or stdlib helper that returns a second union-like terminal or
  classification result and may `match` that second result without losing the
  producing-step identity needed by `requires_variant`;
- nested finalizers such as imported `std/resource/finalize-selected-item`, or
  equivalent typed family terminal reprojection, may appear under those proved
  branches without triggering `workflow_boundary_type_invalid` because the
  compiler retargeted refinement at a non-variant wrapper step; and
- the accepted route remains the shared compiler/runtime path rather than a
  family-local decomposition into path-heavy wrapper workflows, re-read
  compatibility bundles, or caller-name-specific validator exemptions.

The minimum behavior check for this contract is a compile/shared-validation
fixture that exercises this exact shape:

- fixed `run-item` stdlib entry;
- imported child phase call returning a union;
- `match` over that call result;
- branch-local call to a terminal-classification or recovery helper returning a
  second union; and
- branch-local call to imported `finalize-selected-item` or an equivalent typed
  terminal projection.

Until that route works, a family may still adopt the parent-loop, request-
record, projection, transition, and publication slices that do not
depend on this branching shape, but it must not claim completion of the
simplified item-context-first child-phase reuse route.

Feasibility: this does not require a new language feature beyond the accepted
WCC route. Surface `match` already elaborates to WCC `case`, `case` opens the
variant/refinement scope, and join parameters are the normal way for branch
results to leave that scope. The implementation work is to make the existing
refined match-binder model complete for called-workflow results, nested
finalizers, and terminal reprojection, with source maps and shared-validation
refinement metadata generated from those lexical bindings. A fix that exposes
refinement tokens as authored values, adds caller-name-specific refinement
allowlists, or
requires branch-local bundle rereads is a compatibility workaround, not the
target shape.

#### 9.2.4 No Internal Compatibility-Carrier Lane

The final target has no hidden compatibility-carrier abstraction for ordinary
internal `.orc` composition. If a route still needs `run_state_path`, a
relpath, a summary path, or another compatibility value to cross a stdlib
child-call boundary, that is migration debt, not target completion.

The only accepted outcomes are:

- remove the carrier by passing typed values and using runtime-owned
  checkpoint/resource state;
- stop the current slice and select the prerequisite that removes the carrier.

A gap must not make progress claims by threading the carrier through more
domain payloads, widening workflow-ref signatures, adding family-local wrapper
workflows, or other changes whose only purpose is to keep the carrier alive.

#### 9.2.5 Work-Item Summary Ownership Over Imported `finalize-selected-item`

For families whose selected-item route still produces ordinary terminal or
blocked-recovery summary files inside the work-item body, imported
`finalize-selected-item` adoption requires one additional family-owned
prerequisite: summary files must stop being a hidden precondition for terminal
typed return.

The minimum contract is:

- imported `finalize-selected-item` may consume typed summary values, but it
  must not require body-owned summary materialization in order to return the
  typed `SelectedItemResult`;
- the accepted route does not keep `record-work-item-terminal-outcome`,
  `record-work-item-blocked-recovery-summary`, or equivalent family-local
  summary writers as the mechanism that allows imported
  `finalize-selected-item` to complete.

The minimum behavior check for this contract is:

- one compile/shared-validation or runtime smoke fixture where imported
  `finalize-selected-item` returns the typed work-item terminal result without
  relying on body-owned summary materialization;
- one negative check that interior field-level publication or
  rendered-summary-as-authority still fails the promoted route.

For this target, a failing smoke or regression that expects an interior
`item_summary.json` file on completed, exhausted, or blocked-recovery work-item
routes is stale compatibility coverage. The correct repair is to update that
expectation to typed terminal return plus declared boundary publication or
legacy bridge, not to restore body-owned `item_summary.json` materialization.

For the Design Delta reference family, this prerequisite stays separate from
the broader stdlib-adoption rewrite: the route may clear called-workflow
branching and imported finalizer placement while still being blocked if the
unblocked selected-item path only completes through interior summary
materialization.

Until that route works, a family may still adopt parent-loop, request-record,
and transition cleanup slices, but it must not claim imported
`finalize-selected-item` adoption on routes where ordinary work-item summary
durability still lives in the work-item body.

### 9.3 Shared `std/phase` Owner-Lane Self-Hosting Prerequisite

For any parent-callable family that reuses child phase workflows through the
imported `std/phase` lane, the shared stdlib owner lane must already support
ordinary `std/phase` compile and validation as an imported module on the same
WCC/schema-2 route the family is using. This is a separate prerequisite from
the family-specific `item-ctx` and `backlog-drain` wiring above.

The minimum contract is:

- `std/phase` resolves and exports its own authored review/fix types and
  helpers, including `ReviewDecision`, `ReviewFindings`, and
  `ReviewLoopResult`, without family-local aliases, copied type declarations,
  or compiler-name special cases;
- `review-revise-loop`, `phase-scope`, and any helper procedures they depend on
  compile through the ordinary imported-stdlib route with the same type
  environment and source-map visibility expected of other builtin stdlib
  modules;
- owner-lane behavior checks include at least one compile/shared-validation fixture that
  fails closed on missing local type resolution or builtin-module self-reference
  drift, rather than relying only on downstream family workflows to discover the
  failure; and
- a family does not satisfy this prerequisite by forking `std/phase`,
  restating the missing types in family modules, or broadening its own design
  scope to patch shared stdlib/compiler semantics under a family migration gap.

Until that shared contract exists, a family may still adopt request-record,
projection, transition, publication, parent-loop, and phase-boundary
cleanup slices that do not depend on the broken `std/phase` owner lane, but it
must not claim completion of the imported child-phase/stdlib route.

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

## 11. Implementation Boundaries

Implementation follows this design only if the default `.orc` authoring and
lowering path provides the behavior. The following do not satisfy the target:

- a test-only fixture that bypasses provider prompt composition;
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
not an isolated teaching fixture.

## 12. Compatibility And Migration

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

## 13. Verification Strategy

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

Acceptance is based on the authored surface and executable behavior.
Diagnostic summaries, inventories, manifests, reports, and evidence refreshes
are non-goals unless they are generated as a direct consequence of changing the
executable contract.

### 13.4 Design Delta Drain Acceptance

Full reference-family acceptance is demonstrated by the real promoted route:

- provider calls use typed request records or small typed values, with write
  targets classified separately from prompt-subject data;
- public boundaries reject runtime context, generated roots, checkpoint paths,
  and generated output targets;
- imported stdlib child workflows return typed values that parents can bind,
  match, and project without family-local loop or finalization rewrites;
- reachable gap, selected-item, blocked, exhausted, and terminal paths converge
  through ordinary typed composition;
- deterministic reshaping uses typed projection where the closed expression
  surface is sufficient;
- durable state changes are named domain operations lowering to typed
  transitions or certified transition adapters;
- ordinary terminal summaries are boundary publications, not body-owned
  prerequisites for typed return;
- compatibility carriers are absent from ordinary internal composition, or are
  isolated at declared public/legacy boundaries while a live consumer remains;
  and
- the Design Delta family route compiles, validates, and dry-runs or smoke-runs
  as a parent-callable workflow.

Use the narrowest runnable checks that exercise the changed behavior. Do not
select work whose primary effect is refreshing census, manifest, report, or
diagnostic artifacts.

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
  input is nontrivial;
- hides runtime context and generated paths from public authored inputs;
- keeps private context parameters limited to internal definitions;
- uses typed projection instead of Python for deterministic local reshaping
  where the closed expression surface is sufficient;
- represents durable drain/work-item/recovery state changes as named domain
  operations that lower to typed transitions or certified transition adapters;
- contains no body-level `materialize-view` except justified timed
  publications or low-level compatibility fixtures;
- keeps remaining Python helpers only as certified external or legacy adapters;
- retires transitional compatibility surfaces from ordinary internal
  composition;
- represents phase, item, drain, selection, and recovery behavior through
  library/domain records and imported stdlib/family modules over the generic
  resource/context core, not through family-specific compiler branches;
- produces the same public terminal outputs expected by the selected parity
  target; and
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
  are typed projections or certified adapters;
- drain/work-item/recovery state changes are named domain operations that lower
  to typed transitions or certified transition adapters;
- public summaries and legacy bundles are produced by publication policy or
  bridge metadata; and
- the run produces parity-comparable terminal state and artifacts without
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
- emulating missing shared `backlog-drain` parent-loop behavior in family-local
  adapters instead of proving the owner-lane contract;
- working around missing shared callable-child value-return support by
  restoring direct `EmitDrain*`-style terminal normalization, family-local
  finalizer wrappers, same-file-only terminal special cases, or ad hoc
  exhaustion overrides, or by making side effects prerequisites for simple
  `DrainResult<TSummary>` return instead of landing the separate prerequisite
  gap in Section 9.1.0;
- working around missing shared `gap-drafter` callable-boundary support by
  widening the imported `gap-drafter` workflow-ref shape, flattening typed gap
  payloads into public or path-heavy parameters, rereading compatibility
  bundles to reconstruct the payload, or inserting family-local wrapper or
  projector workflows whose only purpose is to smuggle selector-produced gap
  fields across the fixed boundary instead of landing the separate
  prerequisite gap;
- treating a one-field shared gap payload such as `gap-id` as
  sufficient for richer typed selector `GAP` records instead of landing the
  narrower generic record-leaf prerequisite in Section 9.1.2.1;
- working around missing family gap re-entry convergence by forcing selector
  `DONE`, relying on fake-provider tuple sequencing, hidden in-memory flags,
  report rereads, or family-local loop bypasses instead of landing the
  separate prerequisite gap in Section 9.1.3;
- working around missing shared parent terminal reprojection support by nesting
  imported `backlog-drain` under family-local post-projection control wrappers
  or by restoring handwritten drain-terminal fan-in instead of landing the
  separate prerequisite gap;
- working around missing shared branch-local terminal contract alignment by
  widening the family/public terminal union just to mirror stdlib child fields
  such as `blocker-class`, or by adding same-file-only reprojection hooks,
  wrapper workflows, or compatibility-bundle rereads whose only purpose is to
  preserve those fields across the parent boundary instead of landing the
  separate prerequisite gap;
- widening the imported `backlog-drain` `run-item` workflow-ref shape or
  depending on fixture-specific child-phase caller allowlists instead of
  landing the shared phase-family prerequisite;
- working around an internal compatibility carrier by surfacing it as a public
  or ordinary authored parameter, treating it as private runtime context,
  or inserting family-local wrapper workflows instead of removing it;
- working around missing work-item summary ownership over imported
  `finalize-selected-item` by keeping body-level summary writers or
  `materialize-view` calls as prerequisites for terminal return, or by
  treating rendered summary paths as semantic authority, instead of landing
  the separate prerequisite gap in Section 9.2.5 and deleting the summary lane
  unless a named public or legacy consumer still requires it;
- working around missing called-workflow result branching support by splitting
  ordinary work-item routing into family-local wrapper workflows, compatibility
  bundle rereads, or other refinement-preserving facsimiles instead of landing the
  shared prerequisite in Section 9.2.3;
- keeping Design Delta-specific bridge augmentation in core compiler modules;
- patching a missing shared `std/phase` type/export/import-resolution contract
  inside a family migration slice instead of landing a separate owner-lane
  prerequisite gap first;
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
2. introduce typed request records and compile fixtures;
3. add or finish lowering for implicit provider-input rendering and boundary
   publication;
4. convert deterministic helpers to typed projections;
5. convert state updates to typed transitions or certified adapters;
6. simplify the `.orc` source;
7. run compile, shared validation, and focused dry-run/smoke checks for the
   changed behavior; and
8. remove obsolete follow-up text after the working reference family supports the
   behavior.
