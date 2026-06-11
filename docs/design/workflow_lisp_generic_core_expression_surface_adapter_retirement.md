# Workflow Lisp Generic Core, Expression Surface, And Adapter Retirement

Status: draft target design
Kind: architecture decision / runtime simplification and language-extension target
Created: 2026-06-11
Scope: generic runtime resource/context core; pure expression surface; typed
projection; materialized value views; typed transitions; boundary authority
classes; stdlib-owned domain contexts; adapter retirement for workflow
semantics; and Design Delta Drain family cleanup.

Authority:

- Normative runtime and DSL behavior remains in `specs/`.
- `docs/design/workflow_lisp_frontend_specification.md` is the authoritative
  Workflow Lisp language baseline. This document proposes deltas to merge into
  that baseline; it does not fork it.
- `docs/design/workflow_lisp_generic_resource_context_core.md` is the decision
  record for the small runtime core. This document is the executable target for
  that decision.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  owns the broader family migration sequence, readiness labels, parent-callable
  parity evidence, and promotion gates. This document supplies the substrate
  that its context, projection, adapter, resource-transition, and
  post-promotion simplification tranches consume.
- `docs/design/workflow_lisp_core_calculus_middle_end.md` owns WCC, ANF
  normalization, scope/effect/proof analysis, and defunctionalization. This
  document extends the atom/projection/effect surfaces only; it adds no
  competing control-flow lowering route.
- `docs/design/workflow_lisp_state_layout.md` owns generated path identity and
  allocation rules. Pure-projection, materialized-view, and transition-audit
  paths route through it.
- `docs/design/workflow_command_adapter_contract.md` owns adapter certification
  policy. This document owns the retirement taxonomy and evidence boundaries for
  replacing workflow-semantics adapters.

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_generic_resource_context_core.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/lisp_workflow_drafting_guide.md`
- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `specs/state.md`
- `specs/dsl.md`

## 1. Purpose

The next Workflow Lisp target should make the language expressive enough to
retire Python or shell adapters that only encode workflow semantics, while
making the runtime smaller and easier to maintain.

The intended endpoint is:

```text
runtime owns durable invariants;
Workflow Lisp owns typed authoring and stdlib composition;
workflow-family libraries own domain records;
Python/bash remain only for genuine external processes or certified temporary bridges.
```

The Design Delta Drain `.orc` family is the motivating fixture. Its parent
`drain.orc` already uses typed records, unions, `loop/recur`, `match`,
provider results, command results, and imported child workflows. It also still
exposes YAML-era mechanics: public context records, public state and bundle
paths, command adapters for selector projection, command adapters for terminal
status and summary writing, and loop state that carries file paths rather than
typed resource state.

Those are not isolated problems. They share one root cause:

```text
semantics escape to Python because the language cannot express them;
bookkeeping paths become public because files are the easiest transport;
the runtime grows domain nouns because escaped concepts are patched back in as special cases.
```

The fix is one architectural move:

```text
small generic runtime core
  + minimal total expression surface
  + typed projection
  + materialized value views
  + typed resource transitions
  + mandatory boundary authority classes
  + stdlib/domain contexts over the generic core
```

## 2. Executive Decision

Adopt the generic core from
`workflow_lisp_generic_resource_context_core.md` and implement it with the
minimal expression/projection substrate needed to retire semantic adapters:

```text
Runtime owns:
  RunCtx
  Resource<TState>
  Transition<TRequest, TResult>
  StateLayout allocation
  resume identity
  provenance and audit
  one closed pure-expression evaluator

Language owns:
  pure expression core
  typed projection
  materialized value views
  transition call surface
  boundary authority classification

Stdlib/domain modules own:
  PhaseCtx
  ItemCtx
  DrainCtx
  SelectionCtx
  RecoveryCtx
  with-phase
  finalize-selected-item
  backlog-drain
  review/revise composition

Python/bash keep:
  genuine system interaction behind certified command/adapters
  temporary migration backends under typed contracts
```

The design principle is:

```text
Bake invariants into the runtime.
Keep workflow-domain state in Workflow Lisp libraries.
```

Implement the work in ordered tranches:

- G0: adapter census, boundary authority classification, and retirement labels.
- G1 (P0): pure expression core, WCC atom/projection support, and runtime
  evaluator.
- G2: pure typed projection retirement for classification/routing adapters.
- G3 (P0): generic resource and transition runtime core.
- G4: materialized value views.
- G5: context generalization: `RunCtx`-only runtime bootstrap and type-driven
  private-context classification.
- G6: stdlib migration of phase/drain forms onto the generic core.
- G7: Design Delta Drain boundary and adapter cleanup.
- G8: evidence-gated deletion of retired ontology tables, retired adapters, and
  raw semantic argv surfaces.

G1 and G3 are the two load-bearing substrate tranches. They may proceed in
parallel after G0. G8 is deletion-only and must not be selected until evidence
from G2 through G7 proves every removed path is unused.

## 3. Problem And Current Evidence To Verify

### 3.1 Adapter behavior is underclassified

The Design Delta Drain family uses command adapters for several behavior
classes:

- typed field projection;
- routing/classification over status values;
- run-state and ledger mutation;
- summary and bundle view writing;
- manifest/index assembly;
- path and pointer materialization;
- validation against schemas; and
- genuine external checks or tools.

Only the last class inherently requires external Python, shell, or subprocess
execution. The others are candidates for typed projection, materialized views,
or resource transitions.

This document intentionally does not bake in exact script counts. Tranche G0
must produce the verified census from the current checkout and make every
classification machine-checkable before retirement work proceeds.

### 3.2 The reference drain exposes YAML-era internals

`workflows/library/lisp_frontend_design_delta/drain.orc` currently exposes
path-like public inputs including:

- `phase-ctx`;
- `manifest_path`;
- `progress_ledger_path`;
- `run_state_path`;
- `architecture_bundle_path`;
- `selection_bundle_report_path`;
- `existing_architecture_index_path`;
- generated draft and validation bundle targets; and
- `drain_summary_target_path`.

Some are true public authored inputs. Many are compatibility bridges,
runtime-derived values, generated internals, or materialized-view targets. The
promoted boundary must distinguish those classes instead of treating every path
as caller-authored workflow input.

### 3.3 Runtime context recognition is too domain-shaped

The current system has grown several context names and phase/drain lowering
hooks. The exact code locations and current count are implementation details
that G0 must verify. The architecture problem is durable: if every family noun
becomes a runtime-recognized context, the runtime becomes a taxonomy of
applications rather than a workflow execution substrate.

The target runtime should recognize only the generic core. Contexts such as
`PhaseCtx`, `DrainCtx`, `ItemCtx`, `SelectionCtx`, and `RecoveryCtx` should be
records in stdlib or workflow-family modules over `RunCtx`, resources,
transitions, and allocations.

### 3.4 The language has types without enough total operators

The frontend has typed values such as `Bool`, `String`, `Int`, records, unions,
options, lists, and maps. The missing piece is a small total operator set:
boolean connectives, equality, ordering where type-safe, integer arithmetic,
option/default handling, bounded string construction, and record update.

Without those operators, simple workflow semantics become command adapters.
Examples include selector action projection, terminal-state classification,
iteration count updates, reason/default string construction, and transition
preconditions.

## 4. Authority And Dependency Direction

### 4.1 This Document Consumes

- WCC as the compiler substrate for all new expression/projection work.
- Runtime foundation contracts for private typed values, structured output,
  strict gates, and `StateLayout`/`PathAllocator`.
- Post-foundation projection, adapter, private-context, and promotion evidence
  requirements.
- Adapter certification policy from the command-adapter contract.
- State layout rules for generated paths, source maps, and resume identity.

### 4.2 This Document Owns

- the pure expression core and its typing/totality rules;
- runtime evaluator semantics for pure projection payloads;
- the generic `Resource<TState>` and `Transition<TRequest, TResult>` target
  contract;
- materialized value-view authority rules;
- boundary authority classes and promotion lints;
- adapter retirement labels and retirement evidence;
- `RunCtx`-only runtime bootstrap as the context generalization target;
- stdlib migration targets for phase/drain domain contexts over the generic
  core; and
- the Design Delta Drain cleanup acceptance vehicle for this substrate.

### 4.3 This Document Does Not Own

- normative DSL/runtime behavior until a spec delta is merged;
- WCC calculus or pass structure;
- concrete path names or allocation identity;
- adapter certification mechanics;
- the family promotion sequence and parity gate thresholds;
- runtime closures or dynamic procedure values; or
- broad collection/string-processing libraries.

### 4.4 Prohibited Directions

```text
workflow-family noun        -> runtime scope/effect/path kind     PROHIBITED
adapter retirement pressure -> general scripting surface           PROHIBITED
pure expression core        -> IO, clock, randomness, shell        PROHIBITED
materialized view           -> semantic authority                  PROHIBITED
stdlib module/workflow name -> compiler branch                     PROHIBITED
boundary cleanup            -> hiding true public authored inputs  PROHIBITED
```

## 5. Goals

- Keep the runtime's workflow-facing vocabulary generic: run identity,
  resources, transitions, allocations, views, projections, resume, provenance,
  and audit.
- Let authors express scalar predicates, counting, message construction,
  option defaulting, record/union construction, and simple transition
  preconditions in Workflow Lisp.
- Retire Python adapters that only classify, project, format, or mutate
  workflow state by convention.
- Preserve Python/bash only for genuine system interaction or certified
  temporary migration backends.
- Make durable state changes go through typed transitions with runtime-enforced
  version, idempotency, conflict, atomic/fail-closed commit, resume, and audit
  behavior.
- Require boundary authority classification for all path-like values in
  parent-callable candidates.
- Move `PhaseCtx`, `ItemCtx`, `DrainCtx`, `SelectionCtx`, and `RecoveryCtx` to
  stdlib/domain records over the generic core.
- Close the backend ambiguity for `resource-transition`: the target contract is
  runtime-native, with certified adapters allowed as migration backends under
  the same visible contract.

## 6. Non-Goals

- Do not add a general scripting language.
- Do not add runtime closures, runtime procedure values, dynamic workflow
  dispatch, runtime-loaded code, arbitrary file IO, arbitrary JSON parsing,
  regex/report parsing, network access, or shell interpolation as language
  primitives.
- Do not add broad collection operators such as `map`, `filter`, `sort`, or
  arbitrary `length` until a future census proves a workflow-safe need.
- Do not remove Python, shell, or command execution for genuine external work.
- Do not remove domain context names from authoring. They remain useful records;
  they stop being runtime-recognized primitives.
- Do not rewrite YAML primaries or claim promotion based on these surfaces
  alone. Promotion remains governed by computed parity evidence.
- Do not redesign the runtime around nested executable IR; WCC still
  defunctionalizes into the existing validated runtime model.

## 7. Architecture Invariants

- Generic runtime vocabulary: no workflow-domain noun is a runtime scope kind.
- Single pure-expression semantics: runtime projection evaluation is
  authoritative; compile-time folding is an optimization that must agree.
- Totality and determinism: every pure operator is total over its typed domain
  or fails closed with a typed diagnostic.
- No ambient effects in pure expressions: no IO, filesystem, clock, randomness,
  provider, workflow, command, or network effects.
- Values are semantic authority; materialized views are representations.
- Transitions are the only in-language durable mutation surface.
- Runtime-native transitions and certified-adapter transitions with the same
  contract must be observationally equivalent at the contract boundary.
- Boundary classification is mandatory for parent-callable candidates.
- Surface growth is census-driven. New operators and helpers require a verified
  adapter behavior or fixture that the existing surface cannot express.
- Every replacement for an adapter must remain effect-visible in Semantic IR,
  source maps, and parity evidence.
- New evidence for these surfaces runs on the WCC/schema-2 route.

## 8. Core Model

### 8.1 `RunCtx`

`RunCtx` is the only runtime-bootstrapped private execution context. It carries
or derives:

- run identity;
- managed state, artifact, and temp roots;
- allocation namespace;
- resume namespace;
- provenance/source-map namespace; and
- the `StateLayout` handle.

`RunCtx` may appear in executable contracts, source maps, Semantic IR, runtime
state, and diagnostics. It must not appear as a public authored input of a
promoted workflow.

### 8.2 `Resource<TState>`

A resource is durable workflow-managed state with identity, declared state
type, version, state reference, and provenance:

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

The runtime does not know whether a resource is a backlog item, drain, phase,
recovery attempt, queue entry, design gap, release, or experiment. It knows type
identity, resource identity, version, declared effects, and transition
contracts.

### 8.3 `Transition<TRequest, TResult>`

A transition is an effectful typed operation over one or more resources:

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

The runtime enforces version checks, declared writes, atomic commit or
fail-closed abort, idempotent retry, conflict detection, resume identity, and
audit evidence. The stdlib or workflow-family module defines the transition's
domain meaning.

There is no built-in `DONE` state and no universal status enum. Families define
their own state types and transition preconditions.

### 8.4 Pure Expression Core

The pure expression core is a closed set of typed, total, deterministic
operators over existing scalar and structured types. Pure operators elaborate
to WCC atoms; ANF orders them; defunctionalization folds visible producer
regions into typed projection steps where a cross-boundary or materialized value
is needed.

The runtime evaluates projection payloads with a closed interpreter:

- no recursion into user code;
- no loops except structural traversal of the payload;
- no IO;
- no ambient state; and
- bounded payload size fixed at compile time.

### 8.5 Materialized Value Views

A materialized view renders a typed value to a deterministic representation,
usually canonical JSON or a registered text/Markdown renderer. It receives a
`StateLayout`-allocated path and an authority class of `materialized_view`.

The typed value remains semantic authority. The view is a report, prompt input,
compatibility representation, or public artifact only according to its declared
contract.

### 8.6 Boundary Authority Classes

| Class | Meaning | Treatment |
| --- | --- | --- |
| `public_authored` | Caller genuinely chooses the value | Keep public |
| `compatibility_bridge` | YAML-era surface retained for parity or consumers | Keep temporarily with owner and retirement route |
| `runtime_derived` | Derivable from `RunCtx`, resource identity, or `StateLayout` | Bind internally |
| `generated_internal` | Compiler/runtime bundle, write root, temp, sidecar, or checkpoint | Allocate privately |
| `materialized_view` | Deterministic rendering of typed value | Allocate as view; never semantic authority |
| `public_artifact` | Intentionally exposed artifact value | Keep public only when explicitly contracted |

Parent-callable candidates may carry labeled bridges. Promotion-quality
boundaries expose only `public_authored` plus explicitly accepted
`compatibility_bridge` values.

### 8.7 What Remains External

A retained Python/bash command must satisfy at least one condition:

- genuine system interaction: external process, shell, git/gh, network,
  benchmark, validator, or provider wrapper;
- declared transition backend during migration;
- certified legacy bridge with `parity_constrained` label and retirement route.

Everything else is adapter-retirement backlog.

## 9. Tranche G0: Census And Boundary Classification

### 9.1 Contract

Freeze the current adapter and boundary state as machine-checkable evidence so
later tranches measure actual retirement instead of relying on impressions.

### 9.2 Tasks

- Build a checked adapter census covering every script invoked by the reference
  family and every certified adapter manifest entry.
- Classify behavior as one of:
  `typed_projection`, `outcome_classification`, `resource_transition`,
  `view_writer`, `manifest_assembly`, `path_materialization`, `validation`,
  `genuine_system`, or `legacy_bridge`.
- Assign each adapter a retirement label:
  `retire_to_projection`, `retire_to_view`, `retire_to_transition`,
  `keep_certified_system`, `keep_bridge`, or `unknown_requires_design`.
- Add boundary classification metadata for every path-like input/output in the
  Design Delta Drain family.
- Add a promotion lint for unclassified bookkeeping paths and for
  `generated_internal` or `runtime_derived` values exposed as public inputs.

### 9.3 Acceptance

- The census artifact exists and is validated in CI.
- Boundary reports exist for `drain`, `selector`, `work_item`, plan phase,
  implementation phase, and design-gap architect surfaces.
- No path-like value remains unclassified in the reports.
- A negative fixture exposing a generated internal path publicly fails the
  promotion lint.

## 10. Tranche G1: Pure Expression Core

### 10.1 Contract

Add a closed, total, deterministic operator set over existing types. Operators
compile through WCC atoms and projection payloads and execute through one
runtime evaluator.

### 10.2 Operator Set

| Group | Operators | Typing | Initial justification |
| --- | --- | --- | --- |
| Equality | `=`, `!=` | `String`, `Int`, `Bool`, `Symbol`, enum with same type | status/routing projection |
| Ordering | `<`, `<=`, `>`, `>=` | `Int` with `Int`; `Float` with `Float` | iteration and attempt bounds |
| Boolean | `and`, `or`, `not` | `Bool` operands | compound routing conditions |
| Arithmetic | `+`, `-`, `*`, `min`, `max` | `Int` operands, `Int` result | iteration/item counting |
| String | `string/concat`, `string/empty?`, `symbol/name` | strings/symbols only | reason/summary construction |
| Option | `some?`, `or-else` | `Optional[T]`; fallback type `T` | optional defaults |
| Record | `record-update` | record plus field bindings | loop-state evolution |

Deliberate exclusions:

- no division/modulo until justified;
- no float equality;
- no path string concatenation;
- no deep record equality;
- no union equality;
- no collection operators; and
- no regex or broad string processing.

Variant discrimination stays with `match` and proof contexts. An `if` over a
status string cannot justify variant-specific field access.

### 10.3 Semantics

- strict typing and no implicit coercion;
- 64-bit integer arithmetic with fail-closed overflow diagnostics;
- deterministic evaluation independent of step order;
- no IO or ambient state;
- optional access must be proven or defaulted; and
- one runtime interpreter is the authoritative semantics.

### 10.4 Compilation

- WCC gains pure-operator atoms.
- ANF normalizes nested pure expressions.
- Defunctionalization folds visible pure regions into typed projection steps
  when a workflow output, materialized view, transition precondition, or
  cross-boundary value needs a producer.
- Projection steps include `pure_expr_schema_version`.
- Source maps record each folded operator's authored span.

### 10.5 Acceptance

- Runtime interpreter and compile-time folding agree on shared golden vectors.
- A loop counter can increment and compare without a command adapter.
- Selector-action projection can be written without a command adapter.
- Overflow, union equality, float equality, and path string-concat negative
  fixtures fail with typed diagnostics.
- Every operator has a G0 census or fixture justification.

### 10.6 Normative Spec Deltas

- Add the operator table to the frontend specification's pure-expression
  section.
- Allow computed pure `Bool` conditions.
- State that union discrimination still requires `match`.
- Add diagnostics for unsupported pure operators, union equality, float
  equality, optional access without proof/default, and pure expression overflow.

## 11. Tranche G2: Pure Typed Projection Adapter Retirement

### 11.1 Contract

Replace adapters whose behavior class is `typed_projection` or
`outcome_classification` with in-language pure projections.

### 11.2 Tasks

- Re-express selector action projection from `SelectorPublicResult` to
  `DesignDeltaDrainAction`.
- Re-express work-item terminal classification after phase results are proper
  typed unions.
- Re-express blocked-recovery route classification when its inputs are typed
  state rather than reports.
- Keep adapters callable during a bridge window.
- Add dual-run fixtures comparing adapter output and in-language projection as
  typed values.
- Mark adapters `retired` in the census only after the family stops invoking
  them.

### 11.3 Acceptance

- Named projection/classification adapters have in-language replacements.
- Dual-run parity passes before flip.
- The reference family has no command step for selector action projection.
- Replacement effects are projection effects only.

## 12. Tranche G3: Generic Resource And Transition Runtime Core

### 12.1 Contract

Implement `Resource<TState>` and `Transition<TRequest, TResult>` as runtime
contracts with enforced invariants. The target backend is runtime-native;
certified adapters may implement the same contract during migration.

### 12.2 Runtime Obligations

- resource registry with identity, kind, declared state type, version, and
  provenance;
- transition input version checks;
- precondition evaluation through the G1 pure evaluator;
- declared write-set enforcement;
- atomic commit or fail-closed abort;
- idempotency-key deduplication;
- conflict policy;
- resume identity registration;
- audit record persistence; and
- Semantic IR/effect entries for transition name, request/result type, and
  resource writes.

### 12.3 Tasks

- Define transition declarations and type/effect rules.
- Implement a first file-backed runtime transition executor behind the generic
  contract.
- Rebind run-state mutation, drain status update, terminal work-item recording,
  and blocked recovery recording as declared transitions.
- Ensure nested subprocess adapter calls are dissolved into declared effects.
- Add backend-equivalence tests for runtime-native and certified adapter
  implementations.

### 12.4 Acceptance

- Version mismatch, precondition rejection, undeclared write, conflict,
  idempotent replay, and resume fixtures pass.
- Run-state mutation executes as declared transition in a family fixture.
- Transition audit records are available to parity evidence.

### 12.5 Normative Spec Deltas

- Generalize `resource-transition` around `Transition<TRequest, TResult>`.
- Define preconditions as pure expressions.
- Add a generalized transition effect to Semantic IR/effect docs.
- Record certified adapters as migration backends under the same transition
  contract.

## 13. Tranche G4: Materialized Value Views

### 13.1 Contract

`materialize-view` renders typed values to deterministic files for prompts,
reports, compatibility, or public artifacts without granting the file semantic
authority.

### 13.2 Tasks

- Add `materialize-view` over canonical JSON and versioned registered text
  renderers.
- Add `StateLayout` allocation role `materialized_view`.
- Add source-map and Semantic IR entries for view value type, renderer, target,
  allocation identity, and authority class.
- Replace summary/bundle writer scripts when they only render typed state.

### 13.3 Acceptance

- Identical typed input produces byte-identical view output across run/resume.
- Drain summary can be generated as typed result plus materialized view.
- A negative fixture consuming a view as semantic authority fails.

## 14. Tranche G5: Context Generalization

### 14.1 Contract

`RunCtx` is the only runtime-bootstrapped context. Private context
classification becomes type-driven rather than name-driven.

### 14.2 Classification Rule

A record is private executable context if it transitively contains a `RunCtx`, a
`Resource` handle, or a runtime-derived allocation. Capabilities derive from the
core handles the record carries, not from the record's name.

### 14.3 Tasks

- Implement type-driven context classification.
- Keep existing name-based recognition only as labeled compatibility until
  differential evidence proves it redundant.
- Define `PhaseCtx`, `ItemCtx`, `DrainCtx`, `SelectionCtx`, and `RecoveryCtx`
  in stdlib/domain modules as records over `RunCtx`, resources, and
  allocations.
- Add `RunCtx`-only entry bootstrap and hidden internal binding.

### 14.4 Acceptance

- A new domain context name unknown to the runtime receives correct private
  classification and allocation behavior.
- A promoted entrypoint constructs `PhaseCtx` or `DrainCtx` from runtime
  `RunCtx` without exposing them publicly.
- Differential tests prove type-driven classification matches existing
  behavior before old name tables are deleted.

### 14.5 Normative Spec Deltas

- `RunCtx` is the runtime-owned exception.
- Domain contexts are library records over the generic core.
- Private context classification is structural/type-driven.

## 15. Tranche G6: Stdlib Migration Of Phase/Drain Forms

### 15.1 Contract

`with-phase`, `finalize-selected-item`, and `backlog-drain` become stdlib
`.orc` code over the generic core rather than Python lowering hooks keyed to
domain form names.

### 15.2 Tasks

- Implement `std/context`, `std/resource`, `std/projection`, and `std/drain`
  modules.
- Express `with-phase` as context construction plus scoped allocation.
- Express `finalize-selected-item` as typed match/projection plus transition.
- Express `backlog-drain` as `loop/recur`, typed selection/result unions, and
  resource transitions.
- Add hook-redundancy evidence before deleting old lowering hooks.

### 15.3 Acceptance

- Stdlib forms compile through ordinary import/specialization/typecheck/WCC.
- No promoted fixture depends on a compiler branch keyed to a stdlib form name.
- Deleting a redundant hook does not change accepted fixture output.

## 16. Tranche G7: Design Delta Drain Cleanup

### 16.1 Contract

Re-express the Design Delta Drain family in the target idiom as the end-to-end
acceptance vehicle for this substrate.

### 16.2 Target Shape

- Public inputs keep only true authored values such as steering, target design,
  baseline design, and explicitly authored references.
- YAML-era state files are labeled `compatibility_bridge` while parity requires
  them.
- `phase-ctx`, generated bundle targets, summary targets, selection bundle
  report paths, and internal state roots are private, derived, generated, or
  views.
- Loop state carries typed values and resource handles, not path authority.
- Selector action and terminal classification are pure projections.
- Status and recovery updates are transitions.
- Summaries and reports are materialized views.
- Remaining external checks are certified `genuine_system` commands.

### 16.3 Acceptance

- The cleaned family compiles on the WCC route.
- Boundary inspection shows only `public_authored` and labeled bridges public.
- No workflow-semantics adapter executes in the reference family fixture.
- Strict parity can compare typed terminal states, resource versions,
  transition audits, and materialized views.

## 17. Tranche G8: Evidence-Gated Legacy Deletion

### 17.1 Contract

Delete only what evidence proves is dead.

### 17.2 Tasks

- Delete name-keyed context tables after G5 differential evidence and family
  migration.
- Delete retired adapter scripts after no workflow invokes them and census
  labels are `retired`.
- Delete or shrink redundant phase/drain lowering hooks after G6
  hook-redundancy evidence.
- Add CI guards against reintroducing name-keyed context recognition or raw
  semantic argv in high-level family modules.

### 17.3 Acceptance

- Grep guards prove removed context tables are absent.
- Deleted adapters are absent from tree and manifest.
- Family fixtures still pass.
- Deletion evidence reports line-count and hook-surface reduction.

## 18. Design Details

### 18.1 One Predicate Semantics

Transition preconditions, `if` conditions, projection logic, and boundary lints
use the same pure expression semantics. There is no adapter-resident predicate
language and no second precondition language.

### 18.2 Projection Folding

Defunctionalization folds maximal effect-free regions into one projection step
per binding group where a visible producer is required. Step identity comes
from semantic ownership, scope, loop/call frame, and lowering schema version,
not operator count.

### 18.3 Atomicity Honesty

`resource-transition` must not claim stronger atomicity than the backend can
provide. The first file-backed executor may provide single-resource atomic
commit and multi-resource fail-closed sequencing with recorded partial-failure
evidence. Stronger transactionality requires a backend that actually supports
it.

### 18.4 Bridge-Window Dual Running

Adapter retirement follows one protocol:

```text
declare replacement
dual-run against incumbent adapter
compare typed values
flip family to replacement
mark adapter retired
delete in G8
```

Retirement without dual-run evidence is prohibited.

## 19. Contracts And Interfaces

### 19.1 Frontend/Typechecker

- operator typing rules;
- optional proof/default rules;
- record-update typing;
- transition declaration typing;
- type-driven private context classifier; and
- boundary authority-class emission.

### 19.2 WCC

- pure-operator atoms;
- projection-step folding;
- route/schema identity for new fixtures; and
- no new control constructs.

### 19.3 Shared Validation

- pure expression payload schema;
- projection output contracts;
- transition request/result/write-set contracts;
- materialized-view renderer and authority-class contracts; and
- public/private boundary validation.

### 19.4 Runtime

- pure-expression interpreter;
- transition executor;
- materialized-view writer;
- private `RunCtx` bootstrap;
- deterministic replay for projections/views; and
- idempotent transition replay.

### 19.5 StateLayout / PathAllocator

New allocation roles:

- `pure_projection`;
- `materialized_view`;
- `transition_audit`;
- `resource_state`; and
- `compatibility_bridge_view`.

This document adds roles, not path identity rules.

### 19.6 Adapter Registry

Add census/retirement metadata:

- behavior class;
- retirement label;
- replacement surface;
- bridge owner;
- expiry condition; and
- evidence links.

## 20. Dependencies And Sequencing

```text
G0
  -> G1 -> G2
  -> G3 -> G4
G1 + G3 -> G5
G3 + G5 -> G6
G1..G6 -> G7
G7 + promotion evidence -> G8
```

Relationship to post-foundation:

| This target | Feeds |
| --- | --- |
| G1/G2 | typed projection substrate |
| G3 | resource-transition ownership |
| G4 | materialized view authority |
| G5 | private executable context bridge |
| G6 | imported/std composition |
| G7 | parent-callable family cleanup |
| G8 | post-promotion simplification and deletion |

## 21. Deferred Work

- collection operators;
- broad string processing;
- regex;
- arbitrary JSON/file IO;
- database/object-store resource backends;
- multi-resource transactional backend stronger than file-backed fail-closed
  sequencing;
- `orchestrate explain`; and
- general-purpose scripting conveniences.

## 22. Evidence And Implementation Boundaries

### 22.1 Required Evidence

- G0 census and boundary reports.
- G1 golden vectors and runtime/folding agreement.
- G2-G4 dual-run retirement evidence.
- G3 backend-equivalence transition suite.
- G5 type-driven vs name-driven differential tests before deletion.
- G6 hook-redundancy evidence.
- G7 family fixture with zero workflow-semantics adapters.
- G8 deletion deltas and grep guards.

### 22.2 Prohibited Evidence

- claiming an adapter retired while a family workflow still invokes it;
- retirement without typed dual-run comparison;
- operator additions without census/fixture justification;
- using materialized views as semantic authority;
- legacy-route-only fixtures as acceptance evidence;
- documentation-only changes counted as adapter retirement;
- deleting name-keyed recognition before differential tests and family
  migration prove it redundant; and
- claiming promotion while unclassified path-like public inputs remain.

## 23. Compatibility And Migration

YAML remains primary until the post-foundation promotion gate passes.

Compatibility windows:

- adapters stay callable until replacement evidence lands and family usage is
  flipped;
- `PhaseCtx` bootstrap recognition may remain as labeled compatibility until
  `RunCtx`-only bootstrap is proven;
- YAML-era state path bridges may remain while parity requires them; and
- legacy schema/route evidence is not acceptance evidence for this target.

Resume compatibility is fail-closed by schema/version identity. Runs must not
silently cross pure-expression schema, transition schema, view-renderer schema,
or lowering-route boundaries.

## 24. Verification Strategy

- operator golden-vector tests;
- compile-time folding vs runtime evaluator agreement;
- projection folding tests;
- transition contract tests parameterized over runtime-native and adapter
  backends;
- crash/idempotency/resume tests for transitions;
- byte-determinism tests for materialized views;
- context classifier differential tests;
- new-domain-context fixture requiring no runtime edit;
- stdlib hook-redundancy dual-compile tests;
- Design Delta Drain family fixture with adapter-free workflow semantics;
- boundary inspection tests; and
- strict parity tests that include resource versions, transition audits,
  materialized views, and route identity.

## 25. Declarative Acceptance Scenarios

### 25.1 The Drain Counts Its Iterations

A drain loop carries `iteration-count : Int`, updates it with `+`, compares it
to `max-iterations`, and lowers through WCC to a visible projection. No command
adapter or stringly counter script participates.

### 25.2 Selector Action Without Python

`SelectorPublicResult` is projected to `DesignDeltaDrainAction` in Workflow
Lisp using equality, boolean operations, option/default handling, and union
construction. Dual-run parity with the previous adapter passes, then the
adapter is retired.

### 25.3 Status Written As A Transition

The drain terminal status update is a declared transition over a
`Resource<DrainRunState>`, with version check, precondition, atomic/fail-closed
commit, audit, and idempotent replay. The summary report is a materialized view
over the transition result.

### 25.4 A New Domain Context Costs Zero Runtime Changes

A workflow family defines `ExperimentCtx` as a record over `RunCtx`,
`Resource<ExperimentState>`, and an allocation scope. Private classification,
allocation, and transition behavior work without editing runtime context-name
tables.

### 25.5 Promotion Boundary Hides Internals

The cleaned drain exposes only true public authored inputs plus labeled YAML
bridges. Public `phase-ctx`, generated bundle targets, state roots, write
roots, and materialized-view targets are absent.

### 25.6 Name Tables Are Deleted

After G8, grep guards find no context-name table or capability map. The family
fixtures still pass and a CI guard rejects reintroduction.

## 26. Success Criteria

- The runtime durable ontology is `RunCtx`, `Resource<TState>`,
  `Transition<TRequest, TResult>`, plus generic allocation, view, projection,
  resume, provenance, and audit mechanics.
- Domain contexts are stdlib/domain records, not runtime primitives.
- The Section 10 operator set is implemented with golden-vector agreement and
  no uncited additions.
- Workflow-semantics adapters in the reference family are retired into pure
  projections, materialized views, or transitions.
- Remaining Python/bash calls are certified genuine-system commands or labeled
  temporary bridges.
- Promoted public boundaries expose only true authored inputs plus accepted
  bridges.
- Generated paths, state roots, bundle targets, view targets, and write roots
  are allocated privately through `StateLayout`.
- Resource transitions produce version/audit evidence visible in Semantic IR
  and migration parity.
- Stdlib phase/drain forms compile through ordinary `.orc` and WCC.
- Name-keyed runtime context recognition and retired adapters are deleted only
  after evidence proves them redundant.
- The Design Delta Drain family can run as typed workflow composition over
  resources and transitions rather than a wrapper over YAML-era state files.

## 27. Summary Recommendation

Accept the generic core and minimal expression surface as one target.

The runtime keeps only what a runtime must guarantee: identity, versions,
allocation, validation, atomic/fail-closed transition commit, idempotency,
resume, provenance, audit, and one small total expression evaluator.

Workflow Lisp gains exactly the surfaces the adapter census should justify:
scalar predicates, integer counting, option/default handling, typed projection,
materialized views, typed transitions, and stdlib contexts over the generic
core.

The reference family proves the payoff: a drain that counts in-language, routes
in-language, commits state through audited transitions, exposes true public
inputs instead of generated paths, and runs without Python scripts that encode
workflow semantics.
