# Parser Syntax Frontend Core Implementation Architecture

## Scope

This design gap covers only the Stage 1 frontend core required by the Lisp
frontend MVP:

- parse one `.orc` compilation unit with source spans;
- preserve an explicit S-expression parse tree boundary;
- elaborate parse results into syntax objects;
- support definition-form coverage for `defenum`, `defpath`, `defrecord`, and
  `defunion`;
- validate duplicate names, unknown names, invalid type references, and
  malformed path-definition shapes.

Out of scope for this tranche:

- `defworkflow`, `call`, `match`, `provider-result`, `command-result`;
- lowering to Core Workflow AST;
- runtime execution or loader integration for `.orc` files;
- macros, modules/imports, procedural lowering, or semantic IR emission.

## Design Constraints

The implementation must follow the frontend requirements in
`docs/design/workflow_lisp_frontend_specification.md`,
`docs/design/workflow_lisp_frontend_mvp_specification.md`, and
`docs/design/workflow_language_design_principles.md`:

- frontend semantics, not YAML generation, are authoritative;
- source spans must survive into diagnostics;
- structured definitions are the semantic authority;
- Stage 1 must stay implementation-bounded and avoid speculative runtime work.

The existing repo already has a typed YAML surface boundary in
`orchestrator/workflow/surface_ast.py`, elaboration in
`orchestrator/workflow/elaboration.py`, and validation error plumbing in
`orchestrator/exceptions.py`. The Lisp frontend should mirror that separation
instead of mixing reading, syntax, validation, and lowering into one file.

## Proposed Package Boundary

Add a new isolated package:

```text
orchestrator/workflow_lisp/
  __init__.py
  spans.py
  diagnostics.py
  sexpr.py
  reader.py
  syntax.py
  definitions.py
  compiler.py
```

Responsibilities:

- `spans.py`: source coordinates and span helpers.
- `diagnostics.py`: frontend diagnostic records and renderers.
- `sexpr.py`: parse-tree node types that preserve authored shape.
- `reader.py`: deterministic `.orc` reader from text to S-expression tree.
- `syntax.py`: syntax-object wrapper layer over parse-tree nodes.
- `definitions.py`: typed definition AST for header, enums, paths, records, and
  unions.
- `compiler.py`: Stage 1 orchestration entrypoint that runs read -> syntax ->
  definition elaboration -> definition validation.

This keeps Stage 1 independent from `WorkflowLoader` until lowering exists,
while still giving later stages a clean integration point.

## Data Model

### Source Spans

Use a closed span model rather than raw tuples:

```text
SourcePosition(file, line, column, offset)
SourceSpan(start, end)
```

Requirements:

- `line` and `column` are 1-based;
- `offset` is byte or codepoint based, but the choice must be fixed and tested;
- every parsed node carries one span;
- diagnostics refer to the span of the authored form that caused the error.

### S-Expression Parse Tree

The parse tree is a syntax-free authored representation. Required node kinds:

- `ListExpr(items, span)`
- `SymbolAtom(value, span)`
- `KeywordAtom(value, span)`
- `StringAtom(value, span)`
- `IntAtom(value, span)`
- `BoolAtom(value, span)`

Stage 1 should not add general numeric, vector, quote, or reader-macro support.
Comments are discarded during reading and do not appear in the tree.

### Syntax Objects

Syntax objects are the bridge between raw parse structure and future macro-safe
frontend AST. Even though MVP Stage 1 does not implement macros, the shape
should reserve the right metadata now:

```text
SyntaxNode(datum, span, module_path, form_path)
```

Required semantics:

- `datum` points at the preserved parse-tree node;
- `module_path` is the `.orc` file path;
- `form_path` identifies enclosing forms such as
  `workflow-lisp > defrecord ChecksResult`;
- syntax creation is deterministic and does not rewrite authored structure.

### Typed Definition AST

Stage 1 elaborates syntax objects into a constrained definition AST:

- `WorkflowLispModule(language_version, target_dsl_version, definitions, span)`
- `EnumDef(name, values, span)`
- `PathDef(name, kind, under, must_exist, span)`
- `RecordDef(name, fields, span)`
- `UnionDef(name, variants, span)`

Field and variant members keep their own spans so later type errors can point
at the exact field, not only the parent form.

## Compilation Pipeline

Stage 1 compilation is a four-pass pipeline:

1. `read_source(path)` in `reader.py`
   - parses UTF-8 text into one root S-expression tree;
   - rejects malformed parentheses, malformed strings, and unsupported atoms;
   - assigns spans to every node.
2. `build_syntax_module(parse_tree)` in `syntax.py`
   - requires exactly one root `(workflow-lisp ...)` form;
   - wraps child forms in syntax objects with module/form metadata.
3. `elaborate_definitions(module_syntax)` in `definitions.py`
   - converts supported forms into typed definition nodes;
   - rejects unknown top-level forms and malformed field lists.
4. `validate_definition_module(module_ast)` in `compiler.py`
   - builds the symbol table;
   - resolves type references against the fixed prelude and local definitions;
   - emits deterministic diagnostics for duplicates and unresolved names.

The output of Stage 1 is a typed module artifact plus diagnostics. It is not
yet a workflow bundle and must not pass through YAML lowering surfaces.

## Validation Rules

The Stage 1 validator owns only frontend-local checks.

### Header Validation

Require:

- exactly one top-level `workflow-lisp` form;
- `:language` present and equal to `"0.1"`;
- `:target-dsl` present and supported, initially `"2.14"` only.

Reject:

- duplicate header keywords;
- unknown header keywords in MVP strict mode;
- extra forms outside the root module.

### Name And Type Validation

Build the symbol table in two phases:

1. register all top-level definition names;
2. resolve referenced types in records and unions.

Resolution order:

- local type definitions from the same file;
- fixed Stage 1 prelude: `String`, `Int`, `Bool`, `Json`, `Provider`,
  `Prompt`, `PathRel`.

This allows forward references without requiring author order tricks.

### Path Definition Validation

For Stage 1, `defpath` supports only the MVP relpath contract shape:

- `:kind relpath`
- `:under "..."` required
- `:must-exist true|false` required

Reject missing keywords, duplicate keywords, non-string `:under`, and
unsupported `:kind` values now rather than carrying partial path contracts
forward.

### Record And Union Validation

Require:

- unique field names inside each record;
- unique variant names inside each union;
- unique field names within a variant payload;
- at least one enum value, record field, and union variant.

Recursive self-reference is allowed only if it is structurally inert at this
stage. If implementation complexity becomes high, Stage 1 may reject recursive
type cycles explicitly and defer them to a later tranche.

## Diagnostics

Do not reuse raw string-only loader errors for the frontend internals. Add a
typed diagnostic record:

```text
LispFrontendDiagnostic(code, message, span, form_path, notes=[])
```

Required error codes for this tranche:

- `frontend_parse_error`
- `language_version_unsupported`
- `target_dsl_unsupported`
- `definition_form_unknown`
- `definition_duplicate`
- `type_unknown`
- `record_field_duplicate`
- `union_variant_duplicate`
- `path_definition_invalid`

Provide one renderer that converts diagnostics into stable human-readable text.
Later loader integration may adapt these records into
`orchestrator.exceptions.ValidationError`, but Stage 1 should keep the richer
diagnostic structure internally.

## Integration Strategy

This tranche should not splice `.orc` support into `WorkflowLoader` yet.
Instead, expose a pure API such as:

```python
compile_stage1_module(path: Path) -> WorkflowLispModule
```

or

```python
compile_stage1_module(path: Path) -> Stage1CompileResult
```

where the result carries the typed module and any diagnostics.

Why this boundary:

- it keeps Stage 1 testable without entangling the runtime;
- it preserves the spec's parse-tree -> syntax-AST boundary;
- it avoids inventing half-finished `.orc` loader semantics before lowering
  exists.

Once Stage 3 lowering exists, `WorkflowLoader` or a sibling frontend loader can
call this compiler entrypoint and then hand the lowered Core AST into the
existing validation/runtime pipeline.

## Test Strategy

Add focused tests rather than a broad workflow smoke layer for Stage 1.

Proposed test modules:

- `tests/test_workflow_lisp_reader.py`
  - comments ignored;
  - lists/atoms preserve spans;
  - malformed parens and malformed strings fail deterministically.
- `tests/test_workflow_lisp_definitions.py`
  - positive fixtures for `defenum`, `defpath`, `defrecord`, `defunion`;
  - duplicate definitions and bad field shapes fail with the right codes;
  - forward type references resolve.
- `tests/test_workflow_lisp_diagnostics.py`
  - diagnostics render file, line, column, and form context;
  - unsupported target DSL and unknown type references point at authored spans.

Fixture style:

- keep short `.orc` samples under `tests/fixtures/workflow_lisp/`;
- assert specific diagnostic codes and source coordinates, not full prose blobs.

## Implementation Sequence

1. Add the span and diagnostic primitives.
2. Implement the reader and parse-tree nodes with source spans.
3. Implement syntax-object wrapping for the root module and top-level forms.
4. Implement typed definition elaboration for the four MVP definition forms.
5. Add symbol-table and type-reference validation.
6. Expose a stable `compile_stage1_module` entrypoint.

Each step should land with focused tests before the next step extends surface
area.

## Risks And Mitigations

- Risk: parser and definition elaboration collapse into one pass and erase span
  fidelity.
  Mitigation: keep `sexpr.py`, `syntax.py`, and `definitions.py` as separate
  layers with separate tests.

- Risk: Stage 1 drifts into loader/runtime wiring before lowering contracts
  exist.
  Mitigation: keep the Stage 1 API pure and file-based, with no `WorkflowLoader`
  changes in this tranche.

- Risk: diagnostics regress into raw strings that cannot support later source
  mapping.
  Mitigation: introduce typed diagnostic records now and only render to strings
  at the boundary.

- Risk: definition validation duplicates future shared validation behavior.
  Mitigation: limit Stage 1 checks to syntax and local type-definition
  correctness; defer path safety and runtime contract refinement to later shared
  validation passes.
