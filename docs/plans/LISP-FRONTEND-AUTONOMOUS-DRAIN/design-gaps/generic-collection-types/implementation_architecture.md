# Generic Collection Types Implementation Architecture

## Scope

This design gap covers only the bounded generic collection-type slice selected
for the Workflow Lisp frontend:

- add first-class authored type-expression support for `Optional[T]`,
  `List[T]`, and `Map[K,V]`;
- resolve those authored types into frontend-local type refs without replacing
  the existing Stage 1 definition authority or the later shared Semantic IR
  contracts;
- define the exact structured-result lowering surface for collection-typed
  fields in `output_bundle`, `variant_output`, and reusable-state contracts;
- keep collection handling source-mapped and deterministic across definition
  validation, type resolution, contract lowering, and shared contract
  validation;
- state the explicit lowering limits so collection support does not silently
  widen workflow-boundary transport, proof semantics, or runtime behavior.

Out of scope for this tranche:

- new list or map literal expression forms, collection mutation helpers, or a
  broader pure-expression library;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, or runtime state persistence;
- workflow-boundary flattening support for collection-typed `defworkflow`
  params or returns;
- collection items or map values that are records, unions, workflow refs,
  providers, prompts, or opaque `Json` values;
- report parsing, pointer-as-state, inline semantic shell/Python glue, or new
  command-adapter policy.

This is an implementation architecture for exactly the selected
`generic-collection-types` gap. It does not replace the product design in
`docs/design/workflow_lisp_frontend_specification.md`.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `7.6 Optional And List Types`
  - `22. Provider Result`
  - `23. Command Result`
  - `38. Intermediate Overview`
  - `44. Typed Frontend AST`
  - `54. provider-result Lowering`
  - `60. Type Validation`
  - `62. Contract Validation`
  - `98. Metrics Tests`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `5. Type Model`
  - `7. Provider And Command Results`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_type_catalog.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by prior
implementation architectures and the current checkout:

- keep `orchestrator/workflow_lisp/` frontend-owned and keep shared contract
  parsing/runtime validation under `orchestrator/contracts/` and
  `orchestrator/workflow/`;
- reuse the staged pipeline:
  read -> syntax -> definitions/modules -> type environment -> typecheck ->
  lowering -> shared validation;
- reuse `WorkflowLispModule`, `RecordField`, `WorkflowSignature`,
  `LispFrontendDiagnostic`, `FrontendTypeEnvironment`, and the existing
  structured-result lowering seam in `contracts.py`;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- avoid inventing a second type system or fabricating unavailable shared IR
  contracts.

`docs/steering.md` is empty in this checkout. That does not widen scope. The
selector bundle, architecture target contract, existing architecture index, and
current repo evidence remain the effective steering surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defschema-reusable-field-schemas/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/implementation_architecture.md`

### Decisions Reused

- Reuse the existing frontend package ownership split and staged compile
  pipeline.
- Reuse `SourcePosition`, `SourceSpan`, recursive syntax metadata,
  `LispFrontendDiagnostic`, and existing subject/origin remapping instead of
  inventing parallel provenance.
- Reuse `RecordField.type_name` and other authored type-name carriers as the
  frontend surface, rather than replacing definition AST nodes with a new
  authored type tree.
- Reuse `FrontendTypeEnvironment` and `contracts.py` as the only frontend-owned
  authorities for type resolution and structured-result contract derivation.
- Reuse the workflow-boundary flattening slice’s rule that lowered workflow
  boundaries stay a bounded compatibility seam and do not become the semantic
  authority for frontend typing.

### New Decisions In This Slice

- Generalize the current WorkflowRef-only bracket parsing into one compiler
  helper for authored type expressions that preserves the existing symbol-atom
  reader boundary.
- Add frontend-local `OptionalTypeRef`, `ListTypeRef`, and `MapTypeRef`
  without redefining shared TypeCatalog or Semantic IR contracts.
- Support collection typing in definition fields, local/frontend type
  environments, typed expressions, structured-result contracts, and reusable
  state contract metadata.
- Keep workflow-boundary params/returns and `WorkflowRef[...]` transport free
  of collection types in this slice; collection-bearing workflow boundaries
  remain a separate follow-on gap.
- Lower collections only when their recursively contained leaf values are
  already lowerable shared contract primitives:
  `String`,
  `Int`,
  `Bool`,
  enums,
  and relpaths.

### Conflicts Or Revisions

The parser/core slice and current checkout special-case only `WorkflowRef[...]`
as a bracket-bearing type atom. This slice revises that implementation shape
narrowly:

- the reader still emits `SymbolAtom` for authored type references;
- bracket-balanced type atoms become a general reader capability instead of a
  `WorkflowRef[...]` one-off;
- type-expression parsing moves behind one shared frontend helper so
  `WorkflowRef[...]`, `Optional[...]`, `List[...]`, and `Map[..., ...]` do not
  each invent their own bracket parser.

The workflow-boundary flattening slice intentionally kept boundary transport
flat and bounded. This slice does not revise that decision. It makes the
collection-type rejection explicit at workflow boundaries rather than silently
falling through to existing scalar/record logic.

## Ownership Boundaries

This slice owns:

- authored generic type-expression parsing for type-position symbol atoms;
- frontend-local collection type refs and recursive type-resolution helpers;
- collection-type validation rules and diagnostics in definition/workflow
  preflight;
- lowering of collection-typed structured-result fields into recursive shared
  JSON-bundle field schemas;
- shared JSON-bundle contract parsing/validation for those recursive collection
  field schemas;
- prompt-contract rendering for collection field schemas;
- focused tests for reader support, type resolution, structured-result
  lowering, shared bundle validation, and boundary rejection.

This slice intentionally does not own:

- new list/map literal syntax or collection operations in authored expressions;
- workflow-boundary transport for collection types;
- new shared Core AST or Semantic IR surfaces;
- runtime-native effects, command-adapter policy, pointer authority, variant
  proof, or report-authority behavior;
- collection items or map values that are records, unions, workflow refs,
  providers, prompts, or opaque `Json`.

## Current Checkout Facts

The current repo evidence shows the selected gap is still real and specific:

- `orchestrator/workflow_lisp/reader.py` special-cases `WorkflowRef[` and
  otherwise rejects `[` and `]` in Stage 1 atoms, so `Optional[...]`,
  `List[...]`, and `Map[..., ...]` are not lexically readable today;
- `orchestrator/workflow_lisp/definitions.py` accepts only symbol-shaped field
  type references and preserves them as raw `type_name` strings;
- `orchestrator/workflow_lisp/type_env.py` resolves plain names plus the
  dedicated `WorkflowRef[...]` grammar and exposes no collection `TypeRef`
  family;
- `orchestrator/workflow_lisp/compiler.py` definition validation still treats
  field types as direct name membership checks with one `WorkflowRef[...]`
  escape hatch;
- `orchestrator/workflow_lisp/contracts.py` lowers only scalar/enum/relpath
  leaves, nested records by flattening, and unions by discriminant/variant
  field groups;
- `orchestrator/contracts/output_contract.py` already supports optional
  top-level fields via `required: false`, but it has no recursive schema model
  for lists, maps, or typed optional values that should parse to `None`.

The gap is therefore not a full type-system rewrite. It is the missing
compiler-owned type-expression layer and the missing recursive structured-bundle
contract support for collections.

## Proposed Package Boundary

Keep ownership in the existing frontend and shared contract packages:

```text
orchestrator/workflow_lisp/
  compiler.py
  contracts.py
  diagnostics.py
  reader.py
  type_env.py
  type_expressions.py   # new

orchestrator/contracts/
  output_contract.py
  prompt_contract.py
```

Responsibilities:

- `type_expressions.py`
  - parse raw authored type-name strings into a small recursive type-expression
    tree;
  - support named types, `WorkflowRef[...]`, `Optional[...]`, `List[...]`, and
    `Map[..., ...]`;
  - own bracket balancing, comma splitting, and top-level arrow splitting for
    type-position strings.
- `reader.py`
  - generalize bracket-balanced type-atom reading so any type expression that
    starts with an identifier and enters `[` can be preserved as one symbol
    atom with one authored span.
- `type_env.py`
  - resolve parsed type expressions into frontend-local `TypeRef`s;
  - add recursive helpers for collection types;
  - keep imported-type resolution on named inner references, not on whole raw
    collection strings.
- `compiler.py`
  - replace raw string membership checks for field types with parsed
    type-expression validation;
  - reject collection types in workflow-boundary positions in this slice.
- `contracts.py`
  - derive recursive structured-result field schemas for supported collection
    leaves;
  - reject unsupported collection element/value types deterministically.
- `output_contract.py`
  - validate recursive `optional`, `list`, and `map` field schemas against JSON
    bundle values and return parsed Python values.
- `prompt_contract.py`
  - render recursive field schema instructions so provider/command prompts show
    the real contract the runtime will validate.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow/` shared validation and runtime modules

## Data Model

### Authored Type Expressions

Add one frontend-local parsed representation for raw type-position strings:

- `NamedTypeExpr(name)`
- `WorkflowRefTypeExpr(param_types, return_type)`
- `OptionalTypeExpr(item_type)`
- `ListTypeExpr(item_type)`
- `MapTypeExpr(key_type, value_type)`

Rules:

- the reader still hands later phases one raw symbol token and one authored
  span;
- `type_expressions.py` parses only in type positions, not in ordinary
  expression positions;
- diagnostics point at the full type-atom span because the current reader does
  not preserve sub-token spans for bracket contents.

### Resolved Collection Type Refs

Extend `TypeRef` with:

- `OptionalTypeRef(item_type_ref)`
- `ListTypeRef(item_type_ref)`
- `MapTypeRef(key_type_ref, value_type_ref)`

Resolution rules:

- `Optional[T]` resolves recursively through the same inner-type resolver used
  for fields and workflow refs;
- `List[T]` resolves recursively through the same inner-type resolver;
- `Map[K,V]` requires `K` to resolve to `PrimitiveTypeRef(name="String")` in
  this slice;
- imported or module-qualified names inside collection args resolve through
  `ModuleImportScope` one inner name at a time;
- `WorkflowRef[...]` may continue to appear as a standalone type, but it may
  not appear nested inside collections.

### Recursive Structured Field Schema

Add one recursive field-schema vocabulary for structured-result contracts:

- scalar/enum/relpath leaf schemas remain unchanged;
- optional field schema:
  - `type: optional`
  - `item: <recursive schema>`
- list field schema:
  - `type: list`
  - `items: <recursive schema>`
- map field schema:
  - `type: map`
  - `keys: {type: string}`
  - `values: <recursive schema>`

This schema is used only for `output_bundle`, `variant_output`, and derived
reusable-state metadata in this slice. It is not a workflow-boundary surface.

## Parsing And Resolution Pipeline

### Reader Change

Replace `_read_workflow_ref_type_atom()` with a generalized bracket-balanced
type-atom reader:

1. if the current token begins with an identifier and the next type-position
   delimiter is `[`, read until the matching closing `]`;
2. allow whitespace, commas, and `->` inside the balanced brackets;
3. return one `SymbolAtom` containing the raw authored text exactly as written.

This keeps the Stage 1 reader boundary intact while making generic type atoms
possible.

### Type-Expression Parsing

`type_expressions.py` should parse raw strings only when later stages ask for a
type reference. It should not alter the syntax or definition AST.

Required helpers:

- `parse_type_expression(text, span, form_path) -> ParsedTypeExpr`
- `split_top_level_args(text) -> list[str]`
- `top_level_arrow_index(text) -> int | None`

This reuses the existing workflow-ref parsing ideas but centralizes them in one
module instead of scattering bracket parsing across `reader.py`, `type_env.py`,
and `compiler.py`.

### Definition And Workflow Validation

Replace direct string membership checks in `compiler.py` with parsed
type-expression validation:

- named types still resolve against prelude, local definitions, and imported
  bindings;
- collection heads must have exact arity:
  - `Optional` -> 1 arg
  - `List` -> 1 arg
  - `Map` -> 2 args
- `Map` keys must be `String`;
- schema names remain forbidden in any nested type position;
- unknown generic heads emit `type_expression_invalid`, not `type_unknown`.

## Lowering And Validation Limits

### Supported Lowerable Collection Shapes

This slice lowers collections only when the recursively contained leaf types
are already lowerable shared contract primitives:

- `String`
- `Int`
- `Bool`
- enums
- relpaths
- `Optional[...]`, `List[...]`, and `Map[String, ...]` recursively composed of
  those leaves

Examples allowed in structured results:

- `Optional[String]`
- `List[Int]`
- `Map[String, ReviewDecision]`
- `List[Optional[Path.execution-report]]`

### Explicitly Unsupported Shapes

The compiler must reject, with dedicated diagnostics, collections that contain:

- `RecordTypeRef`
- `UnionTypeRef`
- `WorkflowRefTypeRef`
- `Provider`
- `Prompt`
- `Json`
- `Map` keys other than `String`

Recommended diagnostics:

- `type_expression_invalid`
- `collection_key_type_invalid`
- `collection_element_type_unsupported`
- `workflow_boundary_collection_unsupported`

Reuse existing diagnostics where they already fit:

- `type_unknown`
- `schema_used_as_type`
- `json_surface_unsupported`
- `workflow_boundary_type_invalid`

### Workflow-Boundary Rule

Collection types are out of scope for workflow-boundary transport in this
slice. `defworkflow` params, returns, and `WorkflowRef[...]` signatures must
reject them explicitly.

Reason:

- the workflow-boundary flattening slice intentionally bounded the current
  compatibility seam to scalar/relpath leaves, recursively flattened records,
  and the existing union-return projection;
- adding collection transport would require a second boundary revision and call
  surface change that is not the selected gap.

## Structured-Contract Integration

### Contract Derivation

`contracts.py` should keep record and union lowering shapes, but its field
schema derivation becomes recursive:

- record flattening still emits one top-level field spec per authored leaf
  path;
- if that leaf type is a collection, the field spec carries the recursive
  schema instead of a scalar/relpath-only type;
- union shared-field and variant-field derivation use the same recursive field
  schema helper.

### Shared Validation

`output_contract.py` should validate recursive collection specs as follows:

- `optional`
  - missing JSON pointer or explicit JSON `null` -> parsed value `None`;
  - present non-null value -> validate against `item`;
- `list`
  - require JSON array;
  - validate each element against `items`;
  - return parsed Python list;
- `map`
  - require JSON object;
  - validate every value against `values`;
  - return parsed Python dict with string keys.

This keeps structured bundle validation authoritative and avoids using prose or
pointer files as semantic authority.

### Prompt Rendering

`prompt_contract.py` should render nested schemas recursively so provider and
command prompts communicate the same optional/list/map rules that the runtime
will enforce.

## Test Strategy

Add focused tests rather than broad runtime changes.

Frontend tests:

- `tests/test_workflow_lisp_collection_types.py`
  - reader accepts generic type atoms;
  - parser resolves `Optional`, `List`, and `Map`;
  - invalid arity, unknown generic heads, and non-`String` map keys fail
    deterministically;
  - imported inner type names resolve inside collection args.
- `tests/test_workflow_lisp_definitions.py`
  - schema names nested inside collections still fail as type misuse.
- `tests/test_workflow_lisp_workflows.py`
  - collection types are rejected in workflow-boundary params and returns.
- `tests/test_workflow_lisp_lowering.py`
  - provider/command result lowering emits recursive collection schemas.

Shared contract tests:

- `tests/test_output_contract_collections.py`
  - optional fields parse to `None`;
  - list fields validate recursively;
  - map fields validate recursively;
  - unsupported nested record/json/provider/prompt shapes are rejected by the
    frontend before shared validation.

CLI/build coverage:

- one `.orc` compile fixture with collection-typed structured results to prove
  contract emission and prompt rendering stay deterministic.

## Implementation Sequence

1. Add the generalized bracket-balanced type-atom reader support.
2. Add `type_expressions.py` and parse raw authored type strings there.
3. Extend `type_env.py` with collection `TypeRef`s and recursive resolution.
4. Replace raw string membership checks in `compiler.py` with parsed
   type-expression validation.
5. Extend `contracts.py` to derive recursive collection field schemas and
   boundary rejection diagnostics.
6. Extend `output_contract.py` and `prompt_contract.py` for recursive optional,
   list, and map field schemas.
7. Add focused frontend, contract, and compile-fixture tests.

## Acceptance Conditions

- `Optional[T]`, `List[T]`, and `Map[String,T]` are readable and resolvable in
  authored type positions.
- the compiler exposes first-class collection `TypeRef`s rather than raw string
  escape hatches.
- structured-result contracts can lower supported collection fields and shared
  validation can parse them back into typed Python values.
- optional structured fields round-trip as semantic values with `None`, not as
  silently missing artifact entries.
- collection types are still rejected at workflow boundaries in this slice.
- unsupported nested collection shapes fail with deterministic frontend
  diagnostics instead of runtime surprises.

## Verification Plan

- `python -m pytest --collect-only tests/test_workflow_lisp_collection_types.py tests/test_output_contract_collections.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py -q`
- `python -m pytest tests/test_workflow_lisp_collection_types.py -q`
- `python -m pytest tests/test_output_contract_collections.py -q`
- `python -m pytest tests/test_workflow_lisp_workflows.py -k 'collection or workflow_boundary' -q`
- `python -m pytest tests/test_workflow_lisp_lowering.py -k 'collection or structured_result' -q`
