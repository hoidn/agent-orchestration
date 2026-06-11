# Workflow Lisp Generic Resource And Context Core

Status: draft design
Kind: architecture decision / simplification target
Created: 2026-06-09
Scope: Workflow Lisp private context, resource state, typed transitions, and
the runtime/library boundary for post-foundation composition work.

Authority:

- Normative runtime and DSL behavior remains in `specs/`.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  owns the broader post-foundation migration sequence.
- `docs/design/workflow_lisp_state_layout.md` owns generated path and state
  layout principles.
- `docs/design/workflow_command_adapter_contract.md` owns adapter
  certification and hidden glue policy.
- This document narrows the post-foundation context/resource target. It does
  not by itself add runtime primitives or promote any `.orc` workflow.

Related docs:

- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/state.md`
- `specs/dsl.md`

## 1. Purpose

The post-foundation design identifies private executable context and
resource-transition ownership as blockers for parent-callable Workflow Lisp
migration. Its examples name several context families, including `RunCtx`,
`PhaseCtx`, `ItemCtx`, `DrainCtx`, `SelectionCtx`, and `RecoveryCtx`.

Those names are useful for describing the Design Delta Drain domain, but they
should not all become privileged runtime scope kinds.

This document defines the simpler core: the runtime should own generic durable
context, resource identity, transition, version, conflict, resume, path-safety,
and provenance mechanics. Workflow Lisp libraries should define domain records
such as phases, items, drains, selections, and recoveries on top of that core.

## 2. Executive Decision

Move the post-foundation private-context/resource target toward a three-part
generic core:

```text
RunCtx
Resource<TState>
Transition<TRequest, TResult>
```

The runtime should not hard-code `PhaseCtx`, `ItemCtx`, `DrainCtx`,
`SelectionCtx`, or `RecoveryCtx` as first-class scope categories. Those are
Workflow Lisp library/domain records backed by generic resources,
transitions, and `StateLayout` allocation metadata.

The design principle is:

```text
Bake invariants into the runtime.
Keep workflow-domain state in Workflow Lisp libraries.
```

Runtime invariants worth baking in:

- run identity;
- resource identity and version;
- transition preconditions;
- atomic commit or fail-closed behavior;
- idempotency and retry rules;
- conflict detection;
- resume identity;
- public/private boundary separation;
- path allocation and path safety;
- source-map and Semantic IR provenance; and
- audit evidence.

Domain concepts not worth baking in as runtime primitives:

- phase;
- item;
- drain;
- selection;
- recovery;
- plan;
- implementation; and
- review.

Those concepts may still appear as typed records, unions, stdlib helpers, and
workflow-family modules.

## 3. Problem

The Design Delta Drain migration exposed a real need for first-class
state/resource modeling. Parent-callable `.orc` workflows must not expose raw
`state/` paths, generated write roots, queue files, or recovery ledgers as
ordinary public inputs. They also must not hide state mutation in Python
helpers.

The immediate temptation is to promote every observed domain concept into a
runtime scope:

```text
RunCtx
PhaseCtx
ItemCtx
DrainCtx
SelectionCtx
RecoveryCtx
```

That overfits the runtime to one workflow family. Other families may use
experiments, trials, samples, jobs, batches, candidates, reviews, or releases.
If each domain noun requires a runtime scope, the runtime becomes a taxonomy
of application concepts instead of a workflow execution substrate.

The runtime needs fewer concepts with stronger invariants.

## 4. Authority And Dependency Direction

### 4.1 Desired Direction

```text
Workflow Lisp domain library
  -> typed domain records/unions
  -> generic Resource<TState> references
  -> generic Transition<TRequest, TResult> calls
  -> runtime validation, versioning, commit, resume, audit
  -> StateLayout allocation/provenance
```

### 4.2 Prohibited Direction

```text
Design Delta Drain noun
  -> new runtime context primitive
  -> specialized path/state behavior
  -> more parent workflow domains need more runtime primitives
```

### 4.3 Boundary

The runtime owns durable mechanics. The `.orc` library owns domain modeling.

Examples:

| Domain need | Runtime core | Library/domain layer |
| --- | --- | --- |
| A drain has iterations | versioned resource plus transition history | `DrainState`, `DrainIteration`, `DrainTerminalResult` |
| An item moves from active to done | transition preconditions and commit | `BacklogItemState`, `CompleteItemRequest` |
| A phase needs private paths | `RunCtx` plus `StateLayout` allocation | `PhaseCtx` record with allocated roots/views |
| Recovery retries a blocked item | resource identity, conflict, resume | `RecoveryCtx`, `RecoveryDecision`, `RecoveredGapAttempt` |
| Selection emits a bundle view | projection/materialized view mechanics | `SelectionResult`, `SelectionBundleView` |

## 5. Core Model

### 5.1 `RunCtx`

`RunCtx` is the only always-present private execution context. It represents
runtime execution identity and allocation authority.

It should include or derive:

- run id;
- run root;
- artifact root;
- state root;
- temp root;
- runtime identity;
- current resume namespace;
- current source-map/provenance namespace; and
- a handle to `StateLayout` allocation.

`RunCtx` is private executable context. It may appear in executable/runtime
contracts, source maps, and Semantic IR. It must not become an authored public
input for promoted `.orc` workflows.

### 5.2 `Resource<TState>`

A resource is durable workflow-managed state with identity, version, and typed
state. It may be backed by files, a ledger, a database, object storage, or an
adapter during migration. File layout is an implementation detail behind the
resource contract.

Minimal resource shape:

```text
Resource<TState> {
  resource_id
  resource_kind
  state_type
  version
  state_ref
  provenance
}
```

The runtime must not need to know whether the resource is a backlog item, a
phase, a queue entry, or a recovery attempt. It only needs the declared type,
identity, version, and transition contract.

### 5.3 `Transition<TRequest, TResult>`

A transition is an effectful typed operation over one or more resources.

Minimal transition contract:

```text
Transition<TRequest, TResult> {
  name
  input_resources
  expected_versions
  request_type
  result_type
  preconditions
  write_set
  conflict_policy
  idempotency_key
  resume_policy
  audit_projection
}
```

The request and result are domain-typed values. The runtime enforces the
durable rules around version checks, declared writes, atomicity, retry, and
audit. The library defines what the transition means.

Illustrative in-Lisp shape:

```lisp
(resource-transition complete-backlog-item
  :resource selected-item
  :expect-version selected-version
  :request (CompleteBacklogItem
             :terminal_result terminal-result
             :artifacts produced-artifacts))
```

The runtime does not need a built-in `DONE` state. The `CompleteBacklogItem`
transition's typed preconditions define when the transition is valid. A
workflow family may use `DONE`, `MERGED`, `ARCHIVED`, `ACCEPTED`, or no status
label at all.

## 6. Domain Contexts As Library Records

Domain contexts remain useful, but they are records over the generic core.

Example:

```text
PhaseCtx {
  run: RunCtx
  phase_name: PhaseName
  phase_resource: Resource<PhaseState>
  report_view: MaterializedViewRef
  bundle_root: AllocatedPath
}
```

```text
DrainCtx {
  run: RunCtx
  drain_resource: Resource<DrainState>
  backlog_resource: Resource<BacklogState>
  iteration: DrainIteration
}
```

```text
RecoveryCtx {
  run: RunCtx
  blocked_item: Resource<BacklogItemState>
  recovery_resource: Resource<RecoveryState>
  retry_identity: ResumeIdentity
}
```

These records can be defined in stdlib or workflow-family modules. They may
have helpers such as `phase-report-path`, `current-selection`, or
`record-recovery-attempt`, but those helpers lower to generic allocation,
projection, resource, and transition effects.

## 7. Resource State Labels

State labels such as `ACTIVE`, `BLOCKED`, `DONE`, and `EXHAUSTED` are domain
fields, not runtime requirements.

They are useful when a workflow family wants a finite-state resource model:

```text
BacklogItemState =
  | Active(...)
  | Blocked(...)
  | Done(...)
```

But a workflow can also model progress without coarse status labels:

```text
BacklogItemState {
  completed_at: Optional<Timestamp>
  terminal_result: Optional<WorkItemTerminalResult>
  blockers: List<Blocker>
  attempts: List<AttemptRef>
}
```

The generic transition core supports both. It requires typed preconditions and
declared writes, not a universal status enum.

## 8. File-Backed State

This design does not require a workflow system to expose file manipulation as
its resource state machine.

Files are one possible backing store and one possible materialized view. The
runtime contract should be phrased in terms of resources, versions,
transitions, artifacts, and views. A concrete implementation may persist those
through:

- workspace JSON files;
- append-only ledgers;
- content-addressed artifact records;
- a database;
- object storage; or
- certified migration adapters.

When the backing store is files, the abstraction is still needed because raw
file writes do not by themselves define:

- resource identity;
- version/freshness;
- valid transition preconditions;
- conflict behavior;
- idempotency;
- resume behavior;
- public/private boundary;
- source-map provenance; or
- parity evidence.

## 9. Certified Adapters

Certified adapters remain necessary for legacy scripts and external tools, but
they should target the generic core.

A retained adapter that moves resources should declare itself as implementing
a `Transition<TRequest, TResult>` behavior class, not as a special drain,
phase, or recovery primitive.

Examples:

| Legacy helper behavior | Preferred classification |
| --- | --- |
| update run-state JSON | `Transition<RunStateUpdateRequest, RunStateUpdateResult>` |
| record blocked recovery | `Transition<RecoveryRecordRequest, RecoveryRecordResult>` |
| publish selector bundle | typed projection or `Transition<SelectionPublishRequest, SelectionPublishResult>` if it commits resource state |
| move backlog item | `Transition<BacklogMoveRequest, BacklogMoveResult>` |

This keeps Python acceptable at the boundary while preventing Python from
owning invisible workflow semantics.

## 10. Minimal Adapter-Retirement Surface

This design should not grow into a general Python replacement language. The
minimal path for retiring simple Python adapters is four workflow-safe
surfaces:

1. pure typed projection: construct a typed record or union from existing typed
   values without invoking a command;
2. a tiny deterministic expression surface for those projections: string and
   enum equality, boolean literals/operators/conditionals, field access,
   record construction/update, and option/default handling;
3. materialized value views: write a typed value as deterministic JSON or text
   for prompt, report, or compatibility consumers without making the file
   semantic authority; and
4. typed transitions: commit durable resource changes through
   `Transition<TRequest, TResult>` with version, idempotency, conflict, resume,
   audit, source-map, and Semantic IR evidence.

These surfaces split adapter retirement by authority class:

| Current adapter behavior | Minimal replacement |
| --- | --- |
| selector/action classification | pure typed projection |
| terminal outcome classification | match plus typed projection |
| summary or bundle view writing | materialized value view over typed state |
| run-state, ledger, queue, or recovery mutation | typed transition |
| external tools or legacy protocol bridges | certified adapter remains |

Do not add map/filter/sort libraries, arbitrary file IO, general JSON
manipulation, or broad path-string helpers merely to remove a Python script.
Add those only when a concrete workflow-safe contract requires them. State and
path authority should flow through typed values, materialized views,
`StateLayout`, and typed transitions rather than unconstrained Lisp file
operations.

This surface is intentionally limited to scalar predicates and typed value
construction; it is not a general string-processing or scripting layer.

## 10A. Public Boundary And Bookkeeping Path Retirement

Workflow inputs should remain user-provided when they are true public semantic
inputs. The cleanup target is not "derive every path"; it is to stop exposing
runtime bookkeeping, generated output targets, and YAML-era compatibility paths
as ordinary high-level `.orc` inputs.

Classify each path-like boundary value before removing or deriving it:

| Class | Meaning | Treatment |
| --- | --- | --- |
| `public_authored` | The caller genuinely chooses the value, such as target design, baseline design, steering, or an explicit output root | Keep as public input |
| `compatibility_bridge` | A YAML-era state or artifact path retained for parity, migration, or existing consumers | Keep temporarily with provenance, `parity_constrained` labeling, and a retirement path |
| `runtime_derived` | A value derived from `RunCtx`, resource identity, or `StateLayout` | Hide from public input and bind internally |
| `generated_internal` | Compiler/runtime-owned bundle, write-root, temp, or sidecar path | Allocate through `StateLayout` and keep private |
| `materialized_view` | Deterministic file representation of a typed value for prompts, reports, or compatibility consumers | Allocate as a view; do not treat as semantic authority |

For the Design Delta Drain family, examples of likely public authored inputs
are `steering_path`, `target_design_path`, and `baseline_design_path`.
Examples of compatibility bridges include existing YAML-facing
`manifest_path`, `progress_ledger_path`, and `run_state_path` while parity
still compares those surfaces. Examples of generated/internal or view paths
include selection bundle views, draft bundle targets, validation bundle
targets, per-iteration roots, check/report outputs, and drain summary views.

Retirement order:

1. add boundary classification metadata and lints so every path-like value has
   an authority class;
2. hide or derive generated/internal output targets first;
3. replace deterministic publication scripts with typed projection plus
   materialized value views;
4. keep YAML-era state paths only as compatibility bridges until parity no
   longer requires them; and
5. fail promotion on unclassified bookkeeping paths or generated/internal paths
   exposed as public inputs.

Parent-callable candidates may tolerate classified compatibility bridges.
Promotion-quality boundaries may expose only true public authored inputs plus
explicitly accepted compatibility inputs; generated internals and
runtime-derived values must be private.

## 11. Relationship To The Post-Foundation Design

The post-foundation design should keep its domain context names as examples and
acceptance fixtures, but it should treat them as library-level typed records.

Recommended interpretation:

- `RunCtx`: runtime-owned private executable context.
- `PhaseCtx`: stdlib/library record derived from `RunCtx` and phase resources.
- `ItemCtx`: stdlib/library record derived from item resources and allocation.
- `DrainCtx`: workflow-family or stdlib record over drain/backlog resources.
- `SelectionCtx`: workflow-family record over selection result/projection
  resources.
- `RecoveryCtx`: workflow-family record over blocked/recovery resources.

The post-foundation tranches still stand:

- nested structured control is still needed;
- private context is still needed;
- typed projection and materialized value views are still needed;
- certified adapters are still needed;
- resource transitions are still needed;
- parent-callable parity is still needed.

This document narrows the implementation substrate for those tranches so the
runtime does not grow one primitive per workflow-family noun or one adapter
replacement primitive per Python script.

## 12. Acceptance Criteria

The simpler core is acceptable only if it can express the same migration
requirements without hiding semantics.

Required evidence:

- a `RunCtx` private binding is hidden from public `.orc` entrypoints;
- a library-defined `PhaseCtx` can be constructed from `RunCtx`,
  `Resource<PhaseState>`, and `StateLayout` allocations;
- a library-defined `DrainCtx` can carry drain/backlog resources without
  runtime knowing a special `drain` scope;
- resource transitions expose typed request/result contracts to shared
  validation and Semantic IR;
- transition implementations can be runtime-native or certified adapters with
  the same visible contract;
- source maps identify domain helper calls and their generated generic
  resource/transition effects;
- pure typed projections can replace selector/action and terminal
  classification adapters without losing source-map or Semantic IR provenance;
- materialized value views can replace summary/bundle-view writers while
  preserving typed values as semantic authority;
- resume uses generic resource identity, version, call-frame, loop-frame, and
  allocation identity;
- public/private boundary inspection proves generated roots and resources are
  not public authored inputs; and
- migration parity can compare terminal states, artifacts, resource versions,
  and transition audit evidence without knowing workflow-family-specific
  runtime scope names.

## 13. Non-Goals

- Do not remove domain records such as `PhaseCtx` or `DrainCtx` from authoring
  examples.
- Do not force every workflow family to use status labels.
- Do not require file-backed state.
- Do not ban Python, shell, or external tools.
- Do not add arbitrary file IO, general JSON manipulation, or a broad
  collection-processing library merely to remove adapters.
- Do not introduce runtime closures or dynamic procedure values.
- Do not make `Resource<TState>` a public authored-YAML artifact kind in this
  document.
- Do not rewrite existing YAML workflows as part of this design.

## 14. Verification Strategy

Focused fixtures:

- compile a `.orc` helper that builds `PhaseCtx` as a record over `RunCtx` and
  `Resource<PhaseState>`;
- compile a `.orc` helper that executes a typed `complete-backlog-item`
  transition without a runtime-special item scope;
- compile a `.orc` helper that records recovery through a typed transition
  without a runtime-special recovery scope;
- reject public `RunCtx`, resource root, or `__write_root__...` inputs at a
  promoted boundary;
- source-map generated transition effects back to authored helper calls;
- verify Semantic IR records generic resource/transition effects plus domain
  type names;
- verify pure typed projections can replace selector/action and terminal
  classification adapters without introducing command steps;
- verify materialized value views can replace summary/bundle-view writers
  without becoming semantic authority;
- verify a certified adapter and a runtime-native implementation satisfy the
  same transition contract; and
- verify parity reporting can classify resource-transition evidence without
  special-casing drain-family scope names.

## 15. Migration Recommendation

Revise future post-foundation work to implement the generic core first. Keep
the six context names as vocabulary for the Design Delta Drain and stdlib
fixtures, but avoid treating them as runtime primitives.

Implementation order:

1. define private `RunCtx` and public/private boundary inspection;
2. define `Resource<TState>` metadata and source-map/Semantic IR projection;
3. define `Transition<TRequest, TResult>` contracts and effect summaries;
4. express `PhaseCtx` and `DrainCtx` as library records over the generic core;
5. add pure typed projection and materialized value-view support for
   deterministic adapter-retirement cases;
6. map retained Python helpers to typed projection, materialized value view,
   typed transition, or certified external/legacy adapter behavior;
7. add fixtures proving parent-callable workflows do not expose generated
   state roots; and
8. update the post-foundation design to reference this simplified substrate.

This keeps the runtime small while preserving the authority guarantees that
made resource transitions necessary in the first place.
