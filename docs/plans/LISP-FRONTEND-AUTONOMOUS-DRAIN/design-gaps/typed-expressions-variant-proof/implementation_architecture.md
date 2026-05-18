# Typed Expressions And Variant Proof Implementation Architecture

## Scope

This design gap covers only the Stage 2 typed-expression slice required by the
Workflow Lisp frontend MVP:

- elaborate expression forms for `let*`, record construction, dotted field
  access, and `match`;
- resolve expression-local names against a supplied lexical environment plus
  Stage 1 type definitions;
- typecheck record construction and field access against the Stage 1
  definition AST;
- enforce variant-proof rules so variant-specific fields are available only
  inside `match` proof contexts;
- return typed expression artifacts that later workflow/procedure slices can
  reuse.

Out of scope for this tranche:

- `defworkflow`, `defproc`, `call`, `provider-result`, `command-result`, or
  any effectful expression forms;
- lowering to Core Workflow AST, Semantic Workflow IR, or Executable IR;
- `WorkflowLoader` integration or runtime execution of `.orc` files;
- macros, imports/modules, higher-order workflow refs, or standard-library
  phase procedures;
- user-visible top-level harness forms invented only for testing.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `4.3 Expressions`
  - `5.3 Records`
  - `5.4 Unions`
  - `8. Variant Proof`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `7.4 Records`
  - `7.5 Unions`
  - `10. Sequential Binding: let*`
  - `11. Pattern Matching`
  - `44. Typed Frontend AST`
  - `53. match Lowering`
  - `60. Type Validation`
  - `63. Variant Proof Validation`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`

The slice must also preserve the boundaries already established by the parser
and definition tranche:

- `orchestrator/workflow_lisp/` remains the isolated frontend package;
- Stage 1 definitions remain the only source of top-level type authority in
  this slice;
- source spans and typed diagnostics remain mandatory;
- this slice must not redefine shared concepts owned by later contracts:
  Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer
  authority, or the shared variant-proof/runtime guard model.
- this slice must not introduce inline command glue, script-owned semantic
  state, or adapter-shaped shortcuts for expression typing; if a later slice
  extends expressions with `command-result`, that work must follow the command
  adapter contract instead of embedding hidden semantics in command text.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`

### Decisions Reused

- Keep the frontend in `orchestrator/workflow_lisp/` rather than mixing Lisp
  parsing and checking into `orchestrator/workflow/`.
- Reuse the Stage 1 pipeline boundary:
  read -> syntax objects -> typed definitions -> definition validation.
- Reuse `SourcePosition`, `SourceSpan`, `SyntaxNode`, `WorkflowLispModule`,
  and `LispFrontendDiagnostic` rather than creating parallel span or error
  types.
- Keep pre-lowering slices runtime-independent and avoid `WorkflowLoader`
  integration until a later lowering slice exists.

### New Decisions In This Slice

- Add a frontend-local expression layer that is reusable by future workflow
  bodies, but do not claim a full Stage 2 module compiler yet.
- Resolve dotted authored symbols as exact lexical names first, then as
  field-access chains only when the first segment names a bound value.
- Represent variant proof as a frontend-local scoped fact set used by the type
  checker; later lowering may translate those facts into shared proof/runtime
  constructs, but this slice does not own that lowering.
- Require `match` arms to be exhaustive and type-consistent by default.

### Conflicts Or Revisions

No prior architecture decisions need revision. `WorkflowLispModule` remains a
Stage 1 definition artifact; this slice layers expression elaboration and
checking on top of it rather than mutating the Stage 1 ownership boundary.

## Ownership Boundaries

This slice owns:

- expression AST nodes for supported Stage 2 forms;
- a resolved frontend type environment derived from Stage 1 definitions;
- frontend-local proof scopes for variant narrowing during type checking;
- typed-expression checking APIs and diagnostics;
- focused tests for expression elaboration, type checking, and proof checking.

This slice intentionally does not own:

- Core Workflow AST nodes or lowering rules;
- Semantic Workflow IR or the shared TypeCatalog;
- runtime `requires_variant` guards, state layout, pointer materialization, or
  provider/command semantics;
- workflow/procedure signatures and effect checking beyond the local
  expression checker.

This slice adds no scripts, command steps, legacy adapters, or runtime-native
effects. Expression typing stays purely frontend-local so the selected gap does
not create new command-boundary debt while the command-adapter surfaces are
still out of scope.

## Proposed Package Boundary

Extend the existing package with the minimum additional surface:

```text
orchestrator/workflow_lisp/
  __init__.py
  definitions.py       # existing Stage 1 type authority
  expressions.py       # new expression AST + elaboration
  type_env.py          # new resolved frontend type environment
  typecheck.py         # new type/proof checker
```

Responsibilities:

- `definitions.py`
  - remains authoritative for parsed `defenum`, `defpath`, `defrecord`, and
    `defunion` definitions;
  - should not absorb expression logic.
- `expressions.py`
  - elaborates `SyntaxNode` roots into a frontend expression AST;
  - validates only form shape, not semantic types.
- `type_env.py`
  - resolves Stage 1 definitions into frontend-local type references and lookup
    helpers;
  - keeps this slice from embedding ad hoc dictionary lookups throughout the
    checker.
- `typecheck.py`
  - typechecks expressions against a lexical value environment and proof scope;
  - emits typed expressions plus deterministic diagnostics.
- `__init__.py`
  - exports the new expression/typecheck helpers for tests and later slices.

Do not add `compile_stage2_module()` in this tranche. Without `defworkflow`
support, a module-wide Stage 2 compiler entrypoint would imply more runtime
integration than the selected gap actually covers.

## Data Model

### Frontend Type References

Introduce frontend-local resolved type references, not a replacement for the
future shared TypeCatalog:

- `PrimitiveTypeRef(name)`
- `PathTypeRef(name, path_def)`
- `RecordTypeRef(name, record_def)`
- `UnionTypeRef(name, union_def)`
- `VariantCaseTypeRef(union_name, variant_name, variant_def)`

`FrontendTypeEnvironment` should map top-level type names to these resolved
references and expose helpers such as:

- `resolve_type(name) -> TypeRef`
- `record_field(record_type, field_name) -> TypeRef`
- `union_variant(union_type, variant_name) -> VariantCaseTypeRef`

This environment is derived entirely from `WorkflowLispModule` plus the fixed
prelude names already used in Stage 1. It must not invent new top-level type
authority.

### Expression AST

The untyped expression AST should stay small and syntax-directed:

- `NameExpr(name, span, form_path)`
- `LiteralExpr(value, literal_kind, span, form_path)`
- `FieldAccessExpr(base, fields, span, form_path)`
- `RecordExpr(type_name, fields, span, form_path)`
- `LetStarExpr(bindings, body, span, form_path)`
- `MatchExpr(subject, arms, span, form_path)`
- `MatchArm(variant_name, binding_name, body, span, form_path)`

All nodes carry the authored span and form path so later diagnostics point at
the user-facing source, not only a generated checker location.

### Typed Expressions And Proof Scope

The checker should annotate expressions with resolved types:

- `TypedExpr(expr, type_ref, span, form_path)`
- `TypedMatchArm(binding_name, variant_type, body, span, form_path)`

Variant proof stays frontend-local in this slice:

- `ValueEnvironment`
  - lexical value names mapped to resolved type refs;
- `ProofScope`
  - current proven variant facts keyed by subject name.

`ProofScope` is intentionally smaller than the future shared proof graph. It is
only the local evidence needed to accept or reject variant-specific field
access during frontend checking.

## Elaboration Model

This slice must not add fake author-facing top-level forms just to exercise
expressions in tests. The elaboration API should therefore accept an existing
`SyntaxNode` root for one expression. Tests can build that `SyntaxNode` from
`read_sexpr_text(...)` plus a caller-supplied `form_path`.

### Supported Forms

- literals: strings, ints, bools;
- symbols:
  - exact lexical name references;
  - dotted field access chains;
- `(record Type :field expr ...)`;
- `(let* ((name expr) ...) body)`;
- `(match subject ((VARIANT binding) body) ...)`.

### Dotted Symbol Resolution

The reader already preserves dotted atoms as `SymbolAtom` values. Expression
elaboration should not split every dotted symbol eagerly because future slices
will also need dotted qualified names.

Resolution rule:

1. if the full symbol token is bound in the lexical environment, elaborate it
   as `NameExpr`;
2. otherwise, if the token contains `.` and the first segment is a bound value,
   elaborate it as `FieldAccessExpr(base=<first-segment>, fields=<rest>)`;
3. otherwise, leave it as an unresolved `NameExpr` and let type checking emit
   the unknown-name diagnostic.

This keeps Stage 2 compatible with future module/import work instead of making
field access syntax impossible to evolve.

## Typechecking And Proof Rules

### Initial Value Environment

Because this slice excludes `defworkflow`, the checker must accept an explicit
initial lexical environment from its caller. Tests and later workflow-body
elaboration can provide bindings such as:

- `attempt : ImplementationAttempt`
- `result : ChecksResult`
- `count : Int`

The checker must not pretend top-level value definitions exist yet.

### `let*`

Rules:

- bindings are checked in source order;
- each binding is available to later bindings and the body;
- duplicate names within the same binding list are rejected;
- shadowing outer names in nested `let*` forms is allowed because it is normal
  lexical scope.

### Record Construction

`(record Type :field expr ...)` requires:

- `Type` resolves to a `RecordTypeRef`;
- every required field appears exactly once;
- no unknown fields appear;
- each field expression type matches the declared field type exactly.

This slice should not add structural subtyping or contract weakening rules.
Exact declared field types are sufficient for the MVP expression layer.

### Field Access

Field access is valid when:

- the base expression resolves to a record-like type and the field exists; or
- the base resolves to a union and the current proof scope narrows that union
  to a variant that contains the field.

The checker should support both of these inside a `match` arm:

- `completed.execution-report`
- `attempt.execution-report`

That means the proof scope must narrow the matched subject itself, not only the
arm binding alias.

Outside proof, variant-specific field access fails with `variant_ref_unproved`.
Inside a proof for the wrong variant, it fails with `variant_ref_wrong_variant`.

### `match`

Rules:

- the subject must resolve to `UnionTypeRef`;
- every variant must appear exactly once unless a later slice adds explicit
  partial-match syntax;
- each arm introduces:
  - a proof fact that the matched subject is in the arm variant;
  - a lexical binding whose type is `VariantCaseTypeRef`;
- proof facts do not escape the arm;
- all arm bodies must resolve to the same type.

This slice should reject attempts to use string comparisons or ad hoc status
tests as variant proof. Variant availability comes from `match` only.

## Diagnostics

Reuse existing or already-specified error codes whenever the meaning matches:

- `type_unknown`
- `type_mismatch`
- `record_field_unknown`
- `record_field_missing`
- `union_variant_unknown`
- `union_match_non_exhaustive`
- `variant_ref_unproved`
- `variant_ref_wrong_variant`

Add new frontend-local codes only where Stage 1 codes are too coarse:

- `expression_form_unknown`
- `binding_duplicate`
- `match_subject_not_union`

Diagnostic requirements:

- point at the authored field/variant/access form span;
- include the surrounding `form_path`;
- for dotted field access, use the full symbol span because the reader does not
  tokenize segments independently;
- preserve deterministic wording close to the existing Stage 1 diagnostic
  style.

## Integration Strategy

This slice remains pre-lowering. The intended consumer sequence is:

1. `compile_stage1_module(path)` produces `WorkflowLispModule`;
2. `FrontendTypeEnvironment.from_module(module)` resolves type refs;
3. `elaborate_expression(...)` turns one `SyntaxNode` into expression AST;
4. `typecheck_expression(...)` returns typed expressions or diagnostics.

The later `defworkflow`/lowering slice can reuse these helpers directly when it
adds workflow parameters, return-type checking, and Core AST lowering. That
next slice should translate proven union access into shared proof/lowering
constructs instead of re-checking variant access from scratch.

## Test Strategy

Add focused tests rather than pretending the runtime can execute Stage 2 forms.

Proposed test modules:

- `tests/test_workflow_lisp_expressions.py`
  - positive/negative `let*` elaboration;
  - record construction exactness;
  - field access through records;
  - dotted-symbol resolution precedence.
- `tests/test_workflow_lisp_variant_proofs.py`
  - exhaustive `match` requirements;
  - accepted access by arm binding and by narrowed subject;
  - rejected access outside proof;
  - rejected access under the wrong proven variant;
  - arm result type mismatch.

Fixture style:

- reuse `.orc` module fixtures from Stage 1 to define records and unions;
- keep expression samples as inline S-expressions parsed with
  `read_sexpr_text(...)` so the tests do not invent fake top-level language
  forms;
- keep assertions focused on diagnostic codes, spans, and inferred types rather
  than prose snapshots.

## Implementation Sequence

1. Add `type_env.py` with resolved frontend type references over
   `WorkflowLispModule`.
2. Add `expressions.py` with syntax elaboration for the bounded Stage 2 forms.
3. Add `typecheck.py` for literals, names, record construction, and record
   field access.
4. Extend `typecheck.py` with `match` arm checking and variant proof scope.
5. Export the stable helpers from `__init__.py`.
6. Add focused expression and proof tests, then keep Stage 1 regression tests
   passing.

## Acceptance Conditions

This slice is complete when:

- Stage 2 expression elaboration accepts only the bounded forms in this
  architecture and rejects unknown expression forms deterministically;
- record construction and dotted field access typecheck against Stage 1
  definition authority rather than ad hoc dictionaries;
- `match` creates frontend-local proof scopes that allow variant-only field
  access inside the correct arm and reject it outside proof;
- typed-expression helpers remain reusable by later workflow/procedure slices
  without requiring `WorkflowLoader` or runtime integration;
- focused expression/proof tests pass alongside Stage 1 frontend regression
  tests.

## Verification Expectations

Implementation should verify this slice with narrow pytest selectors first:

- collect-only on the new expression/proof test modules;
- focused execution of the new expression and proof suites;
- a final frontend regression run that keeps the Stage 1 reader, definition,
  and diagnostic tests passing with the new Stage 2 helpers.

## Risks And Mitigations

- Risk: dotted symbol parsing hard-codes field access and blocks later module
  qualification work.
  Mitigation: resolve exact lexical names first and split on `.` only when the
  first segment names a bound value.

- Risk: this slice silently redefines the future shared TypeCatalog or proof
  graph.
  Mitigation: keep `FrontendTypeEnvironment` and `ProofScope` explicitly local
  to frontend checking and do not serialize them as shared IR.

- Risk: expression support expands into effectful workflow statements before
  workflow signatures exist.
  Mitigation: keep `call`, `provider-result`, `command-result`, and lowering
  out of the AST and out of the public API for this tranche.

- Risk: proof availability is attached only to the arm binding and not to the
  matched subject, making later lowering awkward.
  Mitigation: narrow both the matched subject and the arm binding within each
  arm from the start.
