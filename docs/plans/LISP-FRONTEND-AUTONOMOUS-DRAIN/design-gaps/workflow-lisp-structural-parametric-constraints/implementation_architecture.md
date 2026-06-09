# Workflow Lisp Structural Parametric Constraints Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-structural-parametric-constraints`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_mvp_specification.md`

## Scope

This slice covers exactly the first-tranche structural parametric constraint
surface selected by the current drain state:

- implement `defproc :where` semantics on top of the already-landed
  compile-time `:forall` / specialization substrate;
- support the owner-doc first-tranche constraint vocabulary only:
  `is-record`,
  `is-union`,
  `has-field`,
  `has-union-variant`,
  and `has-shared-union-field`;
- validate those constraints against resolved concrete call-site types before a
  parametric specialization is accepted;
- preserve the accepted first-tranche pipeline:
  constraint check -> instantiate monomorphic helper -> typecheck instantiated
  helper -> lower;
- add only the minimum capability plumbing required so
  `has-shared-union-field` permits branch-free access to the constrained field
  while ordinary variant proof remains unchanged;
- keep effects, source maps, command-boundary visibility, and runtime-erasure
  rules unchanged for the generated monomorphic helper.

Out of scope for this slice:

- new `:forall` parsing, type-parameter inference, or generic specialization
  identity beyond the already-owned substrate;
- generic `defworkflow`, runtime type values, runtime multiple dispatch, or
  runtime-carried ProcRef / WorkflowRef / provider / prompt values;
- ordinary stdlib `review-revise-loop` authoring in `std/phase.orc`;
- removal of the temporary `__stdlib-specialization__ phase-review-loop`
  compatibility bridge or the review-loop-specific validator/lowerer;
- loop exhaustion projection, caller-owned terminal construction, or review-loop
  parity promotion;
- new scripts, command adapters, runtime-native effects, or changes to the
  command-adapter policy.

This is a bounded implementation architecture for the selected structural
constraint surface only. It does not replace the parent frontend design, the
MVP baseline, or the broader review/revise stdlib integration design.

## Problem Statement

The current checkout has reached an intermediate state:

1. `defproc` already parses `:forall` and `:where` in the accepted header
   order.
2. `FrontendTypeEnvironment` already carries `TypeParamRef`,
   substitution helpers, and monomorphic-boundary rejection.
3. `procedure_typecheck.py` already infers concrete type bindings for generic
   calls and queues deterministic monomorphic specializations.
4. Non-empty `:where` clauses still hard-fail with
   `unsupported_parametric_constraint_surface`.
5. `std/phase.orc` still exports `review-revise-loop` through
   `(__stdlib-specialization__ phase-review-loop ...)`, and
   `typecheck.py` still contains a review-loop-specific union contract
   validator.

That leaves the target design blocked in two concrete ways.

First, the compiler still lacks the reusable type-system mechanism that should
own caller-shape requirements. The only live behavior is "parse `:where`, then
reject it," so stdlib code cannot express the structural preconditions that a
future ordinary generic `review-revise-loop` needs.

Second, the currently retained `:where` metadata is too shallow for the full
first-tranche owner-doc surface. `ProcedureConstraintSyntax.args` stores only
flat symbol strings, but `has-union-variant` must be able to represent
optional field requirements attached to the constrained variant.

The selected gap is therefore narrower than "make review-revise-loop ordinary
stdlib code" and larger than "stop rejecting `:where`":

- normalize the owner-doc constraint surface into frontend-owned syntax and
  checking structures;
- evaluate constraints on concrete call-site types before specialization is
  accepted;
- feed only the proven capabilities that the instantiated helper actually
  needs into ordinary post-specialization typechecking;
- leave bridge removal and stdlib review-loop migration to later slices.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `12. Structural Constraint Dependency`
  - `24. Incremental Implementation Plan`
  - `Stage 9 - Minimal Structural Generics`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `7. Types`
  - `8.8 defproc`
  - `11. Pattern Matching`
  - `16. Effect System`
  - `63. Variant Proof Validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and shared
  runtime behavior under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- preserve the owner-seam split: procedure-call typechecking behavior lands
  through `procedure_typecheck.py`, specialization materialization through
  `procedure_specialization.py`, and runtime-boundary procedure lowering through
  `lowering/procedures.py`;
- keep generated procedures monomorphic before Core Workflow AST, Semantic IR,
  Executable IR, runtime plans, and persisted state are constructed;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep match proof authoritative for variant-specific fields; structural
  constraints must not become a second proof system that bypasses `match`.

`docs/design/workflow_command_adapter_contract.md` is authoritative here even
though this slice adds no new adapter. Structural constraints must not become a
loophole for hiding command semantics behind generic helpers. Effectful generic
fixtures still have to lower through the existing visible
`provider-result` / `command-result` / certified-adapter surfaces.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the staged frontend pipeline and package ownership split.
- Reuse the compile-time-only `TypeParamRef` model, type substitution helpers,
  specialization identity rules, and runtime-erasure boundary from the
  parametric `defproc` substrate.
- Reuse the owner-seam split so new procedure semantics land in
  `procedure_typecheck.py`,
  `procedure_specialization.py`,
  and `lowering/procedures.py`
  rather than extending the public facades directly.
- Reuse Stage 2 variant-proof rules: variant-only fields still require
  proof-bearing `match` branches, and `has-shared-union-field` may not weaken
  that rule.
- Reuse the current provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  `LoweringOrigin`,
  and `LoweringOriginMap`.
- Reuse the command-boundary classification and shared-validation handoff for
  effectful generic procedures.

### New Decisions In This Slice

- Add one dedicated frontend-owned constraint semantics module:
  `orchestrator/workflow_lisp/parametric_constraints.py`.
- Replace flat `:where` argument strings with syntax-preserving constraint
  metadata that can represent the full first-tranche owner-doc surface,
  including `has-union-variant` field requirements.
- Check constraints against resolved concrete call-site types immediately after
  generic type inference and before a specialization request is accepted.
- Represent the result of successful checking as a small compile-time
  capability set; only `has-shared-union-field` contributes a new field-access
  capability beyond what ordinary concrete typing already provides.
- Treat first-tranche "assignment-compatible" field checks as exact resolved
  `TypeRef` compatibility. This slice does not introduce structural widening,
  coercion, or subtyping.
- Keep unknown or future constraint spellings out of tranche one. They fail
  with typed diagnostics instead of silently becoming metadata.

### Conflicts Or Revisions

The parametric `defproc` specialization substrate intentionally retained
`:where` as metadata for a later slice. The current representation is too weak
for the accepted first-tranche syntax because
`ProcedureConstraintSyntax.args: tuple[str, ...]`
cannot encode `has-union-variant` field requirements. This slice revises that
representation narrowly:

- `procedures.py` remains the owner of `defproc` header parsing and clause-order
  validation;
- the stored `:where` payload becomes syntax-preserving or structured enough to
  represent the owner-doc constraint surface;
- semantic normalization and checking move to the new
  `parametric_constraints.py` owner module.

The current hard failure
`unsupported_parametric_constraint_surface`
is also revised narrowly:

- non-empty `:where` no longer fails by default;
- only malformed clauses, unknown constraint names, or unsatisfied concrete
  structural requirements fail.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- the first-tranche structural constraint vocabulary implementation for
  generic `defproc`;
- normalization of parsed `:where` syntax into typed constraint-check records;
- concrete-type structural checking for
  `is-record`,
  `is-union`,
  `has-field`,
  `has-union-variant`,
  and `has-shared-union-field`;
- compile-time capability materialization for successful constraints;
- the small typecheck hook that lets
  `has-shared-union-field`
  authorize branch-free access to the constrained field only;
- focused diagnostics and tests for satisfied, malformed, unknown, and
  unsatisfied constraints.

This slice intentionally does not own:

- the authored `:forall` / specialization substrate itself;
- generic `defworkflow`;
- stdlib `review-revise-loop` authoring or bridge removal;
- review-loop result projection, exhaustion routing, or parity reporting;
- runtime adapter policy, new scripts, or runtime-native effects;
- shared runtime, validation, Core AST, Semantic IR, or source-map schema
  redesign.

## Current Checkout Facts

- `orchestrator/workflow_lisp/procedures.py` already parses `:forall` and
  `:where`, but `ProcedureConstraintSyntax` stores only flat string args.
- `orchestrator/workflow_lisp/type_env.py` already provides
  `TypeParamRef`,
  `substitute_type_params(...)`,
  and `ensure_no_type_params(...)`.
- `orchestrator/workflow_lisp/procedure_typecheck.py` already infers concrete
  type bindings and enqueues `PendingParametricProcedureSpecialization`, but it
  still rejects any non-empty `where_clauses` with
  `unsupported_parametric_constraint_surface`.
- `orchestrator/workflow_lisp/procedure_specialization.py` already owns the
  deterministic specialization substrate; this slice should extend it rather
  than duplicate it.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` still exports
  `review-revise-loop` as a macro over
  `__stdlib-specialization__ phase-review-loop`.
- `orchestrator/workflow_lisp/typecheck.py` still owns the special
  review-loop result-contract validator that later slices are intended to
  retire.
- The owner-seam split already exists on disk:
  `procedure_typecheck.py`,
  `procedure_specialization.py`,
  and `lowering/procedures.py`
  are present and under the 2,000-line cap, while
  `typecheck.py`
  remains a large general-expression consumer.

## Proposed Package Boundary

The narrowest implementation shape is:

```text
orchestrator/workflow_lisp/
  procedures.py                # keep parsing/clause-order checks; store richer where metadata
  parametric_constraints.py    # new owner for normalized constraints + concrete checks
  procedure_typecheck.py       # infer bindings, invoke constraint checks, enqueue validated specializations
  procedure_specialization.py  # carry validated capabilities into generated monomorphic helpers
  type_env.py                  # exact TypeRef compatibility + field/variant lookup helpers
  typecheck.py                 # consume shared-field capabilities during field-access checking
  lowering/procedures.py       # unchanged runtime-erasure boundary for monomorphic helpers
```

Responsibilities:

- `procedures.py`
  - keep `defproc` header parsing and existing diagnostics;
  - preserve the owner-doc clause order;
  - stop flattening all `:where` args to bare strings.
- `parametric_constraints.py`
  - own first-tranche constraint names and arity/shape validation;
  - normalize raw clause syntax into typed `StructuralConstraint` records;
  - check concrete `TypeRef` bindings and return either satisfied capability
    records or typed diagnostics.
- `procedure_typecheck.py`
  - keep generic type inference as the call-site authority;
  - replace the blanket unsupported-surface rejection with
    `parametric_constraints.check_constraints(...)`;
  - pass the resulting constraint capability summary into the specialization
    request.
- `procedure_specialization.py`
  - keep deterministic specialization identity unchanged;
  - attach validated structural capabilities to the generated monomorphic
    procedure metadata needed by post-specialization typing;
  - reject any attempt to construct a specialization without first satisfied
    constraints.
- `type_env.py`
  - add only the exact resolved-type compatibility helpers needed by the first
    tranche;
  - do not introduce structural subtyping or broad assignability.
- `typecheck.py`
  - accept a narrow structural-capability scope for branch-free field access;
  - keep `match` proof rules authoritative for all variant-specific fields.

Do not add a second generic checker or a new runtime-facing constraint system.

## Constraint Semantics

### Syntax Normalization

The first-tranche surface keeps the owner-doc spellings exactly:

- `(T is-record)`
- `(T is-union)`
- `(T has-field field Type)`
- `(T has-union-variant VARIANT)`
- `(T has-union-variant VARIANT (field Type) ...)`
- `(T has-shared-union-field field Type)`

Normalization rules:

- `subject_name` must reference a declared `:forall` type parameter.
- Unknown constraint names fail closed.
- `has-field` and `has-shared-union-field` take exactly two symbol arguments:
  field name and type name.
- `has-union-variant` takes one variant symbol plus zero or more two-symbol
  field-pair lists.
- Nested arbitrary expressions, schemas, trait aliases, or runtime values are
  out of scope and fail as malformed constraint syntax.

### Concrete Checking

Constraint checking runs after generic type inference resolves concrete
bindings:

1. infer one concrete `TypeRef` for each declared type parameter;
2. normalize each `:where` clause against the authored generic definition;
3. resolve referenced field and type names against the existing frontend type
   environment;
4. validate each constraint against the concrete `TypeRef`;
5. if all succeed, produce a deterministic `ConstraintCapabilitySet`;
6. only then accept the specialization request.

Per-constraint rules:

- `is-record`
  - succeeds only for `RecordTypeRef`.
- `is-union`
  - succeeds only for `UnionTypeRef`.
- `has-field`
  - succeeds only for `RecordTypeRef` with the named field;
  - the field type must be exactly compatible with the referenced concrete
    `TypeRef`.
- `has-union-variant`
  - succeeds only for `UnionTypeRef` with the named variant;
  - when field pairs are present, the variant must declare each field with an
    exactly compatible concrete `TypeRef`.
- `has-shared-union-field`
  - succeeds only for non-empty `UnionTypeRef`;
  - every declared variant must include the field;
  - every such field type must be exactly compatible with the referenced
    concrete `TypeRef`;
  - success grants branch-free access to that field only.

This slice deliberately does not add subset construction, field renaming,
constructor mapping, or arbitrary caller-owned union construction.

## Typechecking Integration And Proof Boundary

Most first-tranche constraints are specialization gates only:

- `is-record`,
  `is-union`,
  `has-field`,
  and `has-union-variant`
  ensure the concrete instantiated helper is meaningful, but ordinary concrete
  post-specialization typechecking already knows how to check record fields and
  `match` over concrete unions.

`has-shared-union-field` is the only constraint that requires a new typing
capability after specialization, because ordinary direct union field access is
still proof-gated today.

The integration rule is:

- successful `has-shared-union-field` checks emit a compile-time capability
  bound to lexical values whose type came from the constrained type parameter;
- field-access typing may use that capability only for the one named field;
- the resulting projected value is typed as the referenced concrete field type;
- no capability grants access to variant-specific fields or proves which
  variant is present;
- `match` remains the only way to establish variant-specific proof.

The capability carrier should stay lightweight:

- do not redesign the whole typechecker around a new global context object in
  this slice;
- thread a narrow structural-capability scope alongside the existing
  proof/value environments at the points that already typecheck procedure
  bodies and `let*` bindings.

## Diagnostics

This slice replaces the blanket unsupported-surface failure with typed
constraint diagnostics:

- malformed clause shape stays under the existing
  `procedure_where_clause_invalid`
  family owned by `procedures.py`;
- unknown first-tranche constraint names should raise
  `unknown_parametric_constraint`;
- malformed constraint arguments after header parsing should raise
  `parametric_constraint_arguments_invalid`;
- concrete shape mismatches should raise
  `unsatisfied_structural_constraint`;
- variant-only field access outside proof remains
  `variant_field_without_proof`;
- unresolved type parameters and specialization cycles remain owned by the
  existing parametric specialization substrate.

Primary blame should stay on authored source:

- malformed or unknown constraint syntax points at the `:where` clause;
- unsatisfied structural requirements point at the call site while preserving
  the generic definition / clause provenance through the existing diagnostic
  metadata;
- no shared-validation or runtime diagnostic should be needed for these
  failures because the check must happen before lowering.

## Test Strategy

Primary test surface:

- `tests/test_workflow_lisp_procedures.py`

Secondary regression surfaces:

- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_phase_stdlib.py`

Required fixture families:

- positive generic fixtures for:
  `is-record`,
  `is-union`,
  `has-field`,
  `has-union-variant`,
  and `has-shared-union-field`;
- a generic union fixture proving
  `has-shared-union-field`
  allows branch-free access to the constrained field while variant-specific
  fields still fail outside `match`;
- an effectful generic fixture with ProcRef-selected behavior to prove
  constraint checking composes with visible provider/command effects without
  changing command-boundary semantics;
- negative fixtures for:
  malformed field-pair syntax,
  unknown constraint names,
  missing record fields,
  wrong field types,
  missing union variants,
  variant field requirements that do not match the concrete variant,
  non-shared union fields,
  and unsatisfied constraints on otherwise inferable type bindings;
- one regression that the current imported stdlib review-loop bridge still
  compiles unchanged after this slice, because bridge retirement is not owned
  here.

## Acceptance Conditions

- generic `defproc` definitions can use the owner-doc first-tranche structural
  spellings without hitting
  `unsupported_parametric_constraint_surface`;
- unsatisfied constraints fail before specialization is accepted and before
  lowering begins;
- successful specializations remain monomorphic and leak no `TypeParamRef`
  values to lowered runtime surfaces;
- `has-shared-union-field` grants only branch-free access to the constrained
  field and does not weaken `match` proof rules;
- one non-review-loop fixture proves the mechanism independent of
  `review-revise-loop`;
- the slice does not remove or redefine the current
  `__stdlib-specialization__ phase-review-loop`
  route or the review-loop-specific validator;
- command-result / certified-adapter visibility remains unchanged for effectful
  generic fixtures;
- source maps and specialization identity remain deterministic because this
  slice only extends compile-time checking, not runtime lowering identity.
