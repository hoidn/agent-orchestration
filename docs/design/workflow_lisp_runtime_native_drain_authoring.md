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
  owns the private-checkpoint and consumer-rendering substrate.
- `docs/design/workflow_lisp_generic_resource_context_core.md` owns the
  simplified generic resource/context model.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  owns parent-callable workflow-family migration and promotion evidence.
- `docs/design/workflow_command_adapter_contract.md` owns certified adapter
  boundaries.
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
  -> parity-comparable typed terminal result plus boundary views
```

The user-facing `.orc` should look like domain workflow code:

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
source maps, Semantic IR, and build evidence, but not as public authored
workflow inputs.

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
resume, parity evidence, and authoring guidance.

## 4. Goals

- Make typed domain values the normal carrier between Workflow Lisp
  procedures.
- Let provider calls accept typed prompt-input records or values instead of
  long positional lists of files and scalar fields.
- Keep private runtime context, generated paths, checkpoint identity, and
  write roots out of public authored boundaries and ordinary user-facing call
  signatures.
- Render typed values at consumer seams: provider prompt injection, public
  workflow publication, observability, or compatibility bridges.
- Reserve body-level `materialize-view` for justified timed publications and
  low-level compatibility work.
- Replace deterministic Python helpers with pure typed projections where the
  operation is local, typed, and side-effect free.
- Represent durable state/resource mutation as typed resource transitions or
  certified transition adapters.
- Preserve provider/command structured-output authority through runtime-bound
  validated bundles.
- Keep remaining external Python/shell at certified adapter boundaries with
  typed inputs, typed outputs, effect declarations, fixtures, source maps, and
  retirement metadata.
- Produce a working Design Delta Drain `.orc` family that compiles, validates,
  runs with fake-provider or controlled smoke evidence, and passes migration
  parity expectations for the selected acceptance scope.

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

Preferred shape:

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

That operation lowers to a declared transition contract. The current accepted
substrate shape is:

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

### 7.6 Compatibility Bridges

Legacy files should be driven by bridge metadata:

Illustrative metadata shape:

```lisp
(:bridge
  ((legacy-selection-bundle
     :from selection
     :renderer canonical-json
     :schema design-delta-selection-bundle.v1
     :retire-after design-delta-yaml-primary-retired)))
```

Deleting or expiring the bridge metadata retires the file. The workflow body
does not hand-author path construction for the bridge. Until a concrete `.orc`
bridge declaration surface is accepted, equivalent manifest or boundary metadata
is acceptable if it records the typed source value, renderer, schema/version,
consumer, owner, and retirement condition.

## 8. Contracts And Interfaces

### 8.1 Frontend

The Workflow Lisp frontend must:

- typecheck provider `:inputs` values as typed prompt subjects;
- support typed prompt-input records without forcing materialized prompt files;
- infer consumer-slot rendering where a unique renderer and authority class
  exists;
- lower publication policy and bridge metadata to materialized-view kernel
  operations;
- keep private context bindings out of public authored boundaries;
- emit source maps and Semantic IR entries for inferred context, projection,
  rendering, bridge, and transition effects; and
- reject ambiguous renderer selection or unclassified path plumbing with
  actionable diagnostics.

### 8.2 Runtime

The runtime must:

- preserve provider and command structured-output authority;
- provide private execution context needed for generated paths and resume;
- render typed prompt inputs at provider prompt composition;
- execute or delegate typed resource transitions with version, idempotency,
  conflict, and audit semantics;
- materialize boundary publications and bridges from typed values; and
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

The parity layer must compare typed terminal results, public outputs,
artifacts, resource-transition evidence, resume/reuse behavior, and accepted
compatibility bridges. It must not treat successful compile, dry-run, or a
rendered summary as primary-surface promotion.

## 9. Dependencies And Sequencing

This target consumes the existing WCC route and post-foundation composition
work. Implementation should proceed in this order:

1. classify path-like and render-like fields in the Design Delta `.orc` family
   as public authored input, private runtime context, generated internal,
   materialized view, public publication, or compatibility bridge;
2. introduce typed prompt-input request records for provider calls;
3. replace deterministic helper scripts with pure typed projections where the
   closed expression surface is sufficient;
4. move ordinary terminal summaries and reports to boundary publication policy;
5. move legacy bundle and pointer files to bridge metadata;
6. hide runtime context and generated targets behind private bindings;
7. convert durable state updates to typed transitions or certified transition
   adapters;
8. keep external tools and remaining legacy protocol work behind certified
   adapters; and
9. prove the Design Delta Drain `.orc` family works as one parent-callable
   workflow family under the acceptance criteria below.

Work that can proceed independently:

- provider request-record refactors;
- projection replacement for local deterministic reshaping;
- bridge metadata for existing compatibility files; and
- lint/reporting for explicit body renderings.

Work that should wait for substrate evidence:

- removal of compatibility bridges required by YAML parity;
- defaulting all boundary publications to implicit rendering; and
- deleting certified adapters whose runtime-native replacement has not passed
  positive and negative fixtures.

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
- A compatibility bridge without owner, source typed value, renderer, schema,
  and retirement metadata is invalid for new high-level `.orc`.
- A deterministic projection implemented by Python remains migration debt
  unless certified and justified.
- A resource transition must fail closed on version mismatch, undeclared
  writes, missing audit evidence, or idempotency conflict.

## 11. Evidence And Implementation Boundaries

Implementation follows this design only if the default `.orc` authoring and
lowering path provides the behavior. The following are not sufficient evidence:

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

## 13. Verification Strategy

### 13.1 Static And Compile-Time Checks

- Compile typed provider request-record examples.
- Compile provider `:inputs request` where `request` is a typed record.
- Reject ambiguous renderer defaults for provider inputs.
- Reject public `RunCtx`, generated write-root, checkpoint path, or
  generated-internal output target at a promoted boundary.
- Reject unexplained body-level `materialize-view` outside timed publication
  or compatibility bridge surfaces.
- Verify source maps and Semantic IR record inferred rendering and private
  context bindings.

### 13.2 Runtime Checks

- Provider prompt composition renders typed request records with provenance
  evidence.
- Provider output remains the declared structured bundle, not prompt evidence.
- Boundary publication materializes terminal summaries from typed terminal
  results.
- Compatibility bridge files are generated from bridge metadata and typed
  values.
- Resource transitions validate versions, idempotency keys, write sets, and
  audit projections.
- Resume does not require public authored checkpoint or generated path inputs.

### 13.3 Design Delta Drain Acceptance

Before full reference-family acceptance, implementation must pass a staged proof
ladder:

- typed provider request-record fixture with prompt rendering evidence;
- provider write-target fixture proving targets are role-classified separately
  from prompt-subject data;
- boundary `:publish` fixture proving terminal publication lowers to
  materialized-view kernel operations;
- bridge metadata fixture, or manifest-backed equivalent, proving compatibility
  files are generated from typed source values;
- named domain-transition fixture proving a helper such as
  `complete-work-item` lowers to a declared `resource-transition` contract;
- public/private boundary fixture proving `RunCtx`, generated write roots,
  checkpoint paths, and generated targets stay off public authored inputs; and
- parent-callable smoke or dry-run fixture for the Design Delta family route.

The target is complete only when the Design Delta Drain `.orc` family:

- compiles through the WCC route;
- passes shared validation;
- can be dry-run or smoke-run as a parent-callable workflow family;
- uses typed provider request records for plan, implementation, selector,
  architect, review, fix, and recovery-classifier provider calls where the
  input is nontrivial;
- hides runtime context and generated paths from public authored inputs;
- uses typed projection instead of Python for deterministic local reshaping
  where the closed expression surface is sufficient;
- represents durable drain/work-item/recovery state changes as typed
  transitions or certified transition adapters;
- uses boundary publication or bridge metadata for ordinary summaries,
  reports, selection bundles, and compatibility files;
- contains no body-level `materialize-view` except justified timed
  publications or low-level compatibility fixtures;
- keeps remaining Python helpers only as certified adapters with fixtures and
  source-map/effect evidence;
- produces the same public terminal outputs expected by the selected parity
  target; and
- records migration evidence that distinguishes working parent-callable `.orc`
  execution from YAML-primary promotion.

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
- the run produces parity-comparable terminal state and artifacts.

Forbidden result:

- the `.orc` source succeeds only by passing many raw paths through provider
  inputs and call signatures;
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
- the common drain body uses named domain operations rather than exposing
  routine runtime bookkeeping;
- typed provider request records replace long positional provider input lists
  in the reference family;
- provider write targets are separated from semantic prompt-subject records;
- private runtime context and generated paths are hidden from public authored
  boundaries;
- consumer-side rendering handles prompt inputs, ordinary public summaries,
  observability views, and compatibility bridges;
- deterministic projection no longer requires Python where the closed
  expression surface is sufficient;
- durable state/resource updates are typed transitions or certified transition
  adapters;
- remaining Python helpers are certified external/legacy boundaries, not
  hidden semantic glue;
- source maps, Semantic IR, build reports, and migration evidence expose the
  generated private context, projection, rendering, bridge, and transition
  effects; and
- migration parity can evaluate the `.orc` family without treating rendered
  files or reports as semantic authority. YAML-primary replacement remains owned
  by the separate migration parity and promotion gates.

## 16. Stop Or Revise Criteria

Revise this target if implementation requires:

- exposing private runtime context in public `.orc` syntax;
- adding broad arbitrary file IO or general scripting primitives to Workflow
  Lisp;
- treating rendered files as semantic authority;
- weakening provider/command structured-output validation;
- hiding resource mutation in uncertified adapters;
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

1. census `.orc` path, context, rendering, projection, adapter, and
   transition surfaces;
2. introduce typed request records and compile fixtures;
3. add or finish lowering for implicit provider-input rendering and boundary
   publication;
4. convert deterministic helpers to typed projections;
5. convert state updates to typed transitions or certified adapters;
6. move compatibility files to bridge metadata;
7. simplify the `.orc` source;
8. run compile, shared validation, dry-run/smoke, and parity evidence; and
9. update authoring docs and migration evidence once the working reference
   family proves the target.
