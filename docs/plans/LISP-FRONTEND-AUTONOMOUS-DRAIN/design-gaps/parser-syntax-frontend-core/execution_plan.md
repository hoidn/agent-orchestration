# Parser Syntax Frontend Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Workflow Lisp Stage 1 frontend core: a `.orc` reader with source spans, a preserved S-expression parse tree, a syntax-object layer, typed definition elaboration for `defenum`/`defpath`/`defrecord`/`defunion`, and deterministic span-carrying diagnostics, without any runtime or loader integration.

**Architecture:** Add an isolated `orchestrator/workflow_lisp/` package with a strict four-pass pipeline: read source text into S-expression nodes, wrap those nodes in syntax objects with module/form metadata, elaborate supported top-level forms into a typed definition AST, then validate names and type references through a pure Stage 1 compile API. Keep parse tree, syntax objects, and typed definitions in separate modules so later macro/lowering stages can extend the frontend without collapsing authored shape or losing span fidelity.

**Tech Stack:** Python 3 dataclasses and enums, `pathlib.Path`, UTF-8 text parsing, pytest, `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Context And Boundaries

Read these first:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`

Hard scope limits:

- Implement only Stage 1 frontend core for one `.orc` compilation unit.
- Support one root `(workflow-lisp ...)` form with strict MVP header validation.
- Support only `defenum`, `defpath`, `defrecord`, and `defunion` at top level.
- Resolve type references only against the fixed Stage 1 prelude plus local definitions.
- Keep the compile surface pure. Do not touch `WorkflowLoader`, runtime execution, YAML lowering, Core Workflow AST lowering, or shared validation passes.

Non-goals for this plan:

- No `defworkflow`, `defproc`, `defun`, `call`, `let*`, `match`, or lowering work.
- No macros, imports/exports, module system, vectors, quoted symbols, `nil`, floats, or reader macros.
- No runtime-owned source maps or workflow smoke runs.
- No prompt, provider, command, artifact, or queue behavior.

Design choices to keep fixed during implementation:

- Source coordinates are 1-based for line and column.
- Offset accounting is codepoint-based, not byte-based. Tests must pin this choice.
- Comments are discarded by the reader and never appear in the parse tree.
- Diagnostics are typed records with stable error codes; rendered prose is a view.
- Unsupported lexical forms should fail deterministically with `frontend_parse_error` rather than being silently accepted.

## File Map

Create:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/sexpr.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/compiler.py`
- `tests/test_workflow_lisp_reader.py`
- `tests/test_workflow_lisp_definitions.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/fixtures/workflow_lisp/valid/minimal_module.orc`
- `tests/fixtures/workflow_lisp/valid/type_definitions.orc`
- `tests/fixtures/workflow_lisp/invalid/unclosed_list.orc`
- `tests/fixtures/workflow_lisp/invalid/unterminated_string.orc`
- `tests/fixtures/workflow_lisp/invalid/unknown_top_level_form.orc`
- `tests/fixtures/workflow_lisp/invalid/duplicate_definition.orc`
- `tests/fixtures/workflow_lisp/invalid/unknown_type.orc`
- `tests/fixtures/workflow_lisp/invalid/path_missing_under.orc`
- `tests/fixtures/workflow_lisp/invalid/duplicate_record_field.orc`
- `tests/fixtures/workflow_lisp/invalid/duplicate_union_variant.orc`
- `tests/fixtures/workflow_lisp/invalid/unsupported_target_dsl.orc`

Do not modify unless a focused test proves it is necessary:

- `orchestrator/loader.py`
- `orchestrator/workflow/`
- `orchestrator/exceptions.py`

## Concrete Data Shapes

Implement these Stage 1 types exactly enough that later tasks do not need to rediscover the shape:

```python
@dataclass(frozen=True)
class SourcePosition:
    path: str
    line: int
    column: int
    offset: int


@dataclass(frozen=True)
class SourceSpan:
    start: SourcePosition
    end: SourcePosition
```

```python
@dataclass(frozen=True)
class LispFrontendDiagnostic:
    code: str
    message: str
    span: SourceSpan
    form_path: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
```

```python
SExpr = ListExpr | SymbolAtom | KeywordAtom | StringAtom | IntAtom | BoolAtom
```

```python
@dataclass(frozen=True)
class SyntaxNode:
    datum: SExpr
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]
```

```python
@dataclass(frozen=True)
class WorkflowLispModule:
    language_version: str
    target_dsl_version: str
    definitions: tuple[DefinitionNode, ...]
    span: SourceSpan
```

Definition node family:

- `EnumDef(name, values, span)`
- `PathDef(name, kind, under, must_exist, span)`
- `RecordDef(name, fields, span)`
- `UnionDef(name, variants, span)`

Member nodes must keep their own spans:

- `RecordField(name, type_name, span)`
- `UnionVariant(name, fields, span)`
- `EnumValue(name, span)`

Compile boundary:

```python
def compile_stage1_module(path: Path) -> WorkflowLispModule:
    ...
```

Failure boundary:

- raise a dedicated exception from `compiler.py` carrying `tuple[LispFrontendDiagnostic, ...]`;
- do not convert these diagnostics into `WorkflowValidationError`;
- keep one renderer in `diagnostics.py` that produces stable human-readable text for tests and future CLI integration.

Prelude names for Stage 1 resolution:

```text
String
Int
Bool
Json
Provider
Prompt
PathRel
```

Required diagnostic codes for this tranche:

```text
frontend_parse_error
language_version_unsupported
target_dsl_unsupported
definition_form_unknown
definition_duplicate
type_unknown
record_field_duplicate
union_variant_duplicate
path_definition_invalid
```

## Task 1: Scaffold Package, Spans, And Diagnostic Primitives

**Files:**

- Create: `orchestrator/workflow_lisp/__init__.py`
- Create: `orchestrator/workflow_lisp/spans.py`
- Create: `orchestrator/workflow_lisp/diagnostics.py`
- Create: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Write failing tests for span and diagnostic rendering primitives**

Add focused tests for:

- `SourcePosition` and `SourceSpan` equality/immutability;
- renderer output including diagnostic code, file path, line, column, and form path;
- exception object preserving an ordered tuple of diagnostics.

Use test names:

```python
def test_render_diagnostic_includes_location_and_form_path(): ...
def test_frontend_compile_error_exposes_diagnostics_tuple(): ...
```

- [ ] **Step 2: Create the package entrypoint and test file skeleton**

Add the package directory plus an initial `tests/test_workflow_lisp_diagnostics.py` module so the implementation can proceed with normal pytest discovery. Do not add reader or definition test stubs yet; those arrive with the tasks that own them.

- [ ] **Step 3: Implement span helpers and diagnostic records**

Implementation requirements:

- make the dataclasses `frozen=True` to match the repo's typed-record style;
- store `path` as a string so diagnostics remain stable across temporary test roots;
- expose `render_diagnostic(diagnostic: LispFrontendDiagnostic) -> str`;
- expose `render_diagnostics(diagnostics: Iterable[LispFrontendDiagnostic]) -> str`;
- export the public Stage 1 symbols from `orchestrator/workflow_lisp/__init__.py` only after the modules compile.

- [ ] **Step 4: Run the diagnostics tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -q
```

Expected: PASS for the primitive rendering tests.

## Task 2: Implement The Reader And S-Expression Parse Tree

**Files:**

- Create: `orchestrator/workflow_lisp/sexpr.py`
- Create: `orchestrator/workflow_lisp/reader.py`
- Create: `tests/test_workflow_lisp_reader.py`
- Create fixtures:
  - `tests/fixtures/workflow_lisp/valid/minimal_module.orc`
  - `tests/fixtures/workflow_lisp/invalid/unclosed_list.orc`
  - `tests/fixtures/workflow_lisp/invalid/unterminated_string.orc`

- [ ] **Step 1: Write failing reader tests before implementation**

Cover these behaviors:

- comments beginning with `;` are ignored;
- lists and atoms preserve authored spans;
- booleans parse as `BoolAtom`;
- integers parse as `IntAtom`;
- keywords parse as `KeywordAtom`;
- malformed parens and strings raise `frontend_parse_error` with the failing span.

Use test names:

```python
def test_reader_preserves_spans_for_nested_lists_and_atoms(): ...
def test_reader_ignores_line_comments(): ...
def test_reader_reports_unclosed_list_with_frontend_parse_error(): ...
def test_reader_reports_unterminated_string_with_frontend_parse_error(): ...
```

- [ ] **Step 2: Add minimal valid and invalid `.orc` fixtures**

Fixture requirements:

- `minimal_module.orc` contains a valid header and one `defenum`;
- invalid fixtures isolate one failure mode per file;
- keep fixture bodies short enough that line and column assertions are obvious.

- [ ] **Step 3: Implement the parse-tree nodes and reader**

Implementation requirements:

- parse only lists, symbols, keywords, strings, integers, and booleans;
- reject floats, vectors, quoted symbols, and `nil` with `frontend_parse_error`;
- expose `read_sexpr_text(source: str, *, source_path: str) -> ListExpr`;
- expose `read_sexpr_file(path: Path) -> ListExpr`;
- assign one `SourceSpan` to every node, where the list span covers opening paren through closing paren;
- treat string escape handling conservatively: support `\\`, `\"`, `\n`, and `\t`; reject malformed escapes rather than guessing.

- [ ] **Step 4: Run the reader tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_reader.py -q
```

Expected: PASS with deterministic span assertions.

## Task 3: Add Syntax Objects And Module Header Validation

**Files:**

- Create: `orchestrator/workflow_lisp/syntax.py`
- Modify: `tests/test_workflow_lisp_reader.py`
- Create fixture: `tests/fixtures/workflow_lisp/invalid/unsupported_target_dsl.orc`

- [ ] **Step 1: Extend tests to cover syntax wrapping and header validation**

Add tests for:

- exactly one root `(workflow-lisp ...)` form is required;
- `:language` must exist and equal `"0.1"`;
- `:target-dsl` must exist and equal `"2.14"`;
- duplicate or unknown header keywords fail deterministically;
- `form_path` values are stable for top-level definitions, for example `("workflow-lisp", "defrecord", "ChecksResult")`.

Use test names:

```python
def test_build_syntax_module_requires_workflow_lisp_root(): ...
def test_build_syntax_module_rejects_unsupported_target_dsl(): ...
def test_build_syntax_module_assigns_form_paths_to_top_level_forms(): ...
```

- [ ] **Step 2: Implement syntax-layer dataclasses and module builder**

Implementation requirements:

- keep syntax objects as wrappers over existing `SExpr` nodes, not rewritten forms;
- define a module-level structure that stores header metadata plus top-level `SyntaxNode` forms;
- reserve `form_path` and `module_path` now; do not add hygiene fields in Stage 1;
- emit `language_version_unsupported`, `target_dsl_unsupported`, or `frontend_parse_error` as appropriate.

- [ ] **Step 3: Re-run the reader-facing tests that now cover syntax**

Run:

```bash
python -m pytest tests/test_workflow_lisp_reader.py -q
```

Expected: PASS with root-module and header checks included.

## Task 4: Elaborate Supported Definition Forms Into Typed AST Nodes

**Files:**

- Create: `orchestrator/workflow_lisp/definitions.py`
- Create: `tests/test_workflow_lisp_definitions.py`
- Create fixtures:
  - `tests/fixtures/workflow_lisp/valid/type_definitions.orc`
  - `tests/fixtures/workflow_lisp/invalid/unknown_top_level_form.orc`
  - `tests/fixtures/workflow_lisp/invalid/path_missing_under.orc`
  - `tests/fixtures/workflow_lisp/invalid/duplicate_record_field.orc`
  - `tests/fixtures/workflow_lisp/invalid/duplicate_union_variant.orc`

- [ ] **Step 1: Write failing elaboration tests for the four supported top-level forms**

Positive coverage:

- `defenum` with at least one value;
- `defpath` with `:kind relpath`, `:under "..."`, `:must-exist true|false`;
- `defrecord` with `(field Type)` entries;
- `defunion` with `(VARIANT (field Type) ...)` entries.

Negative coverage:

- unknown top-level forms produce `definition_form_unknown`;
- malformed `defpath` keyword shapes produce `path_definition_invalid`;
- malformed field lists fail before type resolution.

Use test names:

```python
def test_elaborate_definition_module_supports_stage1_type_forms(): ...
def test_elaboration_rejects_unknown_top_level_form(): ...
def test_elaboration_rejects_invalid_defpath_shape(): ...
```

- [ ] **Step 2: Implement typed definition nodes and elaboration helpers**

Implementation requirements:

- parse top-level forms from syntax objects only, never directly from raw text;
- keep child-member spans on enum values, record fields, and union variants;
- allow forward references by recording type names as unresolved strings in the typed AST;
- reject empty enums, empty records, and empty unions during elaboration with stable diagnostics instead of deferring malformed shapes into validation.

- [ ] **Step 3: Run the definition tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_definitions.py -q
```

Expected: PASS for elaboration-only cases that do not depend on final validation.

## Task 5: Add Name Resolution, Type Validation, And The Stage 1 Compile API

**Files:**

- Create: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/definitions.py`
- Modify: `tests/test_workflow_lisp_definitions.py`
- Create fixtures:
  - `tests/fixtures/workflow_lisp/invalid/duplicate_definition.orc`
  - `tests/fixtures/workflow_lisp/invalid/unknown_type.orc`

- [ ] **Step 1: Extend tests to cover symbol table and prelude resolution**

Add tests for:

- duplicate top-level definitions yield `definition_duplicate`;
- unknown field type references yield `type_unknown`;
- forward references across local definitions resolve;
- local names and prelude names are the only valid Stage 1 type sources;
- duplicate field names in a record yield `record_field_duplicate`;
- duplicate variants in a union yield `union_variant_duplicate`.

Use test names:

```python
def test_compile_stage1_reports_duplicate_definition(): ...
def test_compile_stage1_reports_unknown_type_with_field_span(): ...
def test_compile_stage1_allows_forward_type_references(): ...
def test_compile_stage1_rejects_duplicate_record_fields(): ...
def test_compile_stage1_rejects_duplicate_union_variants(): ...
```

- [ ] **Step 2: Implement validation and the compile entrypoint**

Implementation requirements:

- keep validation in two phases:
  1. register top-level names;
  2. resolve field and variant payload type references;
- keep a fixed `PRELUDE_TYPE_NAMES` constant in `compiler.py` or `definitions.py`;
- expose `compile_stage1_module(path: Path) -> WorkflowLispModule`;
- implement the pipeline strictly as `read -> syntax -> elaborate -> validate`;
- raise one compile exception containing all diagnostics found in the phase rather than failing on the first duplicate or unknown type.

- [ ] **Step 3: Run the focused definition suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_definitions.py -q
```

Expected: PASS for both positive and negative definition cases.

## Task 6: Finish Diagnostic Coverage And Run The Stored Verification Set

**Files:**

- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`

- [ ] **Step 1: Add end-to-end diagnostic assertions**

Cover these final behaviors:

- rendered diagnostics include file, line, column, code, and form context;
- unsupported target DSL points at the authored `:target-dsl` value span;
- unknown type diagnostics point at the exact field or variant payload span, not only the parent form;
- multiple diagnostics preserve deterministic ordering.

Use test names:

```python
def test_compile_stage1_renders_unknown_type_diagnostic_with_field_location(): ...
def test_compile_stage1_renders_unsupported_target_dsl_diagnostic(): ...
def test_compile_stage1_preserves_diagnostic_order(): ...
```

- [ ] **Step 2: Run the diagnostics suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -q
```

Expected: PASS with stable rendered output.

- [ ] **Step 3: Run the required verification commands from the work-item bundle**

Run exactly:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_diagnostics.py -q
python -m pytest tests/test_workflow_lisp_reader.py -q
python -m pytest tests/test_workflow_lisp_definitions.py -q
python -m pytest tests/test_workflow_lisp_diagnostics.py -q
```

Expected:

- collect-only shows the intended test cases and no import errors;
- all three focused modules pass;
- no workflow smoke check is required for this tranche because Stage 1 deliberately avoids runtime or loader integration.

## Completion Notes

When implementation is done, record:

- the exact files created under `orchestrator/workflow_lisp/` and `tests/fixtures/workflow_lisp/`;
- whether any unsupported lexical features were explicitly rejected in tests;
- the exact pytest commands run and their results.

Do not claim completion from inspection alone. This work item is complete only when the four stored pytest commands above succeed on fresh command output.
