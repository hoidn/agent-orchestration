# Workflow Lisp Parametric Defproc Specialization Substrate Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-parametric-defproc-specialization-substrate`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_mvp_specification.md`

## Scope

This slice covers exactly the bounded compile-time generic-`defproc`
specialization substrate selected by the current drain state:

- add authored `defproc` support for `:forall` type-parameter declarations in
  the owner-doc clause order:
  `name`, optional `:forall`, ordinary parameter list, optional `:where`,
  return type, body;
- parse and retain `:where` clauses as frontend-owned metadata so later
  structural-constraint work does not need to reopen the `defproc` header
  grammar;
- extend the frontend type layer with compile-time-only type-parameter refs and
  substitution helpers that can appear anywhere an existing `TypeRef` may
  appear in a procedure signature, including nested `ProcRef[...]` and
  `WorkflowRef[...]` positions;
- infer concrete call-site type arguments for generic procedures from actual
  argument types and compile-time ref signatures, then materialize deterministic
  monomorphic specialized procedures before ordinary lowering;
- define typed specialization identity and generated-name rules that compose
  with the existing ProcRef/workflow-ref specialization machinery without
  introducing runtime type values, runtime dispatch, or runtime procedure
  values;
- preserve effect summaries, source-map provenance, and existing inline versus
  private-workflow lowering policy after specialization.

Out of scope for this slice:

- structural constraint semantics such as `is-record`,
  `has-field`,
  `has-union-variant`, or `has-shared-union-field`;
- generic `defworkflow`, generic workflow-boundary transport, or runtime
  workflow loading;
- authoring or lowering of stdlib `review-revise-loop` as an ordinary generic
  `.orc` definition;
- removal of the temporary `__stdlib-specialization__` review-loop bridge;
- new runtime type objects, runtime closures, runtime multiple dispatch, or
  runtime-carried ProcRef/WorkflowRef/provider/prompt values;
- new source-map schema surfaces, new command-adapter behavior, or changes to
  shared runtime/validation ownership.

This is a bounded implementation architecture for the selected specialization
substrate only. It does not replace the parent frontend design, the MVP
baseline, or the broader review/revise stdlib integration architecture.

## Problem Statement

The current checkout already proves one important half of the future generic
story:

- ProcRef specialization exists and is compile-time-only.
- WorkflowRef specialization exists and is compile-time-only.
- Lowering already knows how to reuse deterministic specialized private
  workflows or inline procedures without leaking ref values to runtime state.

But the type layer remains monomorphic:

- `ProcedureDef` stores only authored type-name strings.
- `ProcedureSignature` stores only concrete resolved `TypeRef` trees.
- `FrontendTypeEnvironment` resolves named types, collection types, ProcRef
  types, and WorkflowRef types, but it has no notion of a locally scoped type
  parameter.
- `std/phase.orc` still exports `review-revise-loop` through the temporary
  `__stdlib-specialization__ phase-review-loop` bridge because ordinary
  imported `defproc` definitions cannot yet abstract over caller-owned
  `CompletedT` / `InputsT` shapes.

That leaves the target design stuck between two bad options:

1. keep adding compiler-private stdlib specialization branches; or
2. postpone ordinary generic stdlib code because the frontend cannot express a
   reusable procedure whose signature depends on caller-specific types.

The selected gap is therefore narrower than full structural generics:

- first, the frontend needs a compile-time type-parameter substrate for
  generic `defproc`;
- then later slices can add constraint semantics and use this substrate to
  retire the compatibility bridge.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `11. Parametric Specialization Dependency`
  - `12. Structural Constraint Dependency`
  - `23. Generic Specialization Identity`
  - `24. Incremental Implementation Plan`
    - `Stage 8 - Track A Generic ProcRef Specialization Through Imported .orc`
    - `Stage 9 - Minimal Structural Generics`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `7. Types`
  - `8.8 defproc`
  - `13. Loops`
  - `16. Effect System`
  - `44. Typed Frontend AST`
  - `51. defproc Lowering`
  - `52. call Lowering`
  - `63. Variant Proof Validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/steering.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and shared
  runtime behavior under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- keep generated procedures monomorphic before Core Workflow AST, Semantic IR,
  Executable IR, runtime plans, and persisted state are constructed;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep macros syntax-only and keep command/result semantics subject to the
  existing command-adapter contract even when generic procedures specialize
  around those commands;
- keep the MVP baseline intact on its non-goals:
  no second execution engine,
  no YAML-as-authority,
  no runtime code loading,
  and no report parsing for workflow meaning.

`docs/design/workflow_command_adapter_contract.md` is authoritative here even
though this slice adds no new adapter. Generic specialization must not become a
loophole for hiding semantic command behavior behind type-driven helper
generation. Specialized procedures still lower through the same visible
`command-result` / certified-adapter contracts as monomorphic procedures.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-revise-preflight-hazard-fixes/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the staged frontend pipeline and package ownership split.
- Reuse `SourcePosition`, `SourceSpan`, recursive syntax provenance,
  `LispFrontendDiagnostic`, macro expansion stacks, `LoweringOriginMap`, and
  the persisted source-map sidecar rather than inventing a second provenance
  channel.
- Reuse the existing `defproc` lowering policy:
  generic procedures still choose between `inline`, `private-workflow`, and
  `auto` only after specialization produces a monomorphic callable.
- Reuse the existing compile-time-only ProcRef and WorkflowRef rules:
  no runtime transport, deterministic specialization names, effect visibility,
  and cycle detection stay mandatory.
- Reuse canonical callable identities and imported procedure visibility from the
  module/import/export slice rather than inventing a second linker for generic
  procedures.
- Reuse the workflow-boundary flattening slice's rule that typed frontend
  surfaces remain authoritative until the existing shared boundary seam, even
  when a procedure is generic internally.

### New Decisions In This Slice

- The first stable parametric surface is `defproc`, not `defworkflow`.
- `:forall` becomes a frontend-owned `defproc` header clause now; `:where`
  becomes a parsed metadata clause now, but its constraint semantics remain
  deferred to the structural-constraints slice.
- The frontend type system gains a compile-time-only `TypeParamRef` that can be
  nested inside existing `TypeRef` trees and must be fully substituted away
  before lowering.
- Call-site specialization is inferred from actual argument types and
  compile-time ref signatures; this slice does not add explicit authored type
  application syntax.
- Generic procedure specialization composes with existing ProcRef and
  WorkflowRef specialization instead of replacing them: one specialized
  procedure may carry type bindings, ProcRef bindings, WorkflowRef bindings,
  and bound value identities in the same compile-time metadata object.
- Specialization identity is explicit and deterministic, and generated helper
  names remain implementation details rather than runtime checkpoint keys.

### Conflicts Or Revisions

The accepted `defproc` procedural substrate assumed all procedure signatures
were monomorphic after ordinary type resolution. This slice revises that
assumption narrowly:

- authored `defproc` definitions may now carry compile-time type parameters;
- the runtime-visible callable graph still remains monomorphic because generic
  procedures must specialize before lowering.

The existing ProcRef partial-application slice already owns deterministic
compile-time procedure specialization for ref/value bindings. This slice does
not replace that design. It extends the same compile-time specialization model
with a type-binding dimension and keeps the existing ProcRef behavior valid for
non-generic procedures.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- `defproc` header support for `:forall` and parsed `:where` metadata;
- compile-time type-parameter refs and substitution across procedure
  signatures, nested `ProcRef[...]` / `WorkflowRef[...]` types, and local
  type-resolution contexts;
- call-site type-argument inference for generic procedure calls;
- deterministic generic-procedure specialization identity and generated names;
- materialization of monomorphic specialized procedures before effect closure
  and lowering;
- runtime-erasure guards that reject any remaining `TypeParamRef` after
  specialization;
- focused tests for parsing, inference, specialization identity, monomorphic
  materialization, diagnostics, and runtime-erasure behavior.

This slice intentionally does not own:

- structural constraint vocabulary or enforcement;
- generic `defworkflow`;
- review-loop stdlib authoring, findings schemas, caller projection, or bridge
  retirement;
- source-map schema redesign, runtime checkpoint identity, or shared validation
  category changes;
- new adapters, scripts, runtime-native effects, or command-boundary policies.

## Current Checkout Facts

The current checkout already contains reusable specialization substrate that
this slice should extend rather than duplicate:

- `orchestrator/workflow_lisp/procedure_refs.py` already resolves compile-time
  ProcRef values, computes residual signatures, and generates deterministic
  `%proc-ref.*` specialization names.
- `orchestrator/workflow_lisp/workflow_refs.py` already resolves compile-time
  WorkflowRef bindings and generates deterministic higher-order helper names.
- `orchestrator/workflow_lisp/procedures.py` already defines
  `ProcedureCallableSpecialization`, which carries workflow-ref bindings,
  proc-ref bindings, bound values, and authored origin metadata for generated
  specialized procedures.
- `orchestrator/workflow_lisp/compiler.py` and
  `orchestrator/workflow_lisp/lowering.py` already materialize compile-time
  specializations before executable lowering and already reject leaked runtime
  ref transport.
- `orchestrator/workflow_lisp/type_expressions.py` supports named types,
  collection types, `ProcRef[...]`, and `WorkflowRef[...]`, but there is no
  authored `:forall` / `:where` header grammar and no type-parameter ref in the
  resolved type layer.
- `orchestrator/workflow_lisp/type_env.py` resolves concrete named types only;
  there is no local type-parameter overlay.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` still defines
  `review-revise-loop` as a macro over
  `(__stdlib-specialization__ phase-review-loop ...)`.
- `tests/test_workflow_lisp_procedures.py` already proves deterministic ProcRef
  specialization, cycle detection, effect preservation, and reuse of private
  workflow lowering, but there are no tests for `:forall`, `:where`, or
  generic type-argument inference.

The gap is therefore not generic specialization from scratch. The gap is to add
compile-time type-parameter ownership that plugs into the existing
specialization path.

## Feasibility Proof

This slice depends on one unproven claim: a generic procedure can reuse the
existing specialization-and-lowering path instead of requiring a second
execution model.

The current checkout already proves the critical adjacent capabilities:

- `tests/test_workflow_lisp_procedures.py::test_stage3_materializes_proc_ref_specializations_before_lowering_and_preserves_effects`
  proves the compiler can generate specialized procedures before lowering while
  preserving transitive effects.
- `tests/test_workflow_lisp_procedures.py::test_higher_order_procedure_specializations_reuse_private_workflow_lowering`
  proves specialized helpers can reuse existing private-workflow lowering.
- `tests/test_workflow_semantic_ir.py` already guards that serialized runtime
  authority does not leak `ProcRef` or `WorkflowRef` values.

The missing capability is narrower:

- type-parameter resolution and substitution do not yet exist;
- there is no generic specialization identity that includes type arguments;
- there is no runtime-erasure guard for unresolved type parameters.

That means the architecture is feasible as an extension of the existing
compile-time specialization machinery. It does not justify a new lowering path
or runtime surface.

## Proposed Package Boundary

Keep ownership inside the existing frontend package and add one focused generic
specialization helper module:

```text
orchestrator/workflow_lisp/
  compiler.py
  lowering.py
  modules.py                   # unchanged authority surface
  parametric_procedures.py     # new
  procedure_refs.py
  procedures.py
  source_map.py
  type_env.py
  type_expressions.py          # unchanged recursive grammar; reused named types
  typecheck.py
  workflow_refs.py
```

Responsibilities:

- `procedures.py`
  - parse optional `:forall` and optional `:where` clauses on `defproc`;
  - extend `ProcedureDef` and `ProcedureSignature` with generic metadata;
  - keep ordinary monomorphic `defproc` syntax unchanged.
- `type_env.py`
  - add `TypeParamRef`;
  - add local type-parameter overlay resolution;
  - add recursive type-substitution helpers and a fail-closed leakage checker.
- `parametric_procedures.py`
  - own type-argument inference,
    specialization-key construction,
    monomorphic signature substitution,
    generated-name derivation,
    and reusable specialization-cache helpers.
- `typecheck.py`
  - detect generic procedure call targets;
  - infer concrete type bindings from actual arguments;
  - reject ambiguous or unresolved type arguments;
  - record specialization requests for later materialization.
- `compiler.py`
  - materialize reachable generic specializations before effect closure and
    lowering;
  - compose type bindings with existing ProcRef/workflow-ref/value bindings;
  - keep cycle diagnostics attached to authored call sites.
- `lowering.py`
  - consume only monomorphic specialized procedures;
  - fail closed if any `TypeParamRef` reaches lowering.
- `source_map.py`
  - reuse the existing schema and generated-name provenance fields;
  - serialize specialization-origin notes from the new metadata without
    redesigning the schema.

No new shared-runtime package is introduced.

## Data Model

### Authored Generic Procedure Metadata

Extend the procedure layer with explicit generic header metadata:

```text
ProcedureTypeParam
  name
  span
  form_path

ProcedureConstraintSyntax
  subject_name
  constraint_head
  raw_operands
  span
  form_path

ProcedureDef
  ...
  type_params: tuple[ProcedureTypeParam, ...]
  where_clauses: tuple[ProcedureConstraintSyntax, ...]

ProcedureSignature
  ...
  type_params: tuple[TypeParamRef, ...]
  where_clauses: tuple[ProcedureConstraintSyntax, ...]
```

Clause-order rules for this slice:

- `:forall` may appear at most once and only immediately after the procedure
  name;
- `:where` may appear at most once and only after the ordinary parameter list;
- duplicate type-parameter names are invalid;
- `:where` subjects may reference only declared type parameters;
- non-empty `:where` clauses are retained in metadata now, but semantic
  enforcement is deferred to the structural-constraints slice.

The recursive type-expression grammar does not need a new parser surface for
type variables. Existing `NamedTypeExpr("T")` can resolve to either a concrete
named type or a locally scoped `TypeParamRef` depending on context.

### Type Parameters And Substitution

Add one compile-time-only resolved type:

```text
TypeParamRef
  name
  owner_callable_name
```

Substitution operates over the existing `TypeRef` tree recursively:

- `PrimitiveTypeRef`, `PathTypeRef`, concrete `RecordTypeRef`, and concrete
  `UnionTypeRef` remain unchanged;
- `TypeParamRef` resolves through a concrete binding map;
- `OptionalTypeRef`, `ListTypeRef`, `MapTypeRef`, `ProcRefTypeRef`, and
  `WorkflowRefTypeRef` recursively substitute their nested type refs.

Substitution must be total before lowering. A post-specialization leak of
`TypeParamRef` is a compile-time integrity error.

### Specialization Identity

Add a deterministic generic specialization identity:

```text
ProcedureParametricSpecializationKey
  source_module
  definition_name
  definition_digest
  concrete_type_bindings
  proc_ref_identities
  workflow_ref_identities
  value_binding_identities
  target_dsl_version
  compiler_language_version
  generated_name_schema_version
  call_site_identity?   # included only when provenance/path obligations require it
```

Rules:

- equivalent call sites may reuse one specialization only if the full key
  matches and reuse does not lose required provenance or generated-path
  obligations;
- generated helper names are derived from this key and remain implementation
  details;
- runtime resume/checkpoint identity must remain owned by existing runtime and
  source-map contracts, not by this generated helper name.

`ProcedureCallableSpecialization` should be extended rather than replaced so one
specialized procedure can carry:

- type bindings,
- ProcRef bindings,
- WorkflowRef bindings,
- bound values,
- authored origin metadata,
- and a stable specialization key.

## Compilation Pipeline

### 1. Elaborate Generic `defproc` Headers

`elaborate_procedure_definitions(...)` gains optional `:forall` and `:where`
header handling.

This stage owns:

- clause-order validation;
- duplicate-type-parameter rejection;
- parsing and storing `ProcedureConstraintSyntax`;
- building a local type-parameter scope for signature resolution.

This stage does not yet own structural-constraint semantics.

### 2. Build Generic Procedure Signatures

`build_procedure_catalog(...)` resolves generic procedure signatures under a
local type-parameter overlay:

- signature parameter and return positions may contain `TypeParamRef`;
- nested `ProcRef[...]` and `WorkflowRef[...]` type refs may also contain
  `TypeParamRef`;
- imported procedure catalogs remain the authority for visibility and canonical
  callable naming.

Generic signatures remain frontend-local. They do not cross runtime boundaries.

### 3. Infer Concrete Type Arguments At Call Sites

When typechecking a procedure call whose target signature has `type_params`:

- walk the formal parameter `TypeRef` tree against the actual argument type;
- collect consistent bindings for each `TypeParamRef`;
- recurse through collection, ProcRef, and WorkflowRef type refs using ordinary
  structural equality of the already-supported concrete type shapes;
- treat conflicting inferred bindings as `ambiguous_type_argument`;
- reject any type parameter that cannot be determined from call-site evidence as
  `unresolved_type_parameter`.

This slice does not add expected-result inference or explicit authored type
applications. Type arguments must be inferable from actual call arguments and
compile-time ref signatures alone.

### 4. Materialize Monomorphic Specialized Procedures

After inference, the compiler records a specialization request rather than
lowering against the generic callable directly.

Materialization uses the existing specialization pattern:

- compute a deterministic specialization key;
- generate a hidden specialized procedure name;
- derive a monomorphic `ProcedureSignature` by substituting concrete type
  bindings;
- retain the original authored body syntax;
- typecheck that body under a local environment containing the concrete type
  bindings plus any ProcRef/workflow-ref/value bindings already carried by the
  specialization;
- attach specialization metadata to the generated `TypedProcedureDef`.

This keeps body typechecking honest without inventing a second generic-body IR.
Nested authored type names inside the body continue to resolve through the local
type-binding overlay when the specialized clone is typechecked.

### 5. Compose With Existing ProcRef And WorkflowRef Specialization

Generic procedure specialization is additive:

- a generic procedure may also accept ProcRef parameters;
- a generic procedure may also be specialized by bound values or WorkflowRef
  arguments where those are already supported;
- the compiler should use one specialization queue/cache keyed by the combined
  metadata so it does not emit parallel helpers for the same concrete binding
  set.

Cycle detection must treat generic specialization cycles the same way existing
ProcRef/workflow-ref specialization cycles are treated: as compile-time errors
attached to authored call sites.

### 6. Lower Only Monomorphic Procedures

Lowering remains unchanged in policy but gains one new fail-closed rule:

- no `TypedProcedureDef` with non-empty `type_params`,
  unresolved `TypeParamRef`,
  or unsupported non-empty `:where` obligations may reach lowering.

If a generic procedure is referenced but cannot be specialized into a concrete
callable, compilation fails before lowering and before shared validation.

## Diagnostics And Tests

Add precise diagnostics for the new surface:

- `procedure_type_param_duplicate`
- `procedure_type_param_unknown`
- `procedure_type_param_clause_invalid`
- `procedure_where_clause_invalid`
- `unsupported_parametric_constraint_surface`
- `ambiguous_type_argument`
- `unresolved_type_parameter`
- `runtime_leaked_type_parameter`
- `parametric_specialization_cycle`

Required test families:

- header parsing and clause-order validation for `:forall` / `:where`;
- generic identity fixture with one unconstrained `defproc`;
- generic collection and nested `ProcRef[...]` inference fixtures;
- negative ambiguity and unresolved-type fixtures;
- generic-specialization reuse fixture for equivalent call sites;
- specialization provenance fixture proving generated helpers retain authored
  origin;
- runtime-erasure fixture proving no `TypeParamRef` reaches lowered workflows,
  source-map authority, Semantic IR, or Executable IR serialization;
- compatibility fixture proving non-generic procedures continue to compile
  without behavior change.

## Implementation Sequence

1. Extend `defproc` parsing for `:forall` and `:where` metadata.
2. Add `TypeParamRef` and recursive substitution/leakage helpers.
3. Extend procedure signatures/catalogs to carry generic metadata.
4. Implement call-site inference and specialization-key generation in a new
   frontend-owned helper module.
5. Generalize the existing specialization materialization path to compose type
   bindings with ProcRef/workflow-ref/value bindings.
6. Add fail-closed lowering/runtime-erasure checks.
7. Add focused tests, then add one imported-stdlib-facing proof that this
   substrate can serve the later `review-revise-loop` route without yet
   implementing that route.

## Acceptance Conditions

- A `defproc` with `:forall` and no semantic `:where` dependence can compile by
  specializing to a monomorphic helper before lowering.
- Generic signatures can mention type parameters inside nested
  `ProcRef[...]` and `WorkflowRef[...]` type positions.
- Equivalent call sites reuse one specialization when the deterministic
  specialization key matches and provenance obligations permit reuse.
- Generic call sites preserve effect summaries and existing inline/private
  lowering behavior after specialization.
- Non-empty `:where` clauses are represented in frontend metadata and rejected
  with a dedicated pre-constraint diagnostic rather than ignored or treated as
  runtime semantics.
- No `TypeParamRef` reaches lowered workflows, shared validation artifacts,
  Semantic IR, Executable IR, runtime state, or source-map semantic authority.
- Existing non-generic ProcRef/workflow-ref specialization tests remain valid
  without semantic weakening.

## Verification Plan

Minimum deterministic checks for the future implementation item:

- targeted frontend tests for generic `defproc` parsing, inference, and
  specialization;
- adjacent ProcRef/workflow-ref specialization regression tests;
- a lowering/serialization check that rejects leaked `TypeParamRef`;
- at least one compile-to-validated-bundle proof for a generic procedure used
  from a real workflow body;
- direct artifact/content checks proving the design-gap architecture bundle,
  work-item context, and command list were written to the required paths.
