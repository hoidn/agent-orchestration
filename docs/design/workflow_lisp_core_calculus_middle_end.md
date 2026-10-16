# Workflow Lisp Core Calculus And Compiler Middle-End

Status: accepted architecture; the flat route (defunctionalization into flat
steps and the step runtime that executed them, targets through 2.34) was
retired on 2026-10-13 and executable entries through 2.34 are refused; the
retained middle-end (WCC elaboration, ANF normalization, scope/effect/proof
analysis) feeds the closed program that the evaluated runtime executes at
2.35/2.36 (§§10.1, 11.4, 13.5, 15)
Kind: architecture decision / compiler architecture
Created: 2026-06-09
Updated: 2026-10-15 (flat route retired; evaluated execution is the only route)
Execution scope: the [executor retirement design](workflow_lisp_executor_retirement.md)
and `specs/cli.md` govern executable admission; the
[retirement retrospective](../reports/2026-10-13-flat-route-retirement-retrospective.md)
records which modules were deleted and which were kept. Sections 11.3, the
flat-identity part of 11.4, 12, former §13.4 (dual-compile equivalence),
14.4-14.6 and 17-21 describe the retired flat route and are kept as history.
The historical dual-compile-equivalence anchor remains below; current §13.4
instead owns executable command preparation and single-mode WCC body
preparation (§13.4.2). The selected 2.35 source floor removes exclusive older
source modes after migration; current normalization-stage consumers remain.
Scope: retained typed WCC elaboration, ANF normalization, second-class
join-point control and scope/effect/proof analysis feeding checked closed-program
construction. Defunctionalization into flat steps is retired architecture, not
a current constraint or compatibility backend.

Authority:

- `docs/design/workflow_lisp_frontend_specification.md` remains the umbrella
  Workflow Lisp frontend contract; this document refines its compilation
  pipeline, not its language surface or authority rule.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  records completed migration history; it is not a current tranche selector.
- Normative DSL/runtime behavior remains in `specs/`.
- Shared typed checking and checked-program validation preserve semantic
  authority; the evaluated runtime/memo owns execution and persistence.
- This document does not by itself promote any `.orc` workflow to primary
  surface.
- A behavior described here is implementation-complete only when the listed
  verification evidence passes.

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_unified_frontend_design.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_runtime_closures_boundary.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_executor_retirement.md`
- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
- `docs/reports/2026-10-13-flat-route-retirement-retrospective.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`

<a id="1-purpose"></a>
<a id="2-executive-decision"></a>
<a id="3-relationship-to-the-post-foundation-target"></a>

The original problem, flattening decision and post-foundation delivery ownership are historical. Retained calculus/analysis feeds the checked program; no schema-1/2 flat runtime or resume path remains. See the [preserved record](../reports/documentation-history/workflow_lisp_core_calculus_middle_end-history.md#1-purpose).

<a id="4-authority-and-dependency-direction"></a>
<a id="41-this-document-consumes"></a>
<a id="42-this-document-owns"></a>
<a id="43-this-document-does-not-own"></a>
<a id="5-target-and-prohibited-dependency-directions"></a>
<a id="6-problem"></a>
<a id="7-goals"></a>
<a id="8-non-goals"></a>
<a id="9-architecture-invariants"></a>
<a id="103-elaboration-of-surface-forms"></a>
<a id="113-defunctionalization"></a>
<a id="132-environment-to-state-mapping"></a>
<a id="134-dual-compile-equivalence-policy"></a>
<a id="135-what-the-runtime-sees"></a>
<a id="14-contracts-and-interfaces"></a>
<a id="141-typechecker"></a>
<a id="142-elaborator"></a>
<a id="143-normalizer-and-analyzer"></a>
<a id="144-defunctionalizer"></a>
<a id="145-shared-validation"></a>
<a id="146-projections"></a>
<a id="15-alternatives-considered"></a>
<a id="16-deferred-work"></a>
<a id="17-work-blocked-and-not-blocked"></a>
<a id="18-evidence-and-implementation-boundaries"></a>
<a id="181-required-evidence"></a>
<a id="182-prohibited-evidence"></a>
<a id="19-compatibility-and-migration"></a>
<a id="20-verification-strategy"></a>
<a id="21-declarative-acceptance-scenarios"></a>
<a id="211-nesting-by-construction"></a>
<a id="212-typecheck-owns-the-boundary"></a>
<a id="213-equivalence-gated-route-flip"></a>
<a id="214-resume-schema-safety"></a>
<a id="22-success-criteria"></a>
<a id="23-summary-recommendation"></a>
<a id="12-incremental-migration-tranches"></a>
<a id="121-tranche-m0-characterization-oracle"></a>
<a id="122-tranche-m1-calculus-and-pure-subset"></a>
<a id="123-tranche-m2-straight-line-effects"></a>
<a id="124-tranche-m3-case-and-join-points"></a>
<a id="125-tranche-m4-loops-and-the-full-fixture"></a>
<a id="126-tranche-m5-route-flip-and-lowerer-deletion"></a>

The remaining flat dependency architecture, environment-to-state mapping, rollout/equivalence policy and acceptance inventory are historical. Current calculus/typed analysis/identity/diagnostic rules follow below. See the [preserved record](../reports/documentation-history/workflow_lisp_core_calculus_middle_end-history.md#4-authority-and-dependency-direction).

### Source floor and retained stages

The [2.35 source floor](workflow_lisp_executor_retirement.md#source-floor-235)
retires old-source/import/editor compatibility and source-selectable legacy
lowering routes. The current compiler has one admitted source mode:
`CompilerSession` has no `closed_program` selector, and public compiler/build
requests have no `lowering_route` argument. Exclusive old feature branches and
route exports are removed. Preserve current provider closure/diagnostic validation and the two
real condition-processing stages. Historical route/schema data may be read
only for a named current inspection consumer, without selecting a compiler
route. This supersedes the earlier old-import rationale for retaining modes;
the completed §13.4 behavior and identity requirements remain.

### Target-2.39 procedure ownership

The [frontend lowering contract](workflow_lisp_frontend_specification.md#106-procedure-lowering-policy-resolved)
selects caller-owned inline composition for definitions originating at target
2.39. The frontend selects inline policy before legacy AUTO/private-workflow
classification, including procedure bodies with loops. WCC consumes that resolved
policy and inferred effect summary; authored ceilings do not select lowering.
Existing ordinary `defworkflow`/`call` carries
an intentional runtime boundary. Admitted 2.35–2.38 imported procedure origins retain
AUTO/private-workflow behavior and existing diagnostic validation. This source
version change does not weaken the completed executable body/command contracts
in §13.4, shared typechecking modes, closure validation, or checked-program
source/capture identity. It introduces no second elaborator or runtime.


## Current Ownership And Invariants

The frontend baseline owns language/type/import rules. This component owns
retained WCC elaboration, lexical scope, normalization and proof/effect analysis;
`workflow_lisp/closed/` constructs the checked program and the evaluated runtime
owns execution/memo persistence. Shared catalogs and exact source provenance
remain available to typed imports, diagnostics and LSP. No migration design,
representation carrier or old header selects a flat executor.

- Join points remain second-class, never stored, returned or transported.
- `inject` determines output variant identity; `case` supplies field proof only.
- Binding visibility follows defining scope/dominance and lexical owner identity.
- Effect rows retain their closed vocabulary; normalization cannot invent effects.
- Loop budgets/exhaustion retain their accepted typed contracts.
- Semantic identity is independent of source position; source frames remain exact provenance.
- Checked artifacts/site identity and memo validation own admitted resume;
  schema-1/schema-2 flat identities are retained typed/history metadata only.
- Unsupported executable effects refuse at the owning checked admission boundary;
  no claim of universal totality follows from the old flattening design.

## 10. The Workflow Core Calculus

### 10.1 Constructs

At target 2.35 the implemented compiler converts WCC to a closed program
that retains control and callee bodies instead of flattening them as at
targets through 2.34. The closed body uses `let`, `perform`, `call`, `if`, `case`,
`join`, `jump`, `loop`, `continue`, `done` and `halt`; closed values retain
literals/references, operators, records, variants, projections, lists/maps,
pure conditionals/selections, `block`, runtime `context`/`result_path` and
`list_map`. Callee definitions, concrete types, canonical configuration and
perform sites are retained in the artifact.
The exact variants and typed fields are owned by the
[Phase 2 schema](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#the-closed-programs-form).
Evidence: `orchestrator/workflow_lisp/closed/build.py`, `closed/values.py`,
`orchestrator/contracts/closed_program/check.py` and
`tests/test_workflow_lisp_closed_program_corpus.py`.
The integrated Phase 3 runtime (`orchestrator/workflow/evaluated/`) evaluates
that closed program through the public entries, as owned by
[evaluated execution §8](workflow_lisp_evaluated_execution.md#8-evaluation-and-resume);
a 2.35 entry never enters the flat lowering below. Evidence:
`tests/test_workflow_evaluated_totality.py` and
`tests/test_workflow_evaluated_cli.py`.

WCC is deliberately small. Target construct count is ten; additions require
amending this document. The implemented model
(`orchestrator/workflow_lisp/wcc/model.py`) carries more node kinds than this
table: `if`, `select`, loop `continue`/`done`, `parallel-map`, and payload
carriers for run references, trials and provider groups.

| Construct | Shape | Role |
| --- | --- | --- |
| `atom` | literals, variable refs, record construction, field projection | pure values; never lowered to steps |
| `inject` | `inject Union.Variant {field: atom, ...}` | variant introduction; sole source of output variant identity |
| `let` | `let x : T = <op> in body` | sequencing; in ANF, `<op>` is a single operation or atom |
| `perform` | `perform class.op(atoms) : T ! row` | effectful operation: provider call, command call, adapter call, workflow call, resource transition, projection, view materialization |
| `case` | `case x of Union.V1(binds) -> body1 \| ...` | variant elimination; opens a proof scope per arm; arms must be exhaustive or carry a typed default |
| `join` | `join k(params: T...) = body in scope` | second-class labeled continuation (join point) |
| `jump` | `jump k(atoms)` | transfer to a join point in scope |
| `rec-join` | `join rec k(params, budget: Bound) = body in scope` | bounded recursive join point; the only loop construct |
| `call` | `call f[spec](atoms) : T ! row` | compile-time-resolved procedure call; `f[spec]` is a specialized `defproc`/ProcRef body, inlined or cloned during elaboration |
| `halt` | `halt atom` | terminal workflow/procedure result |

The table names calculus representation, not executable effect admission.
Historical trial/provider-group/transition/view payload carriers do not admit
those effects to evaluated execution. Only checked admitted sites may execute.

Notes:

- There is no lambda, no first-class function, no store. The only "function
  space" is compile-time-resolved `call` plus second-class `join`. This is
  the smallest extension of straight-line code that expresses arbitrary
  branching and bounded iteration while preserving the no-runtime-closures boundary.
- `rec-join` budgets lower to the same exhaustion semantics the DSL's
  `repeat_until` already defines: budget exhaustion produces a typed
  `EXHAUSTED`-class variant routed like any other case, never a crash.
- `perform` operation classes are the closed effect vocabulary. Adding a
  class is a design change here and in the post-foundation effect summaries
  together.

### 10.2 Typing, effects, and proofs

- Every construct carries a type and an effect row. `atom` and `inject` are
  pure. `perform` and `call` carry rows from their declarations. `let`,
  `case`, `join`, and `jump` propagate rows by union.
- `case` arm bodies typecheck with refined arm bindings plus the arm's variant
  proof in metadata. In surface terms, `((BLOCKED blocked) ...)` binds
  `blocked` as the `BLOCKED` payload; field access on the scrutinee outside a
  proving arm remains a type error.
- A branch returning union type `T` must end in `inject T.V {...}`, a `jump`
  to a join point whose parameters carry `T`, a `call` returning `T`, or
  `halt`. The returned `inject` (or the called procedure's returns) decides
  the variant — eliminating F3 by construction.
- `jump` arity and types must match the join point's parameters; join-point
  parameters are how values flow out of branches and around loop iterations,
  replacing ad hoc "branch projection" rules with ordinary binding.
- Effect rows are checked against declared procedure signatures before
  elaboration; elaboration and normalization may reorganize control but may
  not change a program's row.

## 11. The Middle-End Pipeline

### 11.1 ANF normalization

Normalization brings elaborated programs to administrative normal form:

- every `perform` and `call` result is bound by a `let` to a fresh or
  authored name;
- compound arguments are atomized (bound first, then referenced);
- `case` scrutinees are atoms;
- non-tail `case`/`rec-join` results flow through join points rather than
  implicit expression results; and
- normalization preserves types, rows, proofs, and source frames node by
  node.

After ANF, control structure is fully explicit: a program is a tree of
scopes whose leaves are straight-line `let` sequences ending in `jump`,
`inject`-then-`jump`, or `halt`.

### 11.2 Scope, effect, and proof analysis

Over the normalized program the middle-end computes, per scope:

- binding table (name, type, defining construct, source frame);
- dominance: which bindings each reference may legally see;
- live-out sets per join point (which bindings cross into which jumps);
- effect summary (union of rows, per the closed vocabulary);
- active variant proofs; and
- allocation requests (write roots, bundle paths, view paths) attributed to
  the requesting scope and frame.

This analysis is the artifact the post-foundation target calls the
"composition-normalized structured control graph": `scope_id`, parent scope,
entering control node, active proof, loop/call-frame identity, produced and
projected values, declared effects, and requested allocations all fall out of
ANF structure plus this pass.

### 11.4 Identity and resume

At target 2.35 the compiler assigns local perform sites separately from
call frames; source spans remain provenance. Effect identity in the evaluated
runtime is `(site, activation path)`, as owned by
[evaluated execution §6](workflow_lisp_evaluated_execution.md#6-effect-identity).
The closed artifact uses its own checked schema; no flat lowering schema
identifies its effects. A 2.35 run carries no `lowering_schema_version`: its
header selects the evaluated profile (`specs/state.md`), and resume evaluates
the program again from its entry against the memo instead of restoring a
position in the scopes below. Evidence: `orchestrator/contracts/closed_program/sites.py`,
`tests/test_workflow_lisp_closed_program_sites.py` and, for the runtime,
`tests/test_workflow_evaluated_public_identity.py`.

## 13. Design Details

### 13.1 WCC node contract

Every node carries:

```text
node_id
construct kind
type
effect_row
scope_id
source_frame_stack          ; authored form, macro frames, import frames,
                            ; specialization frames
proof_context               ; active variant proofs
allocation_requests         ; StateLayout semantic requests, if any
```

Join points additionally carry:

```text
join_name (hygienic, owner-chain qualified)
parameters (name, type)
recursive? and budget, for rec-join
live_in / live_out binding sets (filled by analysis)
```

<a id="132-retained-executable-wcc-closure-target"></a>
### 13.2 Retained executable WCC closure

Retained admitted executable forms cross the WCC-to-closed boundary as
structured typed values and completed callable requests. Source-aware
preparation owns expression elaboration, ANF and capture recipes; direct
translation consumes the completed graph without executable frontend source.
The frontend and evaluated designs own source admission, target numbers,
artifact schemas and execution-mode defaults. This boundary changes none of
those contracts. Implementation evidence and remaining independent lanes live
in the [simplification plan](../plans/2026-10-15-orc-simplification-roadmap-extension.md#task-2--close-the-retained-executable-wcc-boundary).

#### One preparation direction

```text
checked source + resolved imports/specializations
  -> source-aware WCC preparation and ANF
  -> complete typed WCC bodies and existing prepared callable requests
  -> direct closed translation, sites, canonicalization
  -> independent source-free artifact checker
```

Preparation owns all expression elaboration, lexical capture materialization
and ANF. It completes the selected entry and every reachable specialized
definition before their WCC-to-closed translation. The translator consumes
resolved typed operands; it never reconstructs a frontend expression, calls
the frontend elaborator, normalizes a freshly reconstructed body or infers a
source child's type. The boundary is a compiler phase, not an assertion that
every helper physically under `closed/` is already a backend helper.

Existing `CallableRequest`/workflow preparation records carry mandatory
`prepared_body`/`prepared_children` facts for retained execution. Missing
preparation refuses; `closed/build.py` has no lazy callee elaboration fallback.
The existing command-scope preparation owns its neutral and annotated passes;
their equality check remains mandatory without another pass. Initial
workflow/procedure elaboration belongs to these preparation owners.
There is no second typed IR, serialized WCC format, alternate executable
backend or new prepared-program service.

The existing preparation traversal also owns specialized loop-effect
cardinality checks: following an inline callee for that check may elaborate
source, so it must finish before emission. Keep the same defining catalogs,
cycle detection and located cardinality diagnostics. Selected-callable source
refusals likewise run during preparation; later call-occurrence inventories
use retained declaration identities rather than inspecting source again.

Source spans, expansion stacks, nominal type declarations, frozen child
capsules and original definition identities may remain for their existing
diagnostic, import and key contracts. A source object is not executable merely
because it is reachable through metadata. Conversely, placing an operand in a
field marked nonserializable does not exempt it: any expression read to decide
a value, capture, argument, condition or effect during translation is an
executable dependency and must be replaced by its prepared facts.

#### Minimal values and owners

The existing value union includes four structured internal value shapes;
these add no control construct or public syntax form. Every shape carries
`WccNodeMetadata`, exact result type and provenance. Fields below are semantic
edges unless identified as lexical/proof facts.

| Source family | Prepared WCC shape | Direct closed form |
| --- | --- | --- |
| `ListExpr` | `WccList(metadata, items: tuple[WccValue, ...])` | Existing `list`; recursively translate prepared items |
| A value-local normalized body, including expansion-owned pure `let*` | `WccBlock(metadata, body: WccBody)` | Translate body in a copied lexical environment with the halt-unwrapping/`block` rule |
| Accepted named `ProviderBundlePathExpr` | `WccResultPath(metadata, source: WccNameAtom)` | Existing `result_path`; source binding identity and exact bundle path type are retained facts |
| Pure `ListMapExpr` | `WccListMap(metadata, source: WccValue, binder_name, binder_type_ref, body: WccBody, body_metadata: WccNodeMetadata, binding_label, binding_identity)` | Existing `list_map`; source is outside the binder and body is inside it |

Other families use the existing nodes:

- A union variant tag is a `WccLiteralAtom` whose type is the resolved
  `DiscriminantTypeRef`. Retain `owner_union`, applied generic owner and exact
  permitted variants. Neither the payload's `UnionTypeRef` nor `String` is a
  substitute. Generated relpath seeds are literals with their resolved nominal
  `PathTypeRef`, literal path and existing provenance.
- A loop-state seed is a `WccRecordAtom` with ordered typed fields and its
  existing compiler-owned state type. A loop-state update uses the existing
  `WccPureOp` with internal tag `loop-state-update`, base first and overrides
  in source order. ANF keeps this operation atomic as its former carrier was;
  ordinary `record-update` remains non-atomic even on the same state type.
  Both tags emit the existing `record_update` payload with unchanged metadata
  identities. Preparation selects the tag from the expression family, never
  from type-name spelling, provenance or proof metadata. The extra internal
  tag preserves the ANF distinction without a new node, metadata flag, public operator or artifact schema.
- Rooted path join and compiler nonempty-list head use `WccPureOp` with their
  typed operands and dedicated direct-translation cases. Their internal
  operation tags are not new public pure operators. Path join retains the
  resolved path descriptor and one `String` child; head retains the exact
  element type, list source type, compiler-owned proof and existing
  `list_nonempty_invariant_broken` diagnostic. The translator emits the
  existing checked payload shapes rather than introducing runtime operations.

`WccBlock` retains value-local scope: list children with local bindings or
ANF temporaries become closed blocks. Elaborate and normalize each
child in its original local scope during preparation, then retain either its
halt value or a block according to the existing closed representation. Do not
hoist those local prefixes around the containing list. Expansion-owned pure
`let*` uses the same structured block value.

For lists, map sources, path children and state fields, source order and the
current nesting of local value blocks are preserved. A block executes once
where its value is demanded; a `WccSelect` arm remains lazy and only its own
prefix executes. A map source executes once, and its body once per element in
order. Preserve the existing unconditional closed `block` wrapper around a
map body, including a body containing only `halt`; the value-block
halt-unwrapping rule does not apply there. Retain `body_metadata` from the
original body expression's provenance and resolved result item type during
preparation; emit the wrapper's provenance from this static fact, not an
executable child. Keep the normalized body's own metadata unchanged: its
first binding can have a different span. This requires one metadata field,
not another block node or a wrapper flag. `WccSelectArm.prefix` is a sequential
scope: each prefix value and the
terminal value are visited once; its retained `WccLet.body` links are not a
second path. ANF may recurse inside a block or map body during preparation but
must not lift work across these boundaries.

The source-aware producer retains bundle-path admission facts using the
existing target guard before making `WccResultPath`; unsupported forms keep
their existing located refusal. The translator must still reject malformed
WCC facts as compiler defects rather than reconstruct source to repair them.

#### Resolved facts and generated facts

Typechecking owns source expression types, proof contexts and resolved
declaration identities. Carry those facts on existing typed expression nodes
or their existing typed owner. List checking retains an ordered
`item_type_refs` tuple on `ListExpr`, excluded from source semantic identity,
and specialization carries those facts forward. Do not create a parallel
expression graph or recover all child types from the parent's type.

Specialization substitutes concrete type arguments and preserves nominal
declaration ownership. A copied type fact is valid only for that specialized
expression and its lexical environment. Preserve existing `resolved_type`,
map item types, path types, loop field types and bound-parameter types where
they remain exact; regenerate invalidated facts at specialization, not in the
closed translator. Imported admitted definitions use their retained owner
and original type environment, not the entry module's spelling of a type.

New ANF references, let-bound intermediates, map binders and loop-state
constructors get types where they are created. A generated name takes its
producer's result type; `WccLet.bound_type_ref` is that result, while the let's
body metadata describes the continuation. A list constructor's result is
`List[T]`; its children carry their own resolved types. A map binder gets the
source item type and the body has the result item type. A tag keeps its
discriminant proof and a path keeps its nominal root contract. Removing
duplicate source inference never removes independent checking of these
claimed facts.

#### Captures and bound procedure arguments

WCC preparation owns the creation region of each `bind-proc` value. Reuse
existing binding identities, specialization capture routes and creation-owner
keys; never key semantics only by a reused source name or runtime value. The
completed operand on a call is a typed WCC value or a reference to a typed
creation binding. Compile-time procedure/workflow references remain resolved
references, not runtime closures.

The source-facing part of computed-capture preparation runs in the existing
callable preparation phase. Each `ComputedCaptureRequest` retains a typed
`prepared_value: WccValue`, its source aliases and insertion alias. Preparation
resolves free-name aliases and retains existing materialization at the same
creation region, after all required sources dominate it and before its first
use. Keep existing alias order, runtime evaluation counts and canonical
generated binding allocation. An already materialized capture is computed once
per creation, including a creation in a lazy arm or map body; it must not move
to call time or outside that branch/iteration.

The [evaluated capture contract](workflow_lisp_evaluated_execution.md#4-the-closed-program)
requires evaluation once at the binding's lexical scope before forwarding.
An unmaterialized computed-list capture forwarded to repeated calls is a
known defect: its additions are re-evaluated per call. Explicit materialization
computes the list once. The migration preserves this observed multiplicity;
it does not establish the required once-only semantics for that defective
case. Repair requires a separate behavior and artifact-compatibility
disposition, recorded in the simplification plan.

For already closed bound arguments, prepare their literal/operator/block
value with an empty runtime environment and retain the resolved formal type.
`_reference_facts` and `_callee_creation_argument` translate that prepared
value directly. For captured arguments, retain the selected binding identity
and prepared capture route. Retain exact nested ProcRef formal paths and
forwarded capture ownership; a direct and a reference call of the same bound
value retain the same creation owner and existing materialization, while
distinct creations remain distinct. No source expression left in
`bound_proc_source` or `source_binding` may supply missing executable facts after preparation; source identity/provenance alone
may remain.

WCC substitution and capture analysis traverse structured values and respect
block, select-arm, map and loop binders. Retained executable `WccIf` uses its
typed `condition` and branch proof contexts; `condition_shape` is `None`. Pure
conditionals in admitted imported definitions also prepare structured values.
`wcc/historical.py` retains reverse substitution for opaque resource-transition
values encountered during provider-region refusal preparation. No WCC
condition-classification projection is produced. Tests inspect the actual
typed condition and branch behavior.
The preparation equality guard must continue comparing the typed condition
and all executable operands; this change does not weaken that guard.

For `WccRecordAtom`, differing `type_name` strings are redundant only when
each side's `resolved_type` and `metadata.type_ref` are record types, and
`type_name == resolved_type.name == metadata.type_ref.name` locally.
In that side's owning program,
`resolved_type` and `metadata.type_ref` must have both equal unprojected
canonical descriptors and equal existing owner-aware key-type projections.
The first preserves concrete RunRef producers, including phantom arguments;
the second preserves retained signatures. Only then omit the cross-side name
string comparison; keep the existing comparisons of metadata, resolved types
and ordered field operands. Equal name strings retain their existing handling.
This adds a local consistency check, not a name-prefix exception or a new
type-identity rule.

#### Effect payload operands

`WccPerform.operation_payload` also contains executable edges. Extending only
`positional_args` and `keyword_args` cannot establish closure. Keep the
existing per-effect payload mappings; their explicit edge contract is:

| Admitted owner | Additional executable fields | Static facts retained separately |
| --- | --- | --- |
| Command (`closed/effects.py`) | `adapter_inputs[*][1]`; `argv_transport[*].parts[*].value` for every `slot` part | Adapter name, input/document presence and order, transport slot selector, literal template parts, return guidance and command declaration |
| Provider and agent turn (`closed/effects.py`, `closed/agent_effects.py`) | Every prepared prompt fill value; `model`, `effort`, `timeout_sec`, `delivery` when present; `prompt_dependencies.rows[*].value` | Resolved prompt slot facts, dependency role/order/position/instruction, return guidance, provider/agent origin identities |
| Agent allocation | No extra payload operands; policies remain `keyword_args` | Resolved provider identity |
| Admitted run reference | No extra payload operands; dynamic inputs remain `keyword_args` | Validated `WccRunRefPayload`/`WccRunRefWorkflowPayload`, descriptors, policy and frozen child-source ownership |
| Workflow call | No extra payload operands; arguments remain `keyword_args` | Resolved callable/preparation identity and existing configuration facts |

Preparation retains a mapping under the existing
`prompt_application` key containing template text and ordered fill rows with
`name`, slot kind, exact `type_ref`, `value: WccValue`, selected renderer,
output role and placeholder ordinals. Derive those static fields from the
resolved declaration at the source-aware producer; preserve existing prompt
identity facts in their current identity owner. `closed/effects.py` consumes
these rows directly, with no `PromptApplicationExpr`/`PromptFill` import or
frontend expression access. This is an internal prepared payload; the closed
prompt representation is unchanged.

The payload walker dispatches by admitted effect kind and known payload field,
then follows the listed WCC operands recursively, including input-slot values
used for command-root routing/provenance. It validates known static fields
instead of descending into declarations as executable code. Unsupported
context/session/materialization payloads retain their existing admission
refusals. Unknown payload kinds, unexpected fields or raw expressions in an
operand position fail closure; they are never silently treated as metadata.
ANF, substitution, capture/demand scans and preparation equality must cover
these same operands while preserving current ordering and block boundaries.
Payload traversal is inspection, not permission to evaluate a duplicated
transport descriptor or hoist its value again. These rules apply to occurrences
inside payloads and ordinary value positions.

#### Semantic boundary and independent checks

The explicit semantic-child inventory in
`closed/command_templates.py::_wcc_semantic_children` covers list items, block
bodies, result-path sources, map sources/bodies and case/select arms. The
closure check also visits prepared capture/bound-argument values. Case-arm `command_scope` values are executable
operands in the arm's binder scope. ANF, substitution, scope, demand/capture
analysis and preparation equality preserve the same binder boundaries and
per-effect payload edges.

`closed/preparation_check.py::assert_closed_preparation` checks the completed
entry and reachable request graph before body emission. Every request must
have its body, child table and capture recipes. It rejects opaque/raw operands,
unknown executable kinds or fields, and missing or extraneous call occurrences.
The prepared child table must exactly cover the callable inventory; emission
must then consume that inventory exactly once. This is closure/inventory
validation, not a duplicate typechecker.

Instantiated captures may use the existing closed wire subset `name`, `field`,
`record`, `lit` and `context`. `_closed_capture_value` uses the artifact
checker's existing `_VALUE_KEYS` and recursively checks executable operands;
`context` is restricted to `run-id`. Typed `lit.v` contains JSON data, so a
mapping inside that literal is data rather than another executable node.
Missing required operands and unknown kinds/fields fail before emission.

Source spans, nominal declarations and frozen child capsules are metadata,
not executable children; each admitted child entry has its own preparation
boundary. `WccOpaqueFrontendValue` remains in the shared union for resource-
transition refusal, but cannot cross an admitted executable edge. Static call/import checks
supplement semantic closure; global grep-zero or removal of a Python union
member is not its criterion.

The independent checker under `contracts/closed_program/` remains source-free.
It checks descriptor/operand agreement, binding scope, capture routes, calls,
site bijections and output contracts from the artifact alone. It may reuse
data representations and canonical descriptor rules, but neither trusts a
WCC validation verdict nor consults frontend source or elaborator state.
Negative tests mutate valid artifacts, including nested child and capture
types, and require rejection on readback.

<a id="finite-implementation-cuts-and-compatibility-evidence"></a>
#### Artifact identity and compatibility

The [simplification plan](../plans/2026-10-15-orc-simplification-roadmap-extension.md#task-2--close-the-retained-executable-wcc-boundary)
owns the completed implementation cuts and their verification evidence.
Source-mode retirement has its own finite consumer disposition. Current
source compilation uses the sole admitted closed behavior; closure does not
introduce a selector or change retained normalization-stage semantics.

Preserve canonical closed trees, digests, definition/capture keys, perform
sites, call frames, diagnostics and target guards for existing accepted
programs at the same target with identity inputs held fixed. Preserve authored
labels and existing generated-name allocation; WCC wrappers do not enter
persisted identity. Compare representative
pre/post canonical artifacts as well as sites: a semantic-equivalence test
alone does not prove resumable identity. An unavoidable artifact change with
those inputs held fixed needs the state/versioning owner's explicit
compatibility decision before it can replace this preservation contract.

Run-ref artifacts embed a compiler/runtime identity that hashes package bytes;
production edits can therefore change that input. Preserve authentic pre/post
artifacts and report their pin differences as mismatches. A separate internal
compilation control may supply both compilers the same
`VerifiedCompilerRuntimeIdentity`, computed from one retained physical package
fixture and the same interpreter/version/schema inputs. Compare its complete
artifact bytes, including pins, without normalization. A passing control proves
byte equality for those fixed inputs, not authentic-package byte equality or
cross-package resume compatibility. Normal identity computation and admission
refusals remain unchanged; no public override is added. This follows the
[existing identity-evidence contract](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#global-constraints).

Primary existing regression owners are
`test_workflow_lisp_closed_program_{elaboration,build,names,check,sites,artifact}.py`,
the WCC/ANF and conditional/hygiene owners, imported/generic procedure tests,
`test_workflow_evaluated_totality.py` and public evaluated identity/resume tests.
Use actual same-target fixtures, including admitted 2.35+ entries consuming
current-target typed imports. A structural test freezes completed preparation,
disables frontend elaboration/ANF/reverse-conversion entrypoints and translates
it successfully; negative cases inject an opaque/raw child separately into a
list, capture, prompt fill, dependency, policy operand, command input and
transport slot, and also reject an unknown payload field. Source
removal alone is insufficient because typed frontend objects may still exist
in memory.

Provider-region reverse reconstruction remains isolated in `wcc/historical.py`
for the retained opaque `ResourceTransitionExpr` refusal path. WCC condition
classification has no surviving producer. Resource transitions retain their
admission refusal. Admitted imported pure `IfExpr` is structured
when prepared for execution. None of these dispositions admits an excluded
effect or permits executable source re-entry.

### 13.3 Diagnostics contract

All language-boundary rejection happens at or before typecheck:

- a feature the calculus cannot express is a surface/typecheck diagnostic
  naming the restriction (there are intentionally few: first-class
  procedure values, unbounded recursion, effects outside the closed
  vocabulary);
- elaboration, normalization and checked-program construction failures on
  typechecked programs are compiler defects by definition and must say so in
  their error text, with node provenance; and
- shared-validation failures on generic-route output are likewise compiler
  defects unless the workflow violates a contract the typechecker does not
  own (path safety against the live filesystem, for example).

In the current checkout an internal exception raised after typecheck by
elaboration, normalization or closed-program construction is reported as one
`compiler_defect` diagnostic (exit 2). It says that the program passed
typecheck, names the stage, and points at the authored form being handled; the
diagnostic keeps the exception as its `cause` (no CLI flag prints the
traceback). An `AssertionError` raised outside the orchestrator package is not
converted (`compiler_defect_boundary` in `orchestrator/workflow_lisp/diagnostics.py`,
applied in `orchestrator/workflow_lisp/closed/build.py`). Two internal checks
have codes of their own: `compiler_defect_hoisted_binding_rename` and
`compiler_defect_constructor_type_dropped`; `compiler_defect_loop_control_value`
and the replay-index code `pure_result_replay_unavailable` were retired with
the flat route. Located diagnostics raised under other codes, such as
`workflow_return_not_exportable` and
`workflow_signature_mismatch`, keep their codes and do not say so.

<a id="134-executable-only-command-preparation-target"></a>
### 13.4 Executable-only command preparation

`closed/command_templates.py::elaborate_command_scopes` is a dedicated
executable entry using the single-mode WCC body preparator. `ControlFacts` is
constructed in production by `closed/build.py::_command_wcc_body` and carries
no execution-mode flag. Shared typing consumes the sole admitted closed-source
facts; it exposes no false-source compatibility mode.

Command binding and procedure-control analysis uses exact binding facts,
callee-local signature types, the callee's defining/import-owner catalogs and
return types, and declared private/inline boundary behavior. Missing owner
facts are an internal error; caller types and fabricated empty catalogs are
not fallbacks. Private procedure outputs use their declared leaf boundaries;
there is no flattened historical output alternative in this family.

The specialized loop-effect scan's
`wcc/analysis.py::_normalized_inline_procedure_wcc_body` uses supplied resolved
procedures/type environments and explicit closed elaboration. Its context has
no `closed_program` flag or false-mode fallback. Existing cycle detection,
cardinality checks and context data retain their owners. This source-aware
scan runs during preparation; §13.2 forbids source elaboration during direct
translation.

Current module/import/LSP processing uses the shared admitted compiler.
An imported 2.35+ typed module supplies its original nominal/source owner;
pre-floor modules refuse before catalog publication. The command preparator's
neutral and annotated passes remain distinct facts. Source origins 2.35–2.38
retain their declared/default lowering and exact-effect rules; target 2.39
has its separately gated authoring contract. Command preparation itself
changes no persisted identity or effect admission.

The command-control/scope/capture/transport and closed names/elaboration tests
cover real typed owners, capture shadowing, private/inline scopes and transport,
specialized-loop cardinality, admitted imported-owner views, negative unknown
operations and retained LSP/CLI behavior. Same-target artifacts and public
compile/run/resume controls verify the boundary with the rest of preparation.
The source floor also removes exclusive old-source modes;
§13.4.2 owns the single-mode body-preparation boundary.

#### 13.4.1 Mode-independent type-fact inference

`wcc/elaborate.py::_infer_expr_type` and `binding_type_for_elaboration` infer
facts without an execution-mode parameter. They preserve capture-source type
precedence, lexical environments, resolved child facts, failures and return
types. The typecheck and later condition-preparation stages retain distinct
semantic consumers; this helper pair needs no mode forwarding or replacement context.

Command-capture shadowing, direct WCC inference, primitive agreement and the
affected command/elaboration tests cover these facts alongside the artifact
and public lifecycle controls above. The separate
`result_guidance.py::_infer_expr_type` is a different function family.

#### 13.4.2 WCC body specialization and historical-consumer boundary

`wcc/elaborate.py::elaborate_typed_workflow_body` is the single executable
body-preparation entry. It and `prepare_elaboration_call_types` have no mode
parameter; `WccIdentityFactory` carries no `closed_program` field or child-scope
propagation. Builder, command-preparation, specialized-loop and provider-member
recursion callers use this same entry. There is no `elaborate_typed_workflow`
convenience function/export, copied pass or historical body-generation route.

The retained source-analysis contract is the shared typed compiler and its
catalogs/provenance. The [frontend baseline](workflow_lisp_frontend_specification.md)
and [LSP contract](workflow_lisp_language_server.md#shared-read-only-build-core-and-imported-bundles)
retain admitted typed analysis independently of WCC body construction.
Historical schema metadata remains data for named readers, not a route
selector; admitted typed imports keep their original nominal/source owners.
Both command-preparation passes, capture recipes, cycle/cardinality
checks and exact source/command-owner validation remain mandatory. The command
validator checks those facts without a mode argument. Calls from this WCC owner
to shared typing use the sole admitted source semantics.

Provider-group closure and validation remain live refusal consumers.
`close_wcc_provider_supervision_members`, the peer-group forwarder and
`_inline_provider_procedure_call` prepare members through the same executable
entry. Eligibility checks, capture substitution, member traversal order and
validation preserve source-level diagnostics and which error wins. The final
builder refusal of supervision and peer groups does not make this earlier
work unobservable or admit execution of either group kind.

Compare complete ordered public diagnostic records, including code, source
span, form path, expansion stack, phase, data and cause type/message where
present. A generic earlier `closed_program_gap` cannot replace member-specific
diagnostics. Existing compiler defects are observed compatibility limits,
not desired diagnostics or permission to repair them within mode removal.
Raw internal tracebacks preserve evidence; changing package paths, source
lines and traceback formatting is distinct from changing authored diagnostics
or their causes.

The shared WCC union still admits opaque resource-transition values so
provider-region substitution and source-located refusal can operate.
`wcc/historical.py` retains their reverse helper; it does not feed admitted
closed translation. Closure-helper retirement requires proof that its refusal
consumers are gone. Shared substitution, capture, type, ANF and identity
helpers retain their live callers. `wcc/route.py` and source-selectable route
exports are removed; retained schema fields are validated data for their
current readers. Internal mode
removal changes no public syntax, target, artifact schema or effect admission.
Artifact compatibility remains subject to the compiler-package identity
boundary in §13.2.

Workflow return boundaries, private-procedure eligibility, union-call
compatibility, run-reference placement and typed capture/enum facts use the
current closed-source behavior directly. In `conditionals.py`, the typecheck-proofs caller uses ordinary
condition normalization even for evaluated typing; later
`prepare_closed_condition_expr` restores retained inputs and applies the
closed loop-order, nested-loop and bound-capture rules. Removing those real
distinctions requires a separate equivalent normalization/admission design,
not a default flip or retirement of old WCC shapes.


## Current Integration And Verification Boundary

Typed elaboration, normalization, scope/effect/proof summaries and source lineage
must agree with the checked artifact consumed by the runtime. Internal failures
after typecheck use the compiler-defect boundary described above; public admission
refusals retain their specific diagnostics. Test current composition through the
public checked compile/run/resume and totality owners named by
[evaluated execution](workflow_lisp_evaluated_execution.md). Historical dual-flat
oracles and old-schema continuation tests preserve evidence for their original
claim; they are not current route prerequisites or a legacy recovery floor.
