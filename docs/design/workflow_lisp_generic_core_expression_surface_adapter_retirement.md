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
- G2A1 (external P0 prerequisite before counting Design Delta family
  retirement evidence): consume the post-foundation phase-family boundary
  rehabilitation surface for the real `lisp_frontend_design_delta` plan,
  implementation, and work-item routes, so promoted high-level candidates no
  longer depend on public low-level state-path inputs or phase-context helper
  boundaries that fail `workflow_boundary_type_invalid`.
- G2A2a (external P0 prerequisite before shared projection-helper proving
  routes are counted as G2 evidence): consume the post-foundation
  route-compatible structured-control surface for the real shared
  selector/terminal/blocked-recovery helper routes, including the accepted WCC
  `IfExpr` prerequisite or an accepted equivalent lowering, so projection
  replacement does not rely on top-level-only structured `if/else` carriage
  for nested routing logic.
- G2A2b (external P0 prerequisite before shared projection-helper proving
  routes are counted as G2 evidence): consume the post-foundation
  projection-helper boundary and exportability rehabilitation surface for
  shared selector/terminal/blocked-recovery projection helpers and proving
  fixtures, so projection replacement does not depend on helper boundary
  shapes that trip
  `low_level_state_path_in_high_level_module`, field-less routing unions that
  trip `variant_output_without_variant_specific_fields`, or helper export
  shapes that fail `workflow_return_not_exportable` /
  `workflow_signature_mismatch` after accepted structured-control carriage
  exists.
- G2A2c (external P0 prerequisite before the G2 reference-family flip):
  consume the same accepted helper-boundary/private-binding surface on the
  real Design Delta family modules after G2A2a and G2A2b are green, so the
  promoted `drain` -> `work_item` replacement route does not reintroduce
  those diagnostics when the helpers are imported and exercised through the
  actual family compile.
- G3 (P0): generic resource and transition runtime core.
- G4: materialized value views.
- G5: context generalization: `RunCtx`-only runtime bootstrap and type-driven
  private-context classification.
- G5A (P0 prerequisite before counting G6 evidence): imported generic stdlib
  effectful-composition substrate for constrained specialization,
  branch-local proof typing, and transition/view resolution on the ordinary
  import/specialization/typecheck/WCC route.
- G5B (P0 prerequisite before counting broader G6 verification evidence):
  shared verification-baseline rehabilitation for imported generic stdlib
  composition, builtin stdlib routing, and tranche-owned gate separation.
- G5C (P0 prerequisite before counting imported-macro-heavy G6 drain
  evidence): imported stdlib macro payload projection and helper-composition
  substrate for hygienic dotted field access from macro-bound values and
  accepted helper-call carriage in the expression positions those macros need,
  with no compiler-name special case.
- G5D0 (P0 prerequisite before counting G5D or bounded-exhaustion G6 drain
  evidence): shared scalar loop-frame carriage through
  `repeat_until.on_exhausted.outputs`, so direct scalar refs rooted in the
  loop binding survive shared validation, output-bundle validation, and final
  workflow output resolution as ref-backed scalar exhaustion outputs.
- G5D (P0 prerequisite before counting bounded-exhaustion G6 drain
  evidence): imported stdlib `loop/recur` exhaustion projection and post-loop
  terminal carriage for `backlog-drain`-style routes, so typed bounded
  exhaustion does not depend on effectful `:on-exhausted` work.
- G5E (P0 prerequisite before counting dedicated G6 drain runtime-proof
  evidence): dedicated stdlib proving-fixture executable-boundary carriage, so
  imported `std/drain` proving routes can reach validated executable-bundle
  construction on the owned runtime-proof lane without forcing G7
  parent-callable boundary cleanup or weakening lower-level validation.
- G6: stdlib migration of phase/drain forms onto the generic core.
- G7: Design Delta Drain boundary and adapter cleanup.
- G8: evidence-gated deletion of retired ontology tables, retired adapters, and
  raw semantic argv surfaces.

G1 and G3 are the two load-bearing substrate tranches. They may proceed in
parallel after G0. Generic G2 projection-substrate work may proceed after G1,
but Design Delta family retirement evidence inside G2 is not selectable until
G2A1's post-foundation phase-family boundary prerequisite is green for the
same routes. Shared projection-helper proving routes are not selectable as G2
evidence until the same routes have also cleared G2A2a's structured-control
route-compatibility prerequisite and G2A2b's projection-helper
boundary/exportability prerequisite. The real reference-family flip is not
selectable until those same routes have then also cleared G2A2c's
family-route consumption prerequisite. G6 proving routes are not selectable
until G5A has shown that imported generic stdlib helpers can carry
constraint-checked caller-owned shapes through proof-gated `match`, declared
transition/view effects, and ordinary WCC lowering without compiler-name
special cases. Imported-macro-heavy G6 drain routes are not selectable until
G5C has shown that an imported stdlib macro can synthesize branch-local field
projection and downstream helper/call arguments through ordinary macro
expansion, specialization, typecheck, and WCC lowering without degrading
hygienic dotted access or depending on a compiler branch keyed to
`backlog-drain`, `std/drain`, or a workflow-family module name. Bounded-
exhaustion G6 drain routes are not selectable until G5D0 has shown that
direct scalar loop-frame refs may lower through
`repeat_until.on_exhausted.outputs` as validated ref-backed scalar carriage,
and G5D has shown that imported stdlib routes use that substrate with pure
`:on-exhausted` projection and post-loop terminal transition/view work. G6 counted
evidence is not complete until G5B has fixed the broader gate: the shared
suites counted as G6 evidence must run against an explicit builtin stdlib
inventory and must not depend on unfinished later-tranche modules or
unrelated frontend regressions. Dedicated `std/drain` runtime-proof routes are
not selectable until G5E has shown that the lowered imported route can produce
a validated executable bundle on the owned runtime-proof lane without relying
on G7 parent-callable boundary cleanup, `workflow_boundary_type_invalid` as a
public-boundary proxy, or a compiler/validator branch keyed to a stdlib form,
module, or proving-fixture name. G8 is deletion-only and must not be selected
until evidence from G2 through G7 proves every removed path is unused.

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

### 3.5 Verification ownership is under-specified

The broader frontend regression lanes consumed by post-foundation stdlib work
currently mix three different ownership classes:

- tranche-owned imported generic stdlib composition guarantees;
- later-tranche builtin stdlib surfaces such as `std/drain`; and
- unrelated shared regressions in adjacent module/import/workflow-ref routes.

Without an explicit gate contract, a green proving route can still fail final
verification for reasons that the tranche does not own. The next prerequisite
must separate counted G6 evidence from broader informative sweeps and make the
builtin stdlib inventory for those counted suites explicit.

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
- Attribute expressive limits honestly: where a surface is excluded by census
  policy rather than architectural necessity (collection operators, structural
  recursion, terminal self-referential types), the design records the
  architecture-compatible admission path in Deferred Work, so policy gates are
  never mistaken for impossibilities and the language's claim to ordinary
  typed-programming semantics stays credible under scrutiny.

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

### 11.1A External Prerequisites For The Reference-Family Flip

The G2 substrate itself depends on G0 and G1. The Design Delta reference-family
flip inside G2 also depends on one phase-family prerequisite plus a
decomposed projection-helper prerequisite stack owned by the post-foundation
composition design.

G2A1 clears the real `lisp_frontend_design_delta` phase-family high-level
boundaries: the plan, implementation, and work-item routes must already carry
private/runtime context and any retained compatibility paths across generated
boundaries without failing promoted compilation on
`low_level_state_path_in_high_level_module` or generic
`workflow_boundary_type_invalid`.

G2A2a clears the route-compatibility seam for the same shared helper routes.
Shared selector-action, terminal-decision, and blocked-recovery projection
helpers plus their proving fixtures must compile through an accepted
structured-control carriage, including the consumed post-foundation WCC
`IfExpr` prerequisite or an accepted equivalent lowering, rather than relying
on top-level-only structured `if/else`.

G2A2b clears the remaining shared projection-helper boundary and
exportability seam for the same family once G2A2a is green. Shared
selector-action, terminal-decision, and blocked-recovery projection helpers
plus their proving fixtures must then compile through an accepted
helper-boundary/private-binding shape or an accepted equivalent lowering,
without widening G2 and without promoting those helper inputs/outputs to
public high-level boundaries. In particular, the consumed post-foundation
prerequisite must own any remaining contract work needed so that the proving
route and shared helper route do not depend on:

- helper boundaries that expose path-typed selection evidence in a shape that
  trips `low_level_state_path_in_high_level_module`;
- field-less routing unions or equivalent typed decisions rejected solely by
  `variant_output_without_variant_specific_fields`; or
- proving/helper exports that fail only because the accepted helper boundary
  shape is unresolved, producing `workflow_return_not_exportable` or
  `workflow_signature_mismatch`.

G2A2c then consumes that same accepted helper-boundary/private-binding surface
on the real `drain` -> `work_item` replacement route. It owns the case where
the standalone proving helpers are green, but the actual family compile still
fails because imported helper calls, bindings, or route-local boundary shapes
reintroduce the same diagnostic family.

This document does not reopen or duplicate those boundary contracts. It
consumes the post-foundation phase-family and projection-helper
rehabilitation surfaces. If a G2 implementation attempt reaches
`projections.orc` or its proving fixtures and first fails on structured-control
carriage for nested routing, the next selectable work is G2A2a's consumed
post-foundation prerequisite, not a widening of G2. If that carriage is green
and the proving routes then fail on helper boundary/exportability diagnostics,
the next selectable work is G2A2b's consumed post-foundation prerequisite. If
those proving routes are green and the real family replacement route then
fails on the same boundary/exportability class when imported into the promoted
family modules, the next selectable work is G2A2c's consumed post-foundation
prerequisite.

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
- Stop and hand off to G2A1, G2A2a, G2A2b, or G2A2c, whichever prerequisite
  still fails, when the real reference-family replacement route still fails on
  high-level boundary carriage, route-compatible structured-control
  validation, helper/private workflow context transport, family-union
  carriage, or helper exportability.
- Mark adapters `retired` in the census only after the family stops invoking
  them.

### 11.3 Acceptance

- Named projection/classification adapters have in-language replacements.
- Dual-run parity passes before flip.
- The reference family has no command step for selector action projection.
- Reference-family retirement evidence is counted only after the same routes
  clear the consumed post-foundation phase-family boundary prerequisite,
  the structured-control route-compatibility prerequisite, and the
  projection-helper boundary/exportability prerequisite for shared helper
  proving routes, and the family-route consumption prerequisite on the real
  Design Delta modules.
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
- Keep the renderer interface invocable independently of file allocation:
  `(typed value, renderer id, renderer version) -> deterministic bytes` as a
  callable seam, with file allocation layered on top. The candidate
  follow-on target (`workflow_lisp_consumer_side_rendering.md`) renders
  typed values at the prompt-composition and observability seams without
  durable allocation; G4 must not foreclose that by welding rendering to
  path allocation.
- Add `StateLayout` allocation role string `materialized_value_view`
  (design shorthand may say `materialized_view`, but the shipped generated-path
  role string stays `materialized_value_view`).
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

Implementation note: the current checkout has landed the structural classifier,
schema-versioned `context_input_roles` binding metadata, the role-driven
executor lane, `std/context.orc`, and acceptance fixtures for unknown
`ExperimentCtx`, imported `std/context` records, and `RunCtx`-only Drain
construction. The legacy name tables remain in place as labeled compatibility
until G8 deletion evidence is complete.

### 14.5 Normative Spec Deltas

- `RunCtx` is the runtime-owned exception.
- Domain contexts are library records over the generic core.
- Private context classification is structural/type-driven.

## 15. Tranche G6: Stdlib Migration Of Phase/Drain Forms

### 15.1 Contract

`with-phase`, `finalize-selected-item`, and `backlog-drain` become stdlib
`.orc` code over the generic core rather than Python lowering hooks keyed to
domain form names.

### 15.1A Prerequisite: Imported Generic Stdlib Effectful Composition

G6 assumes one compiler/frontend capability that is narrower than generic-core
surface design but broader than any single stdlib form body: imported generic
stdlib helpers must be able to combine caller-owned constrained record/union
types, proof-gated `match`, declared transitions, and `materialize-view`
inside one ordinary imported route.

The required contract is:

- compile-time specialization still follows the accepted rule:
  resolve concrete types, check structural constraints, instantiate a
  monomorphic helper, typecheck that instantiated helper, then lower;
- branch-local field access inside `match` is typed after specialization on
  the instantiated helper, not against unresolved type parameters or
  pre-specialization placeholders;
- declared `deftransition` and view/render references authored in an imported
  stdlib module remain resolvable from specialized helper bodies and from
  macro expansions that target those helpers, without adding a compiler branch
  keyed to a stdlib module or form name; and
- the route preserves the expected error/evidence boundaries:
  structural-shape failures remain compile-time
  `parametric_constraint_unsatisfied`-class failures, while positive routes
  preserve source maps, effect visibility, and runtime erasure of compile-time
  only metadata.

If that combined route is not yet proven, the next selectable work is this
prerequisite rather than widening G6 or forcing the stdlib forms back through
macro-only or compiler-special compatibility paths.

### 15.1B Prerequisite: Shared Verification Baseline And Builtin Stdlib Routing

G6 consumes more than the narrow imported-helper proving fixture. Before its
evidence is counted, the broader regression suites used as G6 acceptance
evidence must run against a coherent builtin/module surface and an explicit
gate definition.

The required contract is:

- every suite counted toward G6 acceptance is named explicitly, with a reason
  it belongs to G6 rather than G7 or a later cleanup tranche;
- counted suites may depend only on builtin stdlib modules and shared frontend
  surfaces that are tranche-owned at that point; unfinished later-tranche
  modules such as `std/drain` remain non-gating until their owning tranche
  lands or a compatibility/baseline stub is promoted into the declared
  inventory;
- unrelated regressions in adjacent shared routes, such as module/workflow-ref
  behavior that does not exercise imported generic stdlib transition/view
  composition, are routed to their owning tranche instead of being counted as
  failed G6 evidence; and
- the counted verification lane still includes at least one broader
  cross-cutting suite beyond the bespoke G5A proving fixture, so G6 evidence is
  not reduced to a single happy-path module.

If that broader verification gate is not yet stabilized, the next selectable
work is this prerequisite rather than widening G6 or declaring G5A incomplete.

Status note: the G5B prerequisite is now landed as the checked-in manifest
`docs/workflow_lisp_g6_verification_gate.json`, loaded by
`orchestrator/workflow_lisp/verification_gate.py` and enforced by
`tests/test_workflow_lisp_verification_gate.py`. The counted lane is explicit,
`std/drain` remains declared `pending`, and G6-owned counted-suite additions
are routed to the G6 gap's `pending_material/` directory instead of being
counted as G5B/G6-prerequisite failures.

### 15.1C Prerequisite: Imported Stdlib Macro Payload Projection And Helper Composition

G6 `backlog-drain`-style stdlib routes assume one additional frontend
capability that is narrower than G5A's generic imported-helper proof and more
specific than G5B's counted-suite gate:

- an imported stdlib macro must be able to introduce or bind branch-local
  values and still preserve hygienic dotted field access from those values
  into downstream workflow-call arguments, record constructors, and variant
  constructors after ordinary expansion;
- if the accepted route uses imported helper procedures instead of direct
  dotted projections in the macro template, those helper invocations must be
  expressible in the expression positions the macro needs without being
  reclassified as unsupported pure operators, and without turning effectful
  helper work into hidden pure semantics;
- the route must remain name-neutral: no compiler branch keyed to
  `backlog-drain`, `std/drain`, a workflow-family module name, or one special
  helper proc is allowed to paper over the limitation; and
- positive routes must preserve source maps, proof/effect visibility, and the
  usual owner-layer failures for bad field access, bad helper signatures, or
  disallowed effect positions.

This prerequisite exists because imported generic helper composition is not by
itself proof that imported stdlib macro bodies can project typed payload
fields or synthesize downstream argument structure in the same route.

If this capability is not yet proven, the next selectable work is this
prerequisite rather than widening G6, forcing `backlog-drain` back through a
compiler-special compatibility lane, or claiming that direct dotted
projection inside imported stdlib macros already works.

### 15.1D Prerequisite: Shared Scalar Loop-Frame Carriage Through `repeat_until.on_exhausted.outputs`

G6 `backlog-drain`-style stdlib routes now consume one narrower prerequisite
before the imported-stdlib exhaustion proof itself: the shared loop substrate
must accept ref-backed scalar loop-frame outputs in
`repeat_until.on_exhausted.outputs` rather than restricting that surface to
scalar literals only.

The required contract is:

- direct scalar field accesses rooted in the loop binding are part of the
  baseline exhaustion surface and may lower as ref-backed scalar exhaustion
  outputs;
- shared validation, validated bundle/output resolution, and final workflow
  output resolution must all accept that ref-backed scalar carriage when the
  referenced loop-frame field is already materialized by the loop state;
- arbitrary computed scalar expressions remain outside this prerequisite and
  still fail closed unless some other accepted surface carries them through the
  loop frame first; and
- the route remains name-neutral and compiles through ordinary typecheck, WCC,
  lowering, shared validation, and executable output resolution without a
  compiler or validator branch keyed to `std/drain`, `backlog-drain`, or a
  proving-fixture module name.

If this capability is not yet proven, the next selectable work is this
prerequisite rather than widening G5D, treating the failure as imported-macro
or post-loop-terminal debt, or weakening the baseline exhaustion contract.

### 15.1E Prerequisite: Imported Stdlib Loop Exhaustion Projection And Post-Loop Terminal Carriage

G6 `backlog-drain`-style stdlib routes assume one additional route contract
that is distinct from G5C's macro/helper payload proof and consumes G5D0's
shared scalar-carriage substrate: bounded typed exhaustion must stay within
the baseline `loop/recur` exhaustion surface
instead of smuggling effectful terminal work into `:on-exhausted`.

The required contract is:

- authored `:on-exhausted` projection remains pure, loop-local, and limited to
  the baseline scalar loop-frame outputs already admitted by G5D0;
- imported stdlib drain routes may use `:on-exhausted` to set a terminal
  decision marker or other scalar loop-frame fields, then construct the typed
  exhaustion variant only after loop exit from those materialized loop-frame
  outputs;
- any effectful exhaustion follow-up such as `resource-transition`,
  `materialize-view`, `command-result`, or other durable terminal side effects
  occurs after the loop has returned its typed result, not inside
  `:on-exhausted`; and
- the route remains name-neutral and compiles through ordinary import,
  macro expansion, specialization, typecheck, and WCC lowering without a
  compiler branch keyed to `loop/recur`, `backlog-drain`, `std/drain`, or a
  workflow-family module name.

Current status note:

- G5D is now landed as bounded prerequisite evidence on the imported stdlib
  proving route exercised by
  `tests/test_workflow_lisp_imported_stdlib_loop_exhaustion_post_loop_terminal.py`.
- The proving route keeps `repeat_until.on_exhausted.outputs` data-only,
  rejects effectful `:on-exhausted` helpers, and performs terminal
  `resource-transition` / `materialize-view` work only after loop result
  binding.
- This evidence satisfies the imported-stdlib post-loop terminal-carriage
  prerequisite only. It does not count as G6 completion, hook redundancy,
  family cleanup, or adapter retirement evidence.

If G5D0 is green and this capability is not yet proven, the next selectable work is this
prerequisite rather than widening G5C, treating a bounded-exhaustion drain
failure as macro-helper-composition debt, or widening G6 around an unresolved
stdlib loop contract.

### 15.1F Prerequisite: Dedicated Stdlib Proving-Fixture Executable-Boundary Carriage

G6 `backlog-drain` runtime-proof work assumes one additional route contract
that is narrower than G7 parent-callable boundary cleanup and later than the
imported-stdlib macro/loop prerequisites above: a dedicated imported
`std/drain` proving fixture must be able to lower into a validated executable
bundle on the owned runtime-proof lane even when that fixture intentionally
retains compatibility-shaped or otherwise non-promoted boundary surfaces for
pairing and parity harnesses.

The required contract is:

- the dedicated runtime-proof lane may skip parent-callable/public-boundary
  promotion obligations, but it must still preserve ordinary type, effect,
  proof, source-map, state-layout, and executable-contract validation;
- validated executable-bundle construction must distinguish public or
  parent-callable boundary rules from generated/private helper boundaries and
  from dedicated proving-fixture runtime-proof boundaries, rather than letting
  `workflow_boundary_type_invalid` or equivalent public-boundary-only checks
  block the owned lane;
- generated/private helper workflows introduced by ordinary imported
  `std/drain` composition must remain name-neutral and executable-bundle-valid
  on that lane, with no compiler or validator branch keyed to `std/drain`,
  `backlog-drain`, or a proving-fixture module name; and
- if the same route still requires G7 parent-callable boundary rehabilitation,
  the next selectable work is this prerequisite rather than widening G6,
  weakening validation, or treating the dedicated proving fixture as
  promotion-ready.

This prerequisite exists because imported stdlib lowering success, macro/helper
proof, and loop-exhaustion proof do not by themselves show that a lowered
dedicated `std/drain` proving route can survive validated executable-bundle
construction on its owned runtime-proof lane.

If this capability is not yet proven, the next selectable work is this
prerequisite rather than widening G6, converting the owned runtime-proof lane
into G7 parent-callable cleanup, or papering over the failure with a
stdlib-name special case.

Current evidence note:

- `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py` is the owned G5E
  proof lane. It proves that the imported `std/drain` fixture can compile on
  the explicit dedicated runtime-proof profile, produce a validated executable
  bundle, preserve source-map and certified command-boundary evidence, and
  retain non-promotable boundary diagnostics as machine-readable metadata.
- The same module separately keeps the shared-callable/public-boundary guard
  lane red on generated structured-match boundary rules, so G5E evidence does
  not count as parent-callable readiness or G7 cleanup.

### 15.2 Tasks

- Consume G5A's imported generic stdlib effectful-composition proof before
  counting G6 evidence.
- Consume G5B's verification-baseline and builtin-stdlib-routing proof before
  counting broader G6 evidence.
- Consume G5C's imported stdlib macro payload-projection and helper-composition
  proof before counting `backlog-drain` or other imported-macro-heavy G6
  drain evidence.
- Consume G5D0's shared scalar loop-frame carriage proof before counting G5D
  or any bounded-exhaustion `backlog-drain` evidence.
- Consume G5D's pure exhaustion-projection and post-loop terminal-carriage
  proof before counting `backlog-drain` or other bounded-exhaustion G6 drain
  evidence.
- Consume G5E's dedicated stdlib proving-fixture executable-boundary proof
  before counting dedicated `std/drain` runtime-proof evidence on the owned
  runtime lane.
- Implement `std/context`, `std/resource`, `std/projection`, and `std/drain`
  modules.
- Express `with-phase` as context construction plus scoped allocation.
- Express `finalize-selected-item` as typed match/projection plus transition.
- Express `backlog-drain` as `loop/recur`, typed selection/result unions, and
  resource transitions.
- Add hook-redundancy evidence before deleting old lowering hooks.

### 15.3 Acceptance

- G5A has already proven one ordinary imported route where constrained generic
  stdlib helpers or their macro expansions successfully combine proof-gated
  `match`, declared transition/view effects, and WCC lowering, and where the
  corresponding negative structural-shape fixture still fails as
  `parametric_constraint_unsatisfied`.
- G5B has established an explicit G6 verification gate, named the builtin
  stdlib inventory that those counted suites may assume, and shown that the
  counted suites pass without relying on unfinished later-tranche modules or
  unrelated shared-route fixes.
- G5C has already proven one ordinary imported route where a stdlib macro can
  either project branch-local payload fields directly or route them through an
  accepted helper-composition path into downstream arguments and typed
  constructors under ordinary expansion/typecheck/WCC lowering, and where the
  corresponding negative fixtures still fail closed for bad field access or
  disallowed expression-position helper usage. The dedicated proof lane is
  `tests/test_workflow_lisp_imported_stdlib_macro_payload_helper_composition.py`,
  which pins the helper-composed `let*` route into downstream workflow-call
  arguments, record constructors, and variant constructors.
- G5D0 counts as satisfied only when focused WCC/schema-2 evidence shows that
  one direct union fixture lowers scalar loop-frame refs into
  `repeat_until.on_exhausted.outputs`, one direct-computed-scalar fixture still
  fails closed, and one scope-owned executable loop lane proves the validated
  bundle preserves ref-backed exhaustion outputs through final workflow output
  resolution.
- G5D broader imported-stdlib evidence remains gated by G5D0 plus its own
  route-specific prerequisites and proof lane; G5D0 is necessary substrate,
  but it is not by itself counted as imported-stdlib or G6 evidence.
- G5E counts as satisfied only when focused evidence shows that one imported
  `std/drain` proving route lowers and then reaches validated
  executable-bundle construction on the owned runtime-proof lane without
  tripping `workflow_boundary_type_invalid` or an equivalent
  public-boundary-only check, while a separate boundary-oriented lane still
  proves that parent-callable/public-boundary validation remains active where
  promotion readiness is actually required.
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
  -> G1 -> G2 substrate
  -> G3 -> G4
post-foundation phase-family boundary rehabilitation
  + post-foundation projection-helper structured-control route compatibility
  -> post-foundation projection-helper boundary/exportability rehabilitation
  -> post-foundation projection-helper family-route consumption
  + G1
  -> G2 reference-family flip
G1 + G3 -> G5
G3 + G4 + G5 -> G5A
G5A -> G5B
G5A + G5B -> G5C
G5A + G5B + G5C -> G5D0
G5A + G5B + G5C + G5D0 -> G5D
G5A + G5B + G5C + G5D -> G5E
G3 + G5 + G5A + G5B + G5C + G5D + G5E -> G6
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
| G5A | imported generic effectful-composition substrate |
| G5B | verification baseline for stdlib migration |
| G5C | imported macro/proc authoring substrate for drain stdlib migration |
| G5D0 | shared scalar exhaustion-output carriage |
| G5D | imported stdlib loop exhaustion and post-loop terminal carriage |
| G5E | dedicated stdlib proving-fixture executable-boundary carriage |
| G6 | imported/std composition and hook retirement |
| G7 | parent-callable family cleanup |
| G8 | post-promotion simplification and deletion |

## 21. Deferred Work

- collection operators and structural recursion: deferred until a census
  entry demands them. The architecture-compatible path, recorded so it is
  not re-derived later: evaluator-level total folds over sealed `List[T]`
  using compile-time function hooks (the existing specialization
  machinery), and — if a family genuinely needs tree-shaped data —
  recursive nominal unions with reference-based contract rendering,
  confined to bundle transport and excluded from flattened public input
  surfaces. Well-foundedness is free: values are eager and immutable, so
  self-referential types admit only finite values;
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
- G2 reference-family retirement evidence also consumes the post-foundation
  phase-family boundary proof surface, the projection-helper
  structured-control route-compatibility proof surface, and the
  projection-helper boundary/exportability proof surface for shared helper
  routes, plus the family-route consumption proof surface for the same
  modules; pure-projection fixtures alone are not enough.
- G3 backend-equivalence transition suite.
- G5 type-driven vs name-driven differential tests before deletion.
- G5A imported-generic stdlib effectful-composition proof.
- G5B shared verification-baseline and builtin-stdlib-routing proof.
- G5C imported stdlib macro payload-projection and helper-composition proof.
- G5D0 shared scalar loop-frame exhaustion-output carriage proof.
- G5D imported stdlib loop exhaustion and post-loop terminal-carriage proof.
- G5E dedicated stdlib proving-fixture executable-boundary proof.
- G6 hook-redundancy evidence.
- G7 family fixture with zero workflow-semantics adapters.
- G8 deletion deltas and grep guards.

### 22.2 Prohibited Evidence

- claiming an adapter retired while a family workflow still invokes it;
- retirement without typed dual-run comparison;
- counting reference-family projection retirement while the same replacement
  route still fails on high-level boundary carriage, projection-helper
  structured-control carriage, or projection-helper
  boundary/exportability diagnostics on either the shared helper proving
  routes or the real family-route consumption path owned by the consumed
  post-foundation prerequisites;
- counting G6 stdlib-migration evidence while the same imported route still
  fails to carry constrained generic specialization through proof-gated
  `match`, transition/view resolution, or ordinary WCC lowering;
- counting `backlog-drain`-class G6 stdlib-migration evidence while the same
  imported macro route still lacks an accepted way to carry hygienic
  branch-local dotted field projection or helper-composed payload arguments
  through ordinary expansion/typecheck/WCC lowering;
- counting `backlog-drain`-class G6 stdlib-migration evidence while the same
  route still lacks G5D0's accepted ref-backed scalar loop-frame carriage
  through `repeat_until.on_exhausted.outputs`;
- counting `backlog-drain`-class G6 stdlib-migration evidence while the same
  imported stdlib route still depends on effectful `:on-exhausted` work or on
  non-baseline exhaustion projection instead of a pure loop-frame marker plus
  post-loop terminal projection;
- counting dedicated `std/drain` runtime-proof or broader G6 evidence while
  the same lowered imported route still fails validated executable-bundle
  construction on `workflow_boundary_type_invalid` or an equivalent
  parent-callable/public-boundary check that the G5E dedicated proving-fixture
  lane is supposed to separate from G7 promotion cleanup;
- counting broader imported-stdlib or G6 evidence solely from the shared
  scalar-carriage proof lane before the remaining route-specific boundary or
  builtin-stdlib prerequisites are green;
- counting G6 stdlib-migration evidence while the broader counted suites still
  depend on unfinished later-tranche builtin modules or on unrelated shared
  regressions that have not been routed to their owning tranche;
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
- G6 evidence is counted only after G5A proves imported generic stdlib helper
  composition with constrained specialization, proof-gated `match`, and
  transition/view resolution on the ordinary route.
- G6 `backlog-drain`-class evidence is counted only after G5C proves that
  imported stdlib macro expansion can carry branch-local payload projection or
  an accepted helper-composition equivalent through ordinary expansion,
  specialization, typecheck, and WCC lowering with no compiler-name special
  case.
- G6 `backlog-drain`-class evidence is counted only after G5D0 proves that
  direct scalar loop-frame refs survive `repeat_until.on_exhausted.outputs`,
  shared validation, and final output resolution as ordinary ref-backed scalar
  exhaustion outputs.
- G6 `backlog-drain`-class evidence is counted only after G5D proves that
  bounded exhaustion on the same imported stdlib route uses only pure
  `loop/recur :on-exhausted` loop-frame projection and performs any terminal
  transition/view work only after the loop returns a typed exhaustion result.
- G6 dedicated `std/drain` runtime-proof evidence is counted only after G5E
  proves that the same lowered imported route can reach validated
  executable-bundle construction on the owned runtime-proof lane without
  converting the work into G7 parent-callable boundary cleanup or adding a
  stdlib-name special case.
- G6 evidence is counted only after G5B defines the broader verification gate,
  makes its builtin stdlib inventory explicit, and removes accidental
  dependence on unfinished later-tranche modules or unrelated shared
  regressions.
- G2 reference-family projection retirement counts only after the same
  replacement routes clear the consumed post-foundation phase-family boundary
  prerequisite, the structured-control route-compatibility prerequisite, and
  the projection-helper boundary/exportability prerequisite on shared helper
  proving routes, and then the family-route consumption prerequisite on the
  real Design Delta family modules.
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
