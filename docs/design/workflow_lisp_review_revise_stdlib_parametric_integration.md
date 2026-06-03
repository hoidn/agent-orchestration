# Workflow Lisp Review/Revise Stdlib Integration With Refactor Preconditions and Parametric Constraints

Status: draft design
Kind: incremental architecture / stdlib migration spec / consuming design for parametric Workflow Lisp
Created: 2026-06-03
Scope: `review-revise-loop` first; later reusable review/revise/fix orchestration forms with the same shape.

Related docs:

- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/plans/2026-05-23-workflow-lisp-refactoring-backlog.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `specs/dsl.md`

## 1. Purpose

This document specifies the incremental architecture for moving
`review-revise-loop` from a compiler-special Workflow Lisp form into an
ordinary `.orc` standard-library component.

This document is self-contained with respect to the prerequisite refactoring. It
incorporates the recommended behavior-preserving refactor preflight, the generic
`.orc` expansion Track A, and the minimal parametric type-system work needed
before `review-revise-loop` can become ordinary stdlib code.

This document does not replace the refactor architecture. The refactor
architecture remains the primary source for behavior-preserving frontend
refactor boundaries: module ownership, traversal, context objects, lowering
splits, registries, cleanup, and verification. That architecture says the
refactor is not a language redesign and must preserve authored `.orc` semantics,
generated workflow behavior, runtime execution semantics, diagnostics, source
maps, effect visibility, and validation behavior.

This document also does not turn the general refactoring backlog into feature
work. The backlog explicitly says missing language features and missing shared
contracts should remain tracked by design-gap work, while the backlog itself is
about reducing maintenance cost without changing `.orc` language behavior or
weakening diagnostics, source provenance, type safety, effect visibility, or
lowering correctness.

The review/revise-loop migration therefore has three distinct classes of work:

Class A: behavior-preserving refactor preflight
: Make the frontend safe to extend without semantic drift.

Class B: generic `.orc` expansion substrate
: Make imported `.orc` definitions expand, typecheck, preserve effects/source
  maps, specialize compile-time refs, and lower through the ordinary path.

Class C: missing language/type-system features
: Add only the minimal generic loop, ProcRef, and structural-parametric support
  required to express `review-revise-loop` as stdlib code.

`review-revise-loop` itself should not be implemented as stdlib until Class A
and the relevant Class B substrate have landed.

## 2. Executive Decision

Implement this migration in the following order:

1. Add this integration document as the target architecture.
2. Behavior-preserving refactor preflight:
   - fix concrete hazards;
   - add characterization coverage;
   - decide the lowering package/facade boundary;
   - introduce shared expression traversal coverage;
   - optionally add `TypecheckContext` and coherent lowering helper extraction
     where needed.
3. Generic `.orc` expansion Track A:
   - `FormKind` / `FormSpec` registry;
   - reserved macro names derived from the registry;
   - registry-routed elaboration;
   - architectural denylist tests;
   - tiny imported `.orc` expansion;
   - imported-source source maps;
   - imported effect visibility;
   - generic compile-time ProcRef specialization.
4. Minimal parametric feature substrate:
   - `loop/recur` typed exhaustion projection;
   - `:forall` and monomorphic helper specialization;
   - structural record/union constraints;
   - ProcRef signature constraints;
   - variant-proof preservation through `match`.
5. `std/phase.orc` `review-revise-loop`:
   - caller-owned completed/input/result types;
   - compile-time review/fix ProcRefs;
   - ordinary `loop/recur` + `match` + projection lowering;
   - evidence identity carried by state/inputs.
6. Remove or quarantine the old promoted-path compiler special case:
   - `ReviewReviseLoopExpr`;
   - `_elaborate_review_revise_loop`;
   - review-loop-specific typecheck branches;
   - review-loop-specific lowerer branches;
   - reserved macro treatment that blocks stdlib ownership.
7. Continue broader cleanup backlog after the semantic route is stable.

The generic `.orc` expansion refactor already defines a two-track migration:
Track A is the architectural substrate, and Track B is review-loop compatibility.
Track A includes the form registry, reserved-name derivation, registry-routed
elaboration, denylist tests, generic imported `.orc` expansion, source maps,
imported-effect visibility, and generic ProcRef specialization; that plan
explicitly says Track A must land first or Track B risks becoming another
hand-coded migration path.

## 3. Problem

`review-revise-loop` currently behaves like a high-level reusable workflow
abstraction, but the promoted path still depends on compiler logic that knows
the form by name.

That creates five design problems.

First, the compiler contains review-loop-specific semantic knowledge that should
belong either in `.orc` stdlib code or in generic type-system machinery. The
structural-constraints design identifies the current issue directly:
`review-revise-loop` accepts a caller-owned `:returns` union, but the compiler
currently needs to know that the union contains terminal variants such as
`APPROVED`, `BLOCKED`, and `EXHAUSTED`; that structural validation is encoded
directly in Python for one form.

Second, the stdlib lowering contract says the default implementation path for
high-level library forms is ordinary `.orc` stdlib code compiled through shared
effectful composition. It also states that `review-revise-loop` is not accepted
as a compiler-special primitive for the key-workflow migration tranche, and that
its parity path is ordinary stdlib/generic composition emitting executable
surfaces such as `repeat_until`, structured provider results, `match`,
projection/materialization, source maps, and resume-safe loop state.

Third, `review-revise-loop` is only conditionally feasible as ordinary stdlib
code with the current architecture. The stdlib lowering design says the proof
route is a stdlib `defproc` over compile-time ProcRef review/fix hooks plus
generic `loop/recur` exhaustion projection, while the existing
`ReviewReviseLoopExpr` lowerer remains a shape reference, not acceptance
evidence for ordinary stdlib composition.

Fourth, the frontend has accumulated pass-level complexity that makes new forms
easy to miss in some walkers or passes. The refactor architecture names
repeated expression-tree walkers, module-global compiler state, private helper
imports, duplicated registries, and large pass modules as debt patterns; it
warns that the risk is semantic drift, where a future form is parsed and
typechecked but missed by purity checks, extern discovery, ProcRef
specialization, source-map generation, or lowering analysis.

Fifth, if the generic expansion refactor is skipped, a supposed "stdlib"
implementation can become a renamed compiler special case: a macro that emits a
Python-authored AST, a typechecker branch keyed to `review-revise-loop`, or a
lowerer branch that still constructs the review/fix loop directly. The generic
expansion refactor frames the decisive question as whether the implementation is
a generic `.orc` expansion/specialization mechanism usable by arbitrary `.orc`,
or a review-loop-specific compiler branch with a new name.

The desired architecture is:

```text
review-revise-loop
  authored/imported as std/phase.orc code
  reached through the generic form registry/import path
  checked through generic structural constraints
  specialized into a monomorphic helper/private workflow
  lowered through ordinary Core AST and DSL surfaces
  validated by shared validation
  executed by the runtime as ordinary workflow control
```

The prohibited architecture is:

```text
review-revise-loop
  recognized by Python as a magic form
  typechecked by review-loop-specific code
  lowered by a hand-built ReviewReviseLoopExpr branch
  treated by runtime or shared validation as a special concept
```

## 4. Authority And Dependency Direction

### 4.1 This Document Is A Consuming Architecture

This document consumes, but does not redefine:

- behavior-preserving refactor architecture;
- low-hanging refactor execution plan;
- generic `.orc` expansion Track A;
- compile-time parametric specialization;
- structural parametric constraints;
- macro surface contract;
- ProcRef semantics;
- state layout;
- DSL `repeat_until` semantics;
- migration parity policy.

The ownership split is:

`workflow_lisp_refactor_architecture.md`
: Owns behavior-preserving refactor boundaries, traversal/context/lowering/
  registry cleanup principles, module-boundary direction, and preservation
  invariants.

`2026-05-23-workflow-lisp-refactoring-backlog.md`
: Owns the general cleanup backlog, maintenance-cost reduction goals, and the
  separation between refactor work and missing feature work.

`2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
: Owns the first behavior-preserving implementation tranche, concrete hazards,
  characterization coverage, lowering package/facade decision, shared
  expression traversal utility, lowering extern/type helper extraction, and
  package-root narrowing.

`2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
: Owns Track A generic `.orc` expansion substrate, form registry and extension
  boundary, denylist tests for old review-loop special casing, imported `.orc`
  expansion/source-map/effect visibility, and generic ProcRef specialization
  substrate.

`workflow_lisp_compile_time_parametric_specialization.md`
: Owns `:forall` type parameters, call-site type resolution, concrete
  monomorphic helper/private-workflow specialization, specialization identity,
  runtime erasure of type parameters, compile-time-only ProcRef treatment, and
  source-map obligations for generated specializations.

`workflow_lisp_structural_parametric_constraints.md`
: Owns `has-field` constraints, `has-union-variant` constraints,
  `has-shared-union-field` constraints, `is-record` / `is-union` constraints,
  ProcRef signature constraints, variant-proof preservation, and diagnostics for
  unsatisfied constraints.

This document owns the review/revise stdlib migration sequence, which refactor
work is prerequisite versus follow-up cleanup, the `std/phase.orc`
`review-revise-loop` API shape, approve/revise/blocked/exhausted routing
semantics, evidence-authority rules, loop/recur exhaustion projection
requirement, fixture and promotion matrix, and removal of `ReviewReviseLoopExpr`
from the promoted path.

### 4.2 Target Dependency Direction

Target dependency direction:

```text
public syntax
  -> optional thin macro
  -> imported std/phase.orc definition
  -> generic macro/procedure expansion
  -> generic typechecking and structural constraints
  -> compile-time specialization
  -> ordinary Core AST
  -> shared validation
  -> executable workflow DSL
```

Prohibited dependency direction:

```text
public syntax
  -> parser recognizes review-revise-loop
  -> ReviewReviseLoopExpr
  -> review-loop-specific typechecker branch
  -> review-loop-specific lowerer hand-builds match/loop/projection tree
  -> executable workflow DSL
```

## 5. Goals

- Make `review-revise-loop` ordinary imported stdlib code rather than a compiler
  primitive.
- Do the minimum behavior-preserving refactor preflight before adding new generic
  expansion or type-system behavior.
- Land generic `.orc` expansion Track A before review-loop compatibility work.
- Preserve review decisions as workflow-control authority.
- Preserve typed state and validated artifacts as semantic authority.
- Allow caller-specific records and result unions without compiler branches keyed
  to review-loop names.
- Keep ProcRef, provider refs, prompt refs, type parameters, and
  helper-generation details compile-time-only.
- Preserve provider and command effects after specialization.
- Preserve source-map provenance for authored code, imported stdlib code,
  generated helpers, generated paths, and selected ProcRef bodies.
- Make loop exhaustion an explicit typed terminal result, not hidden failed
  control flow.
- Keep runtime execution Lisp-agnostic: the runtime executes generated DSL
  surfaces, not a special review-loop primitive.
- Provide an incremental path that can coexist with the current legacy bridge
  until parity fixtures pass.

## 6. Non-Goals

This design does not add:

- runtime closures;
- runtime procedure values;
- runtime type values;
- runtime multiple dispatch;
- provider refs in runtime state;
- prompt refs in runtime state;
- implicit structural duck typing at workflow runtime;
- report parsing as semantic state;
- pointer-file choreography as semantic state;
- hidden command adapters for review/revise routing;
- broad style cleanup unrelated to this migration.

This design also does not require every backlog item to finish before
`review-revise-loop` moves to stdlib. The backlog is broader than this migration
and explicitly warns against using refactor cleanup to implement missing language
features.

## 7. Architecture Invariants

A promoted stdlib review loop must satisfy these invariants:

- Structured bundles and typed artifacts are authority.
- Reports, debug YAML, stdout, pointer files, and source maps are views unless a
  specific contract says otherwise.
- Review decisions route workflow control.
- `REVISE` is not completion.
- `EXHAUSTED` is explicit typed non-completion.
- Evidence identities are carried by state or inputs.
- Review-provider output cannot redirect carried evidence identity.
- All generated effects are visible.
- All generated statements and paths are source-mapped.
- All generated paths are deterministic and collision-safe.
- No runtime ProcRef, provider ref, prompt ref, type parameter, closure, or type
  object exists.
- The runtime executes generic DSL surfaces, not Lisp-specific review-loop
  behavior.
- Shared validation remains authoritative after lowering.

## 8. Refactor Prerequisite Model

The refactor work has three tiers.

### 8.1 Hard Preflight Before Track A

The following refactors are hard prerequisites before relying on generic `.orc`
expansion Track A:

- P0.1 Fix concrete review hazards.
- P0.2 Add characterization coverage for affected pass boundaries.
- P0.3 Decide the lowering package/facade boundary before extracting Track A
  helpers.
- P0.4 Introduce shared expression traversal coverage and migrate low-risk
  walkers.
- P0.5 Keep maintained Python frontend modules at or below 2,000 physical lines
  per file, or split them before adding new Track A/type-system behavior.

Rationale: these items reduce the chance that a new generic expansion path is
parsed, elaborated, or typechecked correctly while being missed by purity checks,
extern discovery, ProcRef discovery, source maps, or lowering analysis.
The module-size cap is a refactor-safety rule, not a language semantic rule:
large compiler modules are harder to characterize, review, and extend without
accidentally adding another hidden special case.

### 8.2 Strongly Recommended Before Structural Parametric Work

The following refactors are strongly recommended before implementing structural
constraints and parametric specialization:

- R1 Introduce `TypecheckContext` or equivalent explicit context object.
- R2 Extract coherent lowering extern-discovery helpers.
- R3 Extract lowering-time type helpers.
- R4 Clarify source-map/build-artifact ownership.

These are not all hard gates for the first Track A fixtures, but they become
increasingly important once generic type parameters, variant proof, specialized
helpers, and imported ProcRef bodies are introduced.

### 8.3 Follow-Up Cleanup After Semantic Migration

The following backlog items should continue after the stdlib review-loop route
is stable:

- F1 Diagnostic builder consolidation.
- F2 Pass-local validation helper consolidation.
- F3 Package-root API narrowing.
- F4 Fixture-only code movement.
- F5 Migration scaffolding audit.
- F6 Module dependency audit.

Do not block review-loop stdlib migration on broad cleanup unless a specific
item affects the migration's correctness.

## 9. Hard Preflight: Behavior-Preserving Refactor Tranche

### 9.1 Fix Concrete Hazards

Before adding a generic expansion substrate, fix the concrete hazards called out
by the low-hanging refactor plan:

- remove shadowed duplicate lowering helpers;
- fix missing private-workflow `VariantCaseTypeRef` import or equivalent type
  reference;
- make `defun` purity checking fail closed for unknown `ExprNode` containers;
- guard macro hygiene shape assumptions so malformed macro output preserves
  provenance.

Acceptance:

- `python -m compileall orchestrator/workflow_lisp`
- `pytest tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lowering.py -q`
- `git diff --check`

Any pre-existing failures must be recorded with exact command output before
continuing.

### 9.2 Add Characterization Coverage

Add focused behavior assertions for pass boundaries that Track A and review-loop
stdlib migration depend on:

- provider-result structured outputs;
- command-result structured outputs;
- match variant proof and narrowing;
- loop/recur lowering;
- phase stdlib forms;
- resource/drain stdlib forms;
- workflow calls and workflow references;
- source-map origin serialization;
- validation-error remapping.

Acceptance:

- tests assert important generated boundaries exist;
- tests assert output contract kind where relevant;
- tests assert source-map origin exists for at least one generated step per
  family;
- tests assert workflow call targets remain present inside lowered
  loop/control-flow bodies;
- tests do not snapshot entire lowered workflows unless unavoidable.

### 9.3 Decide Lowering Package/Facade Boundary

Decide before extracting Track A helpers whether
`orchestrator/workflow_lisp/lowering.py` becomes a `lowering/` package facade or
remains a file with sibling helper modules for this tranche.

The low-hanging plan explicitly says Python cannot have both
`orchestrator/workflow_lisp/lowering.py` and an
`orchestrator/workflow_lisp/lowering/` package with the same import path, so this
structure decision should happen before helper extraction. It recommends
converting `lowering.py` into a package facade if the pure move is low-risk,
with sibling helper modules as the fallback only if package conversion causes
import instability.

Acceptance:

- lowering import inventory is recorded;
- package facade or sibling fallback is chosen;
- `orchestrator.workflow_lisp.lowering` remains the public import facade;
- maintained Python modules under `orchestrator/workflow_lisp/` touched by this
  migration are at or below 2,000 physical lines, excluding generated files,
  fixtures, and temporary migration evidence;
- any currently larger touched module is split behind the existing public import
  facade before new generic expansion or type-system behavior is added there;
- no behavior changes occur in the pure move;
- focused lowering tests pass.

### 9.4 Introduce Shared Expression Traversal

Introduce a small shared traversal utility before adding more expression forms or
expansion outputs.

Required helper surface:

```python
def iter_child_exprs(expr: ExprNode) -> tuple[ExprNode, ...]:
    ...


def walk_expr(expr: ExprNode) -> Iterator[ExprNode]:
    ...
```

Required coverage:

- `LetStarExpr`
- `MatchExpr`
- `IfExpr`
- `RecordExpr`
- `ProviderResultExpr`
- `CommandResultExpr`
- `ProduceOneOfExpr`
- `ResumeOrStartExpr`
- `ResourceTransitionExpr`
- `BacklogDrainExpr`
- review-loop legacy node, if still present
- leaf expressions

The low-hanging plan calls expression traversal duplicated across multiple files
the highest-leverage refactor after immediate hazards, and requires a
coverage-style assertion that every current `ExprNode` union member is either
covered by traversal or explicitly classified as leaf/specialized.

Use traversal first in low-risk locations:

- function dependency scanning;
- provider/prompt extern collection;
- ProcRef specialization discovery where current environment handling is
  preserved;
- workflow extern collection if mechanical;
- let-proc escape/value-use checks only if scoped behavior remains obvious.

Do not force scoped walkers into the helper if doing so hides important scope
changes.

## 10. Track A: Generic `.orc` Expansion Substrate

Track A begins only after the hard preflight is complete.

### 10.1 Form Registry

Add a formal registry that classifies every compiler-known head.

Illustrative shape:

```python
class FormKind(Enum):
    CORE_SPECIAL = "core_special"
    CORE_EFFECT = "core_effect"
    STDLIB_EXTENSION = "stdlib_extension"
    TEMP_COMPILER_INTRINSIC = "temp_compiler_intrinsic"


@dataclass(frozen=True)
class FormSpec:
    name: str
    kind: FormKind
    owner: str
    introduced_in: str
    remove_by: str | None = None
    allowed_in_macro_definition: bool = True
    elaborator: str | None = None
    rationale: str = ""
```

Initial classification should be explicit and reviewable:

CORE_SPECIAL:
: `record`, `let*`, `if`, `match`, `call`, `proc-ref`, `workflow-ref`,
  `loop/recur`, `continue`, `done`.

CORE_EFFECT:
: `provider-result`, `command-result`, and other runtime bridge forms that
  directly lower to workflow execution effects.

STDLIB_EXTENSION:
: `review-revise-loop`.

TEMP_COMPILER_INTRINSIC:
: `run-provider-phase`, `produce-one-of`, `resume-or-start`,
  `resource-transition`, `finalize-selected-item`, `backlog-drain`, and other
  high-level forms still needing compiler help until ordinary `.orc` routes
  exist.

The generic expansion refactor gives the same registry direction: classify heads
as core language forms, core effect bridges, standard-library extensions, or
temporary compiler intrinsics scheduled for deletion; derive macro reserved
names from that registry or check parallel lists against it.

### 10.2 Registry-Routed Elaboration

Replace ad hoc head dispatch with registry dispatch.

Intermediate dispatch shape:

```python
spec = FORM_REGISTRY.get(head.resolved_name)

if spec is None:
    return elaborate_callable_or_name_reference(...)

if spec.kind is FormKind.STDLIB_EXTENSION:
    return elaborate_stdlib_extension_reference(...)

if spec.kind is FormKind.TEMP_COMPILER_INTRINSIC:
    warn_or_require_allowlisted_intrinsic(spec, datum)

return spec.elaborator(...)
```

The registry is not a new semantic engine. It is an extension boundary that
forces every compiler-known head to declare why the compiler knows it.

For `review-revise-loop`, the promoted route must be:

```text
head resolves as stdlib extension or imported binding
  -> imported .orc expansion/call
  -> ordinary typecheck/lowering
```

Not:

```text
head == "review-revise-loop"
  -> ReviewReviseLoopExpr
  -> review-loop-specific typecheck/lowering
```

### 10.3 Architectural Denylist Tests

Add tests that fail if promoted review-loop compilation uses semantic
review-loop compiler artifacts.

Denylisted artifacts:

- `ReviewReviseLoopExpr`
- `_elaborate_review_revise_loop`
- `__review-revise-loop__`
- `_lower_review_revise_loop`
- `_validate_review_loop_result_contract`
- typechecker branch keyed directly to `review-revise-loop`
- lowerer branch keyed directly to `review-revise-loop`
- compiler visitor logic keyed directly to `review-revise-loop`
- reserved macro treatment that prevents imported stdlib ownership

The generic expansion refactor explicitly lists these regression guards and says
the old branch may remain temporarily only as a shape oracle for golden fixtures,
not as the accepted semantic route.

### 10.4 Temporary Syntax Compatibility Shim

A temporary compatibility shim is allowed if public `(review-revise-loop ...)`
syntax cannot immediately become an imported macro because the current macro
system reserves the name.

Acceptable:

```python
def expand_review_revise_loop_compat(form: SyntaxList) -> SyntaxList:
    return SyntaxList(
        [introduced_identifier("std.phase/review-revise-loop"), ...],
        span=form.span,
        expansion_stack=push_expansion_frame(...),
    )
```

Unacceptable:

```python
def expand_review_revise_loop_compat(form):
    return ReviewReviseLoopExpr(...)


def lower_review_revise_loop(expr):
    return hand_built_match_loop_tree(...)
```

The compatibility shim must have a registry `remove_by` condition. Once imported
`.orc` macros can own the public name cleanly, remove the shim and unreserve
`review-revise-loop`.

### 10.5 Generic Expansion Metadata

If the compiler needs an internal expansion carrier, it must be generic.

Allowed carrier shape:

```python
@dataclass
class OrcExpansion:
    parsed_expansion_ast: ExprNode
    authored_call_site: SourceSpan
    imported_definition_source: SourceSpan
    specialization_bindings: Mapping[str, Type | ProcRef]
    generated_allocator_identity: GeneratedAllocatorIdentity
    expansion_stack: ExpansionStack
    source_map_frames: list[SourceMapFrame]
```

Disallowed carrier fields:

- `review_provider`
- `fix_provider`
- `review_prompt`
- `fix_prompt`
- `checks_report`
- `progress_report`
- `APPROVED` / `BLOCKED` / `EXHAUSTED` special schema fields

Preferred lifecycle:

```text
Syntax / frontend AST from imported .orc
  -> expansion engine clones/substitutes with ExpansionFrame metadata
  -> returns ordinary ExprNode
  -> normal typecheck
  -> normal lowering
```

Avoid a durable semantic `ExpandedOrcExpr` variant that downstream typechecking
or lowering must dispatch on. A lasting wrapper can recreate the same
special-case smell one level later.

### 10.6 Generic Imported `.orc` Inline-Procedure Expansion

Build a generic imported `.orc` expansion/specialization operation.

Illustrative operation:

```python
def expand_inline_procedure_call(
    call: ProcedureCallExpr,
    callee: TypedProcedureDef,
    ctx: ExpansionContext,
) -> ExprNode:
    ...
```

Required behavior:

- clone an already parsed/elaborated `.orc` body;
- substitute value parameters hygienically;
- substitute compile-time ProcRef parameters as resolved procedure refs;
- allocate generated names and paths through a shared allocator;
- push source-map frames for caller call site and imported definition;
- return ordinary `ExprNode`;
- re-typecheck the expanded expression through the normal typechecker;
- preserve all provider/command effects introduced by the imported definition.

`review-revise-loop` becomes one caller of this mechanism, not the reason the
mechanism is review-loop-shaped.

### 10.7 Imported Expansion Effect Visibility

Imported `.orc` expansion must preserve effects.

A stdlib helper that invokes `provider-result`, `command-result`, or a ProcRef
whose body invokes provider/command effects must expose those effects to:

typechecking, Semantic IR, shared validation, runtime planning, migration
evidence, and debug/explain output.

Invalid implementation:

```text
macro expands to opaque generated step
effects are known only to the macro implementation
validation cannot see provider/command effects until runtime
```

Valid implementation:

```text
imported definition expands to ordinary provider-result/command-result/call nodes
typechecker and lowering see those nodes normally
effect summaries include imported and selected ProcRef bodies
```

### 10.8 Imported Expansion Source Maps

Source maps must identify:

- authored caller call site;
- imported stdlib definition;
- macro expansion frame, if any;
- specialization arguments;
- generated helper/private workflow;
- generated loop frame;
- generated match arms;
- generated materialization/projection steps;
- generated paths and bundle roots;
- selected ProcRef definitions.

A generated executable node without imported-definition provenance is invalid for
promoted review-loop fixtures.

### 10.9 Track A Fixture Ladder

Track A must be proven before implementing stdlib `review-revise-loop`.

Required fixture order:

1. Static denylist for semantic use of review-loop-specific compiler artifacts.
2. Tiny imported `.orc` procedure with source maps for call site and imported
   definition.
3. Imported `.orc` procedure that emits provider or command effects visible to
   validation.
4. Imported `.orc` procedure that matches a union and uses ordinary variant
   proof.
5. Imported `.orc` procedure that uses the accepted loop form and terminal
   exhaustion projection.
6. Imported `.orc` procedure accepting compile-time ProcRef hooks without
   runtime closures.
7. Evidence-identity negative test.
8. No public hidden write-root input test.
9. Public `review-revise-loop` parity suite through the generic route.

### 10.10 Track A Acceptance Checks

Track A passes when:

- `FormKind` / `FormSpec` registry exists.
- `review-revise-loop` is classified as `STDLIB_EXTENSION` or
  `TEMP_COMPILER_INTRINSIC` scheduled for deletion, not `CORE_SPECIAL`.
- Reserved macro names derive from or are checked against the registry.
- Expression elaboration routes through the registry.
- Denylist tests fail on `ReviewReviseLoopExpr` use in promoted route.
- A tiny imported `.orc` procedure expands and lowers through ordinary
  typecheck/lowering.
- Imported expansion source maps include caller and imported definition.
- Imported expansion effects are visible.
- Imported ProcRef specialization works without runtime closures.
- No review-loop-specific compiler artifact is needed for the generic fixture
  ladder.

Only after Track A passes should the review-loop-specific stdlib implementation
begin.

## 11. Parametric Specialization Dependency

This document depends on compile-time parametric specialization.

The required specialization pipeline is:

```text
generic .orc definition
  -> infer concrete call-site types
  -> check explicit shape/trait constraints
  -> instantiate monomorphic helper/private workflow
  -> typecheck the instantiated AST
  -> lower ordinary Core AST
```

For this design, specialization must provide:

- `:forall` type parameters;
- concrete call-site type resolution;
- compile-time ProcRef resolution;
- monomorphic helper/private-workflow generation;
- deterministic specialization identity;
- source-map frames for generated helpers;
- runtime erasure of type parameters and ProcRefs.

Executable runtime state must not contain:

- unresolved type parameters;
- procedure type values;
- ProcRef values;
- provider refs;
- prompt refs;
- runtime method choices;
- closure environments.

## 12. Structural Constraint Dependency

This document depends on structural parametric constraints.

The first useful constraint set is deliberately small:

```text
T has-field name Type
T has-union-variant VARIANT
T has-union-variant VARIANT (field Type ...)
T has-shared-union-field name Type
T is-record
T is-union
P ProcRef[(A B) -> R]
```

For this design, constraints must support:

- caller-owned `CompletedT` record;
- caller-owned `InputsT` record;
- caller-owned `ResultT` union;
- `ResultT` terminal variants `APPROVED`, `BLOCKED`, `EXHAUSTED`;
- review ProcRef signature;
- fix ProcRef signature;
- variant-proof preservation through `match`;
- field projection only under proof;
- constraint failure before lowering.

Constraint checking must happen before the specialized helper is accepted.
Lowering receives only concrete monomorphic definitions.

## 13. Target Compilation Architecture

The target architecture is:

```text
caller .orc
  imports std/phase.orc
  defines caller-owned review and fix procedures
  calls review-revise-loop with proc-ref hooks
        |
        v
form registry / import resolver
  classifies review-revise-loop as stdlib extension or imported binding
  refuses promoted compiler-special route
        |
        v
frontend import resolver
  loads stdlib .orc source
  records imported-definition provenance
        |
        v
macro expansion, if any
  expands only to grammar-accepted .orc
  does not own hidden provider/command effects
  does not own runtime semantics
        |
        v
generic expansion / specialization substrate
  clones imported .orc body
  substitutes value parameters
  substitutes compile-time ProcRef parameters
  allocates generated names/paths through shared allocator
  records source-map frames
        |
        v
generic type checker
  resolves concrete CompletedT / InputsT / ResultT
  checks structural record/union/variant constraints
  checks ProcRef signatures and effects
  preserves variant proof through match
        |
        v
monomorphic helper/private workflow
  contains no type parameters
  contains no runtime ProcRefs
        |
        v
ordinary typecheck and lowering
  loop/recur
  match
  provider-result / command-result
  record/union construction
  materialization/projection
        |
        v
YAML-shaped Core DSL workflow
        |
        v
shared validation / Semantic IR / Executable IR
        |
        v
runtime
  executes repeat_until, provider steps, command steps, match, output contracts
```

The compiler sees the generated helper as ordinary monomorphic Workflow Lisp. The
runtime sees ordinary DSL.

## 14. Stdlib Surface

### 14.1 First Tranche: Concrete Review Decision And Findings, Generic Completed/Input/Result

The first stable implementation should avoid over-generalizing every part of the
loop. It can keep review decision and findings as stdlib-owned concrete types
while allowing caller-owned completed/input records and caller-owned terminal
result unions.

Illustrative stdlib types:

```lisp
(defrecord ReviewFinding
  ((severity String)
   (message String)
   (location OptionalString)))

(defrecord ReviewFindings
  ((summary String)
   (items ReviewFindingList)))

(defunion ReviewDecision
  (APPROVE
    (review_report ReviewReportPath)
    (findings ReviewFindings))

  (REVISE
    (review_report ReviewReportPath)
    (findings ReviewFindings))

  (BLOCKED
    (review_report ReviewReportPath)
    (findings ReviewFindings)
    (blocker_class String)
    (reason String)))
```

Illustrative generic stdlib definition:

```lisp
(defproc review-revise-loop
  :forall (CompletedT InputsT ResultT)
  :where
    ((CompletedT is-record)
     (InputsT is-record)

     (ResultT has-union-variant APPROVED
       (completed CompletedT)
       (review_report ReviewReportPath)
       (findings ReviewFindings))

     (ResultT has-union-variant BLOCKED
       (completed CompletedT)
       (review_report ReviewReportPath)
       (findings ReviewFindings)
       (blocker_class String)
       (reason String))

     (ResultT has-union-variant EXHAUSTED
       (completed CompletedT)
       (last_review_report ReviewReportPath)
       (findings ReviewFindings)
       (reason String))

     (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
     (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT]))

  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
   (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])
   (max_iterations Int))

  -> ResultT

  ...)
```

The spelling is illustrative. The semantic contract is normative:

- `CompletedT` and `InputsT` are caller-owned records.
- `ResultT` is a caller-owned union constrained structurally.
- `review` and `fix` are compile-time ProcRefs.
- `review` returns a typed `ReviewDecision`.
- `fix` consumes findings from `REVISE` and returns the next `CompletedT`.
- `APPROVE` and `BLOCKED` are terminal.
- `REVISE` invokes fix and continues.
- `EXHAUSTED` is typed terminal non-completion.

### 14.2 Extended Model: Generic Decision And Findings

A later version may parameterize decision and findings types too:

```lisp
(defproc review-revise-loop
  :forall (CompletedT InputsT DecisionT FindingsT ResultT)
  :where
    ((CompletedT is-record)
     (InputsT is-record)

     (DecisionT has-union-variant APPROVE
       (review_report ReviewReportPath)
       (findings FindingsT))

     (DecisionT has-union-variant REVISE
       (review_report ReviewReportPath)
       (findings FindingsT))

     (DecisionT has-union-variant BLOCKED
       (review_report ReviewReportPath)
       (findings FindingsT)
       (blocker_class String)
       (reason String))

     (ResultT has-union-variant APPROVED
       (completed CompletedT)
       (review_report ReviewReportPath)
       (findings FindingsT))

     (ResultT has-union-variant BLOCKED
       (completed CompletedT)
       (review_report ReviewReportPath)
       (findings FindingsT)
       (blocker_class String)
       (reason String))

     (ResultT has-union-variant EXHAUSTED
       (completed CompletedT)
       (last_review_report ReviewReportPath)
       (findings FindingsT)
       (reason String))

     (review ProcRef[(CompletedT InputsT) -> DecisionT])
     (fix ProcRef[(CompletedT InputsT FindingsT) -> CompletedT]))

  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> DecisionT])
   (fix ProcRef[(CompletedT InputsT FindingsT) -> CompletedT])
   (max_iterations Int))

  -> ResultT

  ...)
```

This should not block the first migration tranche unless a concrete caller
requires custom findings.

### 14.3 Bridge Model: Terminal-Constructor ProcRefs

If direct generic construction of caller-owned result-union variants is not
ready, the stdlib loop may accept terminal-constructor ProcRefs as a bridge:

```lisp
(defproc review-revise-loop
  :forall (CompletedT InputsT ResultT)
  :where
    ((CompletedT is-record)
     (InputsT is-record)
     (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
     (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])
     (on-approved ProcRef[(CompletedT ReviewReportPath ReviewFindings) -> ResultT])
     (on-blocked ProcRef[(CompletedT ReviewReportPath ReviewFindings String String) -> ResultT])
     (on-exhausted ProcRef[(CompletedT ReviewReportPath ReviewFindings String) -> ResultT]))

  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
   (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])
   (on-approved ProcRef[(CompletedT ReviewReportPath ReviewFindings) -> ResultT])
   (on-blocked ProcRef[(CompletedT ReviewReportPath ReviewFindings String String) -> ResultT])
   (on-exhausted ProcRef[(CompletedT ReviewReportPath ReviewFindings String) -> ResultT])
   (max_iterations Int))

  -> ResultT

  ...)
```

This bridge is acceptable only if constructor hooks are compile-time ProcRefs,
constructor hook effects are visible, constructor hook bodies are ordinary
`.orc`, constructor hook return type is concrete after specialization,
constructor hooks do not introduce runtime procedure values, source maps include
constructor hook bodies, and the bridge is documented as temporary or as an
ergonomic wrapper.

Preferred long-term model: `review-revise-loop` directly constructs `ResultT`
variants justified by structural constraints.

Allowed bridge model: `review-revise-loop` delegates terminal construction to
compile-time ProcRefs while direct generic union construction matures.

Disallowed model: Python compiler branch constructs `ResultT` variants because
it knows `review-revise-loop` by name.

## 15. Review/Revise Semantic Contract

The stdlib loop has four routes.

### 15.1 APPROVE

```text
review(completed, inputs) returns APPROVE
  -> loop exits
  -> terminal result is ResultT.APPROVED
  -> completed state is the current completed value
  -> review_report and findings come from the approving review decision
```

### 15.2 REVISE

```text
review(completed, inputs) returns REVISE
  -> fix(completed, inputs, findings) runs
  -> completed becomes fix result
  -> loop continues
  -> REVISE is not completion
```

### 15.3 BLOCKED

```text
review(completed, inputs) returns BLOCKED
  -> loop exits
  -> terminal result is ResultT.BLOCKED
  -> completed state is the current completed value
  -> review_report, findings, blocker_class, and reason come from the blocking review decision
```

### 15.4 EXHAUSTED

```text
loop reaches max_iterations without APPROVE or BLOCKED
  -> loop exits through explicit exhaustion projection
  -> terminal result is ResultT.EXHAUSTED
  -> completed state is the latest completed value
  -> last_review_report and findings come from the last completed review frame
  -> reason is a deterministic workflow-owned value such as "max_iterations_exhausted"
```

Exhaustion is not hidden control-flow failure. It is a typed non-completion
result.

## 16. Loop State Model

The generated monomorphic helper should lower to an explicit loop-frame state. A
conceptual frame is:

```lisp
(defrecord ReviewLoopFrame
  ((completed CompletedT)
   (decision_status ReviewDecisionStatus)
   (latest_review_report ReviewReportPath)
   (latest_findings ReviewFindings)
   (latest_blocker_class OptionalString)
   (latest_reason OptionalString)
   (iteration Int)))
```

After specialization, `CompletedT` is concrete. No type parameter appears in
lowered Core AST, Semantic IR, executable state, output contracts, provider
payloads, or command payloads.

The frame is semantic state. It must not carry ProcRef values, provider refs,
prompt refs, type parameters, runtime closure environments, unvalidated report
text as structured findings, or evidence identities invented by review output.

## 17. Lowering Contract

A specialized stdlib review loop should lower to existing DSL surfaces.

Representative generated shape:

```text
generated/private review-loop helper
  repeat_until ReviewLoop:
    outputs:
      completed
      decision_status
      latest_review_report
      latest_findings
      latest_blocker_class
      latest_reason

    condition:
      self.outputs.decision_status in ["APPROVE", "BLOCKED"]

    max_iterations:
      max_iterations

    on_exhausted.outputs:
      decision_status = "EXHAUSTED"
      latest_reason = "max_iterations_exhausted"

    steps:
      ReviewOnce:
        call specialized review ProcRef
        produces ReviewDecision

      RouteReviewDecision:
        match ReviewDecision.discriminant
          APPROVE:
            materialize completed unchanged
            materialize latest_review_report
            materialize latest_findings
            set decision_status = "APPROVE"

          REVISE:
            call specialized fix ProcRef
            materialize completed = fix result
            materialize latest_review_report
            materialize latest_findings
            set decision_status = "REVISE"

          BLOCKED:
            materialize completed unchanged
            materialize latest_review_report
            materialize latest_findings
            materialize latest_blocker_class
            materialize latest_reason
            set decision_status = "BLOCKED"

  FinalReviewLoopProjection:
    match ReviewLoop.outputs.decision_status
      APPROVE:
        construct ResultT.APPROVED
      BLOCKED:
        construct ResultT.BLOCKED
      EXHAUSTED:
        construct ResultT.EXHAUSTED
```

The final projection must use loop-frame outputs. It must not reach into only
the first review step or into a body-local step that is not materialized onto the
loop frame.

## 18. Loop Exhaustion Projection

The DSL already has `repeat_until.on_exhausted.outputs`, but it is intentionally
narrow. It maps declared loop-frame output names to literal scalar overrides
only when the body succeeds, outputs resolve, the condition evaluates false, and
`max_iterations` is exhausted. Without `on_exhausted`, exhausting
`max_iterations` remains a failed loop with `error.type:
repeat_until_iterations_exhausted`. Body-step failures, output-resolution
failures, and predicate failures remain failures and do not use exhaustion
overrides.

Therefore, `loop/recur` needs a generic frontend-level exhaustion projection:

```text
loop/recur :on-exhausted
  -> repeat_until.on_exhausted.outputs for scalar markers
  -> final typed projection from last materialized loop-frame outputs
```

Required behavior:

- if `max_iterations` exhausts after a completed iteration, set scalar marker
  `decision_status = EXHAUSTED`, preserve last completed loop-frame outputs, and
  construct typed `ResultT.EXHAUSTED` in final projection;
- if body fails, ordinary failure, not `EXHAUSTED`;
- if output resolution fails, ordinary failure, not `EXHAUSTED`;
- if predicate evaluation fails, ordinary failure, not `EXHAUSTED`;
- if no explicit exhaustion projection exists, preserve DSL behavior:
  `repeat_until_iterations_exhausted`.

This is a generic loop feature, not a review-loop compiler branch.

## 19. Evidence Authority

Review-provider output is decision evidence, not carried-artifact identity
authority.

For implementation review, consumed evidence such as `checks_report` must be
carried by inputs or loop state. The review provider may consume, inspect, and
judge that evidence, but it must not return a replacement `checks_report` path
that becomes authoritative.

Required rule:

```text
final_result.checks_report, or any equivalent carried evidence field,
must be copied from inputs/state, not from ReviewDecision.
```

The stdlib lowering document states this rule directly: consumed evidence
artifacts such as `checks_report` are loop inputs/consumes rather than
review-provider output fields; route and final projection steps carry evidence
refs from loop inputs/state; and negative validation should catch any lowering
where provider output can replace consumed evidence identity.

Required negative case:

```text
A review ProcRef returns a decision bundle containing a checks_report field.
The generic loop attempts to use that returned field as terminal evidence.
Compilation or shared validation fails with evidence_authority_violation.
```

## 20. Effects Contract

A specialized review loop's effect summary is the union of visible effects from
the loop and all selected ProcRef hooks:

```text
effects(review-revise-loop[...])
  =
    effects(review)
  union effects(fix)
  union effects(on-approved), if bridge model is used
  union effects(on-blocked), if bridge model is used
  union effects(on-exhausted), if bridge model is used
  union effects(loop/recur)
  union effects(match)
  union effects(materialization/projection)
```

A macro or specialization that hides provider or command effects is invalid.

Compile-time specialization with procedure references must satisfy this
boundary:

```text
before runtime:
  all type parameters are concrete
  review and fix point to concrete named procedures
  provider and prompt externs used by those procedures are resolved inside those procedures
  no runtime state carries ProcRef, provider ref, prompt ref, or type parameter
```

## 21. Source Maps And State Layout

Generated loop state, bundle paths, temp paths, pointer paths, and artifact roots
should be requested semantically and derived by StateLayout.

The review-loop stdlib implementation must source-map:

- caller call site;
- imported stdlib definition;
- macro expansion frame, if any;
- specialization arguments;
- generated monomorphic helper/private workflow;
- generated `repeat_until` frame;
- generated match cases;
- generated projection steps;
- generated state paths;
- generated bundle roots;
- selected review ProcRef definition;
- selected fix ProcRef definition;
- selected terminal-constructor ProcRefs, if bridge model is used.

High-level `.orc` code should request semantic layout targets such as:

```lisp
(phase-state phase_ctx "review-loop-frame")
(phase-target phase_ctx "review-report")
(phase-target phase_ctx "review-findings")
```

The layout layer derives concrete paths. Exact paths are design choices, not
frontend syntax.

Missing source-map origin for any generated step, boundary field, or generated
path is a compile-time failure.

## 22. Macro Boundary

Macros remain syntax expansion. They do not own runtime semantics.

Allowed:

```text
(review-revise-loop ...)
  expands to a call of a generic stdlib definition
```

or:

```text
(review-revise-loop ...)
  expands to a generated monomorphic .orc helper
  whose generated source then typechecks and lowers ordinarily
```

Disallowed:

- macro expansion owns hidden provider/command effects;
- macro expansion bypasses shared validation;
- macro expansion creates runtime procedure values;
- macro expansion creates source-map gaps;
- macro expansion encodes review/revise terminal behavior outside ordinary
  `.orc`.

A macro may keep public syntax ergonomic, but the control structure belongs in
imported `.orc` source or in a generic typed template mechanism available to
arbitrary `.orc`.

## 23. Generic Specialization Identity

Every generated specialization must have a deterministic identity:

- source module;
- definition name;
- source definition digest;
- concrete type argument identities;
- compile-time ProcRef identities;
- target DSL version;
- language/compiler version;
- generated-name schema version;
- call-site identity, when needed for source-map or path obligations.

Equivalent call sites may share a specialization only if doing so preserves
source-map and generated-path obligations. Otherwise, the compiler should
generate per-call-site helpers.

## 24. Incremental Implementation Plan

### Stage 0 - Add This Integration Document And Wire Related-Doc References

Tasks:

- add `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`;
- add reciprocal related-doc links where useful;
- mark `ReviewReviseLoopExpr` path as legacy/bridge-only;
- document that behavior-preserving preflight and Track A are prerequisites for
  stdlib review-loop promotion.

Acceptance:

- design docs agree on ownership boundaries;
- review-loop stdlib work is not planned before hard preflight and Track A
  substrate;
- legacy path is explicitly non-promoted.

### Stage 1 - Behavior-Preserving Refactor Preflight

Tasks:

- fix concrete hazards in `lowering.py`, `functions.py`, and `macros.py`;
- add focused characterization coverage for affected pass boundaries;
- record any pre-existing failures with exact commands and outputs;
- decide lowering package/facade boundary;
- introduce shared expression traversal utility;
- add traversal coverage over all `ExprNode` variants or explicit
  leaf/specialized classification.

Acceptance:

- compileall passes;
- focused tests pass or pre-existing failures are recorded;
- lowering package/facade decision is made before helper extraction;
- new expression forms have one obvious traversal update point;
- purity/extern/ProcRef discovery cannot silently miss unknown `ExprNode`
  containers.

### Stage 2 - Optional But Recommended Context And Helper Cleanup

Tasks:

- introduce `TypecheckContext` if needed before structural constraints;
- extract lowering extern discovery into a coherent helper module;
- extract lowering-time type helpers into a coherent helper module;
- preserve diagnostic codes, spans, form paths, and expansion stacks.

Acceptance:

- typecheck recursion has an explicit context value or equivalent stable
  boundary;
- variant-proof scope changes remain visible at match/control-flow boundaries;
- provider/prompt extern discovery behavior is unchanged;
- lowering-time type helper diagnostics are unchanged.

### Stage 3 - Track A Form Registry And Elaboration Boundary

Tasks:

- add `FormKind` / `FormSpec` registry;
- classify all recognized heads;
- derive or validate reserved macro names from registry;
- route expression elaboration through registry;
- classify `review-revise-loop` as `STDLIB_EXTENSION` or
  `TEMP_COMPILER_INTRINSIC` scheduled for removal.

Acceptance:

- each compiler-known head has owner, kind, rationale, and removal target where
  applicable;
- `review-revise-loop` is not classified as `CORE_SPECIAL`;
- ad hoc head dispatch is reduced or guarded.

### Stage 4 - Track A Denylist And Architecture Tests

Tasks:

- add promoted-mode denylist for `ReviewReviseLoopExpr` path;
- add `test_no_review_loop_expr_in_core_ast_union`;
- add `test_review_revise_loop_not_reserved_core_macro_name`;
- add `test_review_revise_loop_not_elaborated_by_head_name`;
- add `test_typecheck_does_not_import_review_loop_expr`;
- add `test_lowering_does_not_import_review_loop_expr`.

Acceptance:

- promoted route fails if review-loop-specific compiler artifacts are used;
- legacy fixtures may still opt into old path explicitly;
- tests distinguish syntax compatibility from semantic special casing.

### Stage 5 - Track A Tiny Imported `.orc` Expansion

Tasks:

- load stdlib `.orc` through normal reader/parser/import resolution;
- expand one tiny imported `defproc` call;
- clone/substitute imported body hygienically;
- return ordinary `ExprNode`;
- typecheck and lower through ordinary path;
- record source-map frames for caller and imported definition.

Acceptance:

- tiny imported `.orc` helper compiles;
- generated nodes source-map to both caller and imported definition;
- no review-loop-specific code is involved.

### Stage 6 - Track A Imported Effects And Match/Loop Fixtures

Tasks:

- add imported `.orc` procedure that emits provider or command effects;
- add imported `.orc` procedure using `match`;
- add imported `.orc` procedure using `loop/recur`;
- ensure effects are visible to validation and runtime planning;
- ensure match variant proof is ordinary, not stdlib-specific.

Acceptance:

- imported provider/command effects are visible;
- imported match fixture typechecks and lowers;
- imported loop fixture typechecks and lowers;
- source maps survive all fixtures.

### Stage 7 - Generic `loop/recur :on-exhausted`

Tasks:

- add authoring surface for `loop/recur` exhaustion projection;
- lower scalar markers to `repeat_until.on_exhausted.outputs`;
- add final typed projection from loop-frame outputs;
- preserve DSL failure behavior for body/output/predicate failures;
- reject direct non-scalar `on_exhausted` overrides.

Acceptance:

- generic loop fixture returns typed `EXHAUSTED` result;
- exhaustion without explicit projection still fails as
  `repeat_until_iterations_exhausted`;
- body failure during final iteration remains ordinary failure;
- non-scalar `on_exhausted` override is rejected.

### Stage 8 - Track A Generic ProcRef Specialization Through Imported `.orc`

Tasks:

- resolve ProcRef arguments before lowering;
- allow imported `.orc` procedures to accept ProcRef parameters;
- specialize selected procedures into callable helper/private workflow form;
- preserve provider and command effects from selected procedures;
- reject ProcRef values in runtime state;
- reject provider/prompt refs in runtime state;
- detect specialization cycles.

Acceptance:

- imported `.orc` ProcRef fixture calls review/fix-like hooks inside a loop;
- effect graph includes provider/command effects from hooks;
- runtime state contains no ProcRef/provider/prompt/type values;
- specialization cycle produces compile-time diagnostic.

### Stage 9 - Minimal Structural Generics

Tasks:

- parse `:forall` on `defproc`;
- parse inline `:where` structural constraints;
- support `is-record` and `is-union` constraints;
- support `has-field` constraints;
- support `has-union-variant` constraints;
- support ProcRef signature constraints with type parameters;
- instantiate monomorphic helper before ordinary lowering;
- typecheck instantiated helper;
- preserve variant proof through `match`.

Acceptance:

- pure generic `defproc` fixture passes;
- generic record-field fixture passes;
- generic union-match fixture passes;
- effectful generic ProcRef fixture passes;
- unsatisfied constraint fails before lowering;
- variant field access without proof fails before lowering.

### Stage 10 - Implement `std/phase.orc` `review-revise-loop`

Tasks:

- define stdlib `ReviewDecision` and `ReviewFindings`, unless already defined;
- define generic `review-revise-loop` in `std/phase.orc`;
- accept caller-owned `CompletedT`, `InputsT`, `ResultT`;
- express `ResultT` terminal variants as structural constraints;
- accept review/fix as compile-time ProcRef parameters;
- lower through `loop/recur`, `match`, `provider-result` / `command-result`,
  materialization, and projection;
- carry evidence identity through inputs/state;
- add source-map fixtures.

Acceptance:

- `APPROVE` first pass returns `ResultT.APPROVED`;
- `REVISE -> fix -> APPROVE` returns `ResultT.APPROVED` with fixed completed
  state;
- `BLOCKED` returns `ResultT.BLOCKED`;
- `REVISE` until `max_iterations` returns `ResultT.EXHAUSTED`;
- fix receives findings from the immediately preceding `REVISE` decision;
- terminal outputs come from loop frame/projection, not first review step;
- carried evidence cannot be redirected by `ReviewDecision` output.

### Stage 11 - Optional Terminal-Constructor Bridge

Use this only if direct generic result-union construction is not ready.

Tasks:

- add `on-approved` / `on-blocked` / `on-exhausted` ProcRef bridge surface;
- ensure constructor ProcRefs are compile-time only;
- ensure constructor effects are visible;
- ensure constructor return types specialize to concrete `ResultT`;
- mark bridge as migration-compatible but not the preferred long-term model.

Acceptance:

- review loop compiles without direct generic `ResultT` construction;
- runtime state still contains no constructor ProcRef values;
- source maps include constructor hooks;
- promotion remains blocked until either direct construction lands or bridge is
  accepted as stable stdlib API.

### Stage 12 - Remove Promoted Dependency On Compiler-Special Review Loop

Tasks:

- remove `ReviewReviseLoopExpr` from promoted expression table;
- remove or quarantine `_lower_review_revise_loop`;
- remove or quarantine review-loop-only typecheck branch;
- remove or quarantine `_validate_review_loop_result_contract`;
- remove review-loop-specific compiler visitor logic;
- remove reserved macro treatment that prevents real `.orc` implementation;
- keep legacy fixtures explicitly marked legacy;
- ensure stdlib fixtures compile with special path disabled.

Acceptance:

- promoted review loop compiles without `ReviewReviseLoopExpr`;
- regression guard fails if lowerer recognizes literal `review-revise-loop`;
- generated workflow contains ordinary `repeat_until` / `match` /
  provider/command/projection surfaces.

### Stage 13 - Promotion Evidence

Tasks:

- compile stdlib review-loop candidate;
- run shared validation;
- run dry-run;
- run targeted fake-provider integration for `APPROVE`;
- run targeted fake-provider integration for `REVISE -> APPROVE`;
- run targeted fake-provider integration for `BLOCKED`;
- run targeted fake-provider integration for `EXHAUSTED`;
- run evidence-redirection negative test;
- run source-map provenance test;
- generate parity report;
- compute `non_regressive` mechanically.

`.orc` primary promotion remains blocked until evidence is non-regressive under
the migration parity policy.

### Stage 14 - Resume Broader Cleanup Backlog

After the stdlib route is stable, continue broader cleanup that was not required
as a hard precondition:

- diagnostic builder consolidation;
- pass-local validation helper consolidation;
- source-map/build-artifact ownership cleanup;
- package-root API narrowing;
- fixture-only code movement;
- migration scaffolding audit;
- module dependency audit.

The broader backlog's suggested order is characterization coverage,
`TypecheckContext`, lowering operation-family split, diagnostics/validation
consolidation, source-map/build-artifact ownership, and migration scaffolding
audit after shared Core AST and Semantic IR contracts are resolved.

## 25. Diagnostics

Add precise diagnostics. Avoid generic "type error" where the failure is
architectural.

`stdlib_special_form_disallowed`
: Compiler recognized `review-revise-loop` by name in promoted mode.

`review_loop_special_lowerer_used`
: Promoted fixture attempted to use `ReviewReviseLoopExpr` or equivalent legacy
  branch.

`form_registry_missing_classification`
: Compiler-known head lacks `FormSpec` classification.

`reserved_name_registry_mismatch`
: Reserved macro names diverge from `FormSpec` registry.

`stdlib_extension_missing_import_route`
: Stdlib extension cannot resolve through import/call path.

`imported_expansion_source_missing`
: Imported `.orc` expansion lacks imported-definition source provenance.

`hidden_imported_effect`
: Imported `.orc` definition introduced provider/command effect not visible to
  validation.

`unknown_exprnode_not_classified`
: Expression traversal, purity, extern discovery, or ProcRef discovery
  encountered an unclassified `ExprNode`.

`refactor_characterization_missing`
: Track A attempted to change a pass boundary without focused characterization
  coverage.

`unresolved_type_parameter`
: Type parameter escaped specialization.

`ambiguous_type_argument`
: Call-site types do not determine one concrete type argument.

`unsatisfied_structural_constraint`
: Concrete type lacks required field, union variant, or compatible field type.

`unsupported_parametric_boundary`
: Generic type appeared where a monomorphic workflow boundary is required.

`specialization_cycle`
: Generic/proc-ref specialization recursively depends on itself.

`proc_ref_not_compile_time`
: ProcRef argument did not resolve to a named `defproc` at compile time.

`runtime_leaked_proc_ref`
: ProcRef appears in lowered runtime state or contract.

`runtime_leaked_provider_ref`
: Provider ref appears in lowered runtime state or contract.

`runtime_leaked_prompt_ref`
: Prompt ref appears in lowered runtime state or contract.

`runtime_leaked_type_parameter`
: Type parameter appears in Core AST, Semantic IR, Executable IR, artifact
  contract, output bundle, or provider/command payload.

`hidden_macro_effect`
: Macro introduced provider/command effect not visible in expanded AST.

`variant_field_without_proof`
: Generic body accessed a variant-only field outside proof-bearing match branch.

`non_exhaustive_review_match`
: Review decision match does not cover `APPROVE`, `REVISE`, and `BLOCKED`.

`exhaustion_projection_missing`
: `loop/recur` needs typed `EXHAUSTED` result but no on-exhausted projection
  exists.

`invalid_exhaustion_projection`
: On-exhausted attempted to override non-scalar loop output directly.

`loop_frame_projection_missing`
: Final result projection reads a value not materialized onto the loop frame.

`evidence_authority_violation`
: Reviewer-produced field attempts to replace carried evidence identity.

`source_map_origin_missing`
: Generated helper, step, field, path, or projection lacks source-map
  provenance.

## 26. Fixture Matrix

### 26.1 Behavior-Preserving Refactor Preflight Fixtures

- `lowering_duplicate_helper_guard`
- `private_workflow_variant_case_type_ref`
- `defun_purity_unknown_exprnode_negative`
- `macro_hygiene_malformed_match_preserves_provenance`
- `macro_hygiene_malformed_defworkflow_preserves_provenance`
- `refactor_characterization_provider_result`
- `refactor_characterization_command_result`
- `refactor_characterization_phase_stdlib`
- `refactor_characterization_resource_stdlib`
- `refactor_characterization_drain_stdlib`
- `refactor_characterization_source_map_origin`

### 26.2 Expression Traversal Fixtures

- `expression_traversal_covers_all_exprnode_variants`
- `expression_traversal_letstar`
- `expression_traversal_match`
- `expression_traversal_if`
- `expression_traversal_record`
- `expression_traversal_provider_result`
- `expression_traversal_command_result`
- `expression_traversal_produce_one_of`
- `expression_traversal_resume_or_start`
- `expression_traversal_resource_transition`
- `expression_traversal_backlog_drain`
- `expression_traversal_review_loop_legacy_if_present`
- `expression_traversal_leaf_classification`

### 26.3 Track A Architecture Fixtures

- `form_registry_classifies_all_known_heads`
- `reserved_names_derive_from_form_registry`
- `review_revise_loop_not_core_special`
- `review_revise_loop_promoted_route_denylist`
- `test_no_review_loop_expr_in_core_ast_union`
- `test_review_revise_loop_not_reserved_core_macro_name`
- `test_review_revise_loop_not_elaborated_by_head_name`
- `test_typecheck_does_not_import_review_loop_expr`
- `test_lowering_does_not_import_review_loop_expr`

### 26.4 Imported `.orc` Expansion Fixtures

- `imported_tiny_defproc_expands.orc`
- `imported_tiny_defproc_source_map.orc`
- `imported_provider_effect_visible.orc`
- `imported_command_effect_visible.orc`
- `imported_match_union_proof.orc`
- `imported_loop_recur.orc`
- `imported_proc_ref_specialization.orc`
- `imported_expansion_no_runtime_proc_ref_negative.orc`
- `imported_expansion_hidden_effect_negative.orc`

### 26.5 Generic Language Fixtures

- `generic_pure_identity.orc`
- `generic_record_field_constraint.orc`
- `generic_union_variant_constraint.orc`
- `generic_union_match_projection.orc`
- `generic_proc_ref_effectful_loop.orc`
- `generic_specialization_source_map.orc`
- `generic_specialization_cycle_negative.orc`
- `generic_ambiguous_type_argument_negative.orc`
- `runtime_leaked_type_parameter_negative.orc`
- `runtime_leaked_proc_ref_negative.orc`
- `variant_field_without_proof_negative.orc`
- `hidden_macro_effect_negative.orc`

### 26.6 Loop/Exhaustion Fixtures

- `loop_recur_exhausted_projection.orc`
- `loop_recur_exhausted_without_projection_negative.orc`
- `loop_recur_body_failure_not_exhausted_negative.orc`
- `loop_recur_output_resolution_failure_not_exhausted_negative.orc`
- `loop_recur_non_scalar_on_exhausted_negative.orc`
- `loop_recur_source_map.orc`

### 26.7 Review-Loop Stdlib Fixtures

- `phase_stdlib_review_loop_approve.orc`
- `phase_stdlib_review_loop_revise_approve.orc`
- `phase_stdlib_review_loop_blocked.orc`
- `phase_stdlib_review_loop_exhausted.orc`
- `phase_stdlib_review_loop_malformed_decision_negative.orc`
- `phase_stdlib_review_loop_malformed_findings_negative.orc`
- `phase_stdlib_review_loop_evidence_redirection_negative.orc`
- `phase_stdlib_review_loop_missing_bundle_negative.orc`
- `phase_stdlib_review_loop_no_special_lowerer_negative.orc`
- `phase_stdlib_review_loop_source_map.orc`
- `phase_stdlib_review_loop_resume_checkpoint_identity.orc`
- `phase_stdlib_review_loop_proc_ref_effects.orc`
- `phase_stdlib_review_loop_runtime_leak_negative.orc`

### 26.8 Migration/Parity Fixtures

- `review_loop_compile_pass`
- `review_loop_shared_validation_pass`
- `review_loop_dry_run_pass`
- `review_loop_fake_provider_approve_pass`
- `review_loop_fake_provider_revise_approve_pass`
- `review_loop_fake_provider_blocked_pass`
- `review_loop_fake_provider_exhausted_pass`
- `review_loop_output_contract_parity_pass`
- `review_loop_terminal_state_parity_pass`
- `review_loop_artifact_parity_pass`
- `review_loop_resume_parity_pass`
- `review_loop_non_regressive_report_pass`

## 27. Acceptance Checks

Before removing the promoted-path compiler-special review-loop branch, all of
the following must pass:

- Behavior-preserving preflight is complete.
- Concrete hazards are fixed or explicitly documented as not applicable.
- Characterization coverage exists for pass boundaries touched by Track A.
- Lowering package/facade boundary is decided before helper extraction.
- Shared expression traversal covers every `ExprNode` variant or explicit
  leaf/specialized classification.
- Track A form registry exists.
- Registry-routed elaboration is active.
- Reserved names derive from or are checked against registry.
- `review-revise-loop` is not `CORE_SPECIAL`.
- Promoted route denylist catches `ReviewReviseLoopExpr` use.
- A non-review imported `.orc` fixture uses the same generic expansion
  mechanism.
- Imported `.orc` effects are visible.
- Imported `.orc` source maps include caller and imported definition.
- Imported `.orc` ProcRef specialization works.
- Generic `.orc` definitions can declare structural record and union constraints.
- Unsatisfied constraints fail before lowering.
- Specialization emits monomorphic helpers with no runtime type values.
- Variant-specific fields remain proof-gated after specialization.
- ProcRef hooks are compile-time only.
- Provider/command effects from ProcRef hooks are visible.
- `review-revise-loop` imports from `std/phase.orc`.
- `review-revise-loop` compiles with `ReviewReviseLoopExpr` disabled.
- `review-revise-loop` lowers to ordinary `repeat_until`, `match`,
  provider/command, materialization, and projection surfaces.
- `APPROVE`, `REVISE->APPROVE`, `BLOCKED`, and `EXHAUSTED` behavior pass.
- `EXHAUSTED` is typed non-completion.
- `REVISE` is not completion.
- Review-provider output cannot replace carried evidence identity.
- Source maps identify caller, stdlib, specialization, generated helper,
  ProcRefs, and generated paths.
- Runtime state contains no ProcRef, provider ref, prompt ref, closure, or type
  parameter.
- Shared validation accepts generated workflow.
- Parity report computes `non_regressive` mechanically.

## 28. Compatibility And Migration Policy

Existing YAML workflows remain valid and primary until promotion evidence passes.

Existing compiler-special review-loop support may remain temporarily as a legacy
bridge, but:

- legacy bridge fixtures must be marked legacy;
- promoted stdlib fixtures must run with the special path disabled;
- new review/revise feature work should target `std/phase.orc` plus generic
  constraints;
- no new caller should depend on `ReviewReviseLoopExpr` as the intended
  architecture.

Migration is additive:

1. Add behavior-preserving preflight fixes and characterization.
2. Add Track A generic expansion substrate.
3. Add generic constraints/specialization support needed by imported stdlib code.
4. Add stdlib `.orc` implementation.
5. Add fixtures and negative tests.
6. Compile and validate.
7. Run dry-run and targeted fake-provider integrations.
8. Generate parity report.
9. Let promotion tooling compute `non_regressive`.
10. Only then mark `.orc` primary or remove YAML primary.

## 29. Open Questions

- Should the first stable API expose only `CompletedT`, `InputsT`, and `ResultT`,
  while keeping `ReviewDecision` and `ReviewFindings` as stdlib-owned concrete
  types?
- Should generic `DecisionT` and `FindingsT` wait until a concrete caller needs
  custom decision/findings schemas?
- Should fix receive only `ReviewFindings`, or the entire `REVISE` variant
  payload?
- Should terminal result construction use structural constraints from the start,
  or should constructor ProcRefs be accepted as a temporary bridge?
- If existing caller result unions use phase-specific field names, should the
  type system support trait aliases with field-name mapping, or should callers
  normalize to stdlib protocol field names?
- Should `review-revise-loop` be a `defproc`, `defworkflow`, or macro that
  expands to a call to a generic `defproc`?
- How much generic body checking should occur before monomorphic instantiation?
  The minimal implementation can typecheck instantiated helpers first, but
  better diagnostics require generic checking against constraints.
- What is the stable generated-name schema for specializations whose identity
  includes call-site provenance?
- How should resume checkpoint identity be assigned when a stdlib loop is
  imported, specialized, and lowered to a generated/private workflow?
- Which promotion gate should decide that the terminal-constructor bridge is
  stable enough, if direct generic union construction remains incomplete?
- Which existing high-level forms besides `review-revise-loop` should be
  reclassified from `TEMP_COMPILER_INTRINSIC` to `STDLIB_EXTENSION` after the
  generic expansion route is proven?
- Which refactor preflight items must be hard gates for Track A versus strong
  recommendations before structural constraints? This document treats concrete
  hazards, characterization, lowering-boundary choice, and traversal coverage as
  hard gates.

## 30. Summary Recommendation

Proceed in this order:

1. Add this integration doc and reciprocal related-doc links.
2. Complete hard behavior-preserving preflight:
   - concrete hazards;
   - characterization coverage;
   - lowering package/facade decision;
   - shared expression traversal coverage.
3. Implement Track A:
   - `FormKind` / `FormSpec` registry;
   - registry-routed elaboration;
   - reserved-name derivation/checking;
   - promoted-route denylist tests;
   - tiny imported `.orc` expansion;
   - imported source maps;
   - imported effect visibility;
   - generic ProcRef specialization.
4. Add generic `loop/recur` exhaustion projection.
5. Add minimal structural generics:
   - `:forall`;
   - `is-record`;
   - `has-field`;
   - `has-union-variant`;
   - ProcRef constraints;
   - variant-proof preservation.
6. Implement `std/phase.orc` `review-revise-loop` using direct structural result
   constraints where possible.
7. Use terminal-constructor ProcRefs only as a bridge if direct generic union
   construction is not ready.
8. Prove `APPROVE`, `REVISE->APPROVE`, `BLOCKED`, `EXHAUSTED`, source-map,
   resume, and evidence-authority fixtures.
9. Remove `ReviewReviseLoopExpr` from the promoted path.
10. Gate migration through machine-computed parity evidence.
11. Continue broader backlog cleanup after the semantic route is stable.

The key architectural move is not to move the existing Python branch into a
macro. The key move is to make the frontend refactor-safe first, then make
generic `.orc` expansion and the type system expressive enough that
`review-revise-loop` is just one ordinary effectful stdlib definition over
caller-owned typed state, caller-owned terminal results, compile-time procedure
hooks, structural result constraints, proof-preserving match, and generic loop
exhaustion projection.

## Major Changes

This version explicitly incorporates the broader refactoring order. It
distinguishes hard preflight work from Track A, and Track A from missing
language/type-system features.

The hard preflight now includes concrete hazard fixes, characterization tests,
the lowering package/facade decision, and shared expression traversal coverage.
Broader backlog cleanup is deferred until after the semantic route is stable.

The document now treats
`docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md` as the
Track A implementation prerequisite, while
`workflow_lisp_compile_time_parametric_specialization.md` and
`workflow_lisp_structural_parametric_constraints.md` remain the type-system
mechanism docs.

## Issues To Verify

The main implementation decision to verify is whether `TypecheckContext` should
be a hard gate before Track A, or only before structural constraints. I drafted
it as strongly recommended before structural constraints because Track A can
start with simple imported `.orc` fixtures, but structural generics will likely
make the current typecheck threading more fragile.

The second decision is whether direct generic `ResultT` variant construction is
feasible in the first implementation. If not, terminal-constructor ProcRefs are
a reasonable bridge, but the document keeps direct structural result construction
as the preferred long-term model.
