# Generic Collection Types Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class `Optional[T]`, `List[T]`, and `Map[String,T]` type expressions to the Workflow Lisp frontend for definition fields and structured-result contracts, while keeping collection transport explicitly unsupported at workflow boundaries.

**Architecture:** Keep authored type references as reader-level symbol atoms, add one compiler-owned recursive type-expression parser plus frontend-local collection `TypeRef`s, and extend structured-result contract lowering plus shared JSON-bundle validation to understand recursive optional/list/map field schemas. Preserve the existing read -> syntax -> definitions/modules -> type environment -> typecheck -> lowering -> shared validation seam, keep structured bundles authoritative, and reject any widening into workflow-boundary transport or unsupported nested semantic types.

**Tech Stack:** Python 3, Workflow Lisp frontend (`orchestrator/workflow_lisp`), shared output/prompt contract helpers (`orchestrator/contracts`), `pytest`, `python -m orchestrator compile`

---

## Scope Guardrails

- `docs/steering.md` is empty in this checkout, and `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` currently records no events, so this plan uses only the bounded constraints from the design docs and work-item context.
- Support only authored type positions, frontend type resolution, structured-result lowering, prompt-contract rendering, and shared JSON-bundle validation.
- Lower only recursive collection shapes built from already-supported leaves: `String`, `Int`, `Bool`, enums, and relpaths.
- Reject collections containing `RecordTypeRef`, `UnionTypeRef`, `WorkflowRefTypeRef`, `Provider`, `Prompt`, or `Json`.
- Reject collections anywhere they would cross a workflow boundary: `defworkflow` params, returns, and `WorkflowRef[...]` transport.
- Do not add list/map literal syntax, collection mutation helpers, runtime changes, YAML generation, pointer-authority changes, or workflow-boundary flattening.

## File Map

**Create**
- `orchestrator/workflow_lisp/type_expressions.py`
  - Compiler-owned parser for authored type strings.
- `tests/test_workflow_lisp_collection_types.py`
  - Focused reader/parser/type-resolution diagnostics for collections.
- `tests/test_output_contract_collections.py`
  - Recursive output-bundle and prompt-contract behavior tests for optional/list/map schemas.
- `tests/fixtures/workflow_lisp/valid/collection_structured_result.orc`
  - Compile fixture proving collection-typed structured-result lowering.
- `tests/fixtures/workflow_lisp/invalid/collection_type_invalid_arity.orc`
  - Invalid generic arity fixture.
- `tests/fixtures/workflow_lisp/invalid/collection_map_key_invalid.orc`
  - Invalid `Map` key fixture.
- `tests/fixtures/workflow_lisp/invalid/workflow_boundary_collection_invalid.orc`
  - Invalid workflow-boundary collection fixture.

**Modify**
- `orchestrator/workflow_lisp/reader.py`
  - Generalize the current `WorkflowRef[...]`-only bracket reader.
- `orchestrator/workflow_lisp/type_env.py`
  - Add collection `TypeRef`s and recursive resolution through imports.
- `orchestrator/workflow_lisp/compiler.py`
  - Replace raw string membership checks with parsed type-expression validation and explicit boundary rejection.
- `orchestrator/workflow_lisp/contracts.py`
  - Derive recursive structured-result field schemas and reject unsupported collection elements.
- `orchestrator/workflow_lisp/diagnostics.py`
  - Classify any new collection-specific diagnostic codes into existing phases if needed.
- `orchestrator/contracts/output_contract.py`
  - Validate recursive optional/list/map schemas and return typed Python values, including `None`.
- `orchestrator/contracts/prompt_contract.py`
  - Render recursive collection schemas in output/variant contract prompt blocks.
- `tests/test_workflow_lisp_reader.py`
  - Preserve reader coverage for generic bracket-balanced type atoms.
- `tests/test_workflow_lisp_definitions.py`
  - Cover schema misuse nested inside collections.
- `tests/test_workflow_lisp_workflows.py`
  - Cover workflow-boundary collection rejections.
- `tests/test_workflow_lisp_lowering.py`
  - Cover recursive collection schema emission in lowered contracts.

### Task 1: Add Generic Type-Expression Reader and Parser

**Files:**
- Create: `orchestrator/workflow_lisp/type_expressions.py`
- Modify: `orchestrator/workflow_lisp/reader.py`
- Modify: `tests/test_workflow_lisp_reader.py`
- Test: `tests/test_workflow_lisp_collection_types.py`
- Fixture: `tests/fixtures/workflow_lisp/invalid/collection_type_invalid_arity.orc`

- [ ] **Step 1: Add failing reader and parser coverage**

Add tests that pin these behaviors before implementation:

```python
def test_reader_preserves_generic_type_atom_as_one_symbol() -> None:
    expr = read_sexpr_text("(defrecord X (field List[Optional[String]]))", source_path="inline.orc")
    atom = expr.items[0].items[2].items[1]
    assert isinstance(atom, SymbolAtom)
    assert atom.value == "List[Optional[String]]"


def test_parse_type_expression_supports_nested_collection_types() -> None:
    parsed = parse_type_expression("Map[String, List[Optional[WorkReport]]]", span=SPAN, form_path=FORM_PATH)
    assert parsed.__class__.__name__ == "MapTypeExpr"


def test_parse_type_expression_rejects_invalid_generic_arity() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_type_expression("Optional[String, Int]", span=SPAN, form_path=FORM_PATH)
    assert excinfo.value.diagnostics[0].code == "type_expression_invalid"
```

- [ ] **Step 2: Run the narrow reader/parser tests and confirm failure**

Run:

```bash
python -m pytest tests/test_workflow_lisp_reader.py -k 'generic or workflow_ref' -q
python -m pytest tests/test_workflow_lisp_collection_types.py -k 'parse_type_expression or generic' -q
```

Expected:
- at least one failure because generic collection atoms are not preserved as one symbol today;
- parser tests fail because `type_expressions.py` does not exist yet.

- [ ] **Step 3: Implement generalized bracket-balanced type-atom reading**

Make `reader.py` treat any identifier immediately followed by `[` as one balanced symbol token instead of special-casing `WorkflowRef[` only. Preserve the exact authored token text, including nested brackets, commas, spaces, and `->`.

Implement `type_expressions.py` with:

```python
@dataclass(frozen=True)
class NamedTypeExpr:
    name: str


@dataclass(frozen=True)
class WorkflowRefTypeExpr:
    param_types: tuple["ParsedTypeExpr", ...]
    return_type: "ParsedTypeExpr"


@dataclass(frozen=True)
class OptionalTypeExpr:
    item_type: "ParsedTypeExpr"


@dataclass(frozen=True)
class ListTypeExpr:
    item_type: "ParsedTypeExpr"


@dataclass(frozen=True)
class MapTypeExpr:
    key_type: "ParsedTypeExpr"
    value_type: "ParsedTypeExpr"
```

Also add:
- `parse_type_expression(text, span, form_path, expansion_stack=())`
- `split_top_level_args(text)`
- `top_level_arrow_index(text)`

Rules:
- `WorkflowRef[...]`, `Optional[...]`, `List[...]`, and `Map[..., ...]` parse through one shared helper;
- unknown generic heads raise `type_expression_invalid`;
- diagnostics point at the full authored type span.

- [ ] **Step 4: Re-run the focused reader/parser tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_reader.py -k 'generic or workflow_ref' -q
python -m pytest tests/test_workflow_lisp_collection_types.py -k 'parse_type_expression or generic' -q
```

Expected:
- PASS for generic atom preservation and parser behavior;
- `WorkflowRef[...]` behavior remains covered by the same generalized path.

### Task 2: Resolve Collection TypeRefs and Definition-Time Validation

**Files:**
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Create: `tests/test_workflow_lisp_collection_types.py`
- Modify: `tests/test_workflow_lisp_definitions.py`
- Fixture: `tests/fixtures/workflow_lisp/invalid/collection_map_key_invalid.orc`

- [ ] **Step 1: Add failing resolution and validation tests**

Add tests that pin:
- `Optional[T]`, `List[T]`, and `Map[String,T]` resolve to first-class collection `TypeRef`s;
- imported or module-qualified inner type names resolve inside generic args;
- schema names nested inside collections still raise `schema_used_as_type`;
- invalid generic arity raises `type_expression_invalid`;
- `Map[Int, T]` raises `collection_key_type_invalid`;
- `WorkflowRef[...]` nested inside a collection is rejected.

Use test shapes like:

```python
resolved = type_env.resolve_type("List[Imported.WorkReport]", span=SPAN, form_path=FORM_PATH)
assert isinstance(resolved, ListTypeRef)
assert isinstance(resolved.item_type_ref, PathTypeRef)
```

- [ ] **Step 2: Run the definition/type-resolution selectors and confirm failure**

Run:

```bash
python -m pytest tests/test_workflow_lisp_collection_types.py -q
python -m pytest tests/test_workflow_lisp_definitions.py -k 'collection or schema_used_as_type' -q
```

Expected:
- failures because `type_env.py` only resolves plain names plus `WorkflowRef[...]`;
- compiler definition validation still uses raw string membership checks.

- [ ] **Step 3: Add collection TypeRefs and recursive resolution**

Extend `type_env.py` with:

```python
@dataclass(frozen=True)
class OptionalTypeRef:
    name: str
    item_type_ref: TypeRef


@dataclass(frozen=True)
class ListTypeRef:
    name: str
    item_type_ref: TypeRef


@dataclass(frozen=True)
class MapTypeRef:
    name: str
    key_type_ref: TypeRef
    value_type_ref: TypeRef
```

Then:
- fold the new `ParsedTypeExpr` layer into `_resolve_inline_type`;
- resolve inner names one argument at a time through `ModuleImportScope`;
- require `Map` keys to resolve to `PrimitiveTypeRef(name="String")`;
- reject nested `WorkflowRefTypeRef` inside collections;
- keep `RecordField.type_name` and other authored carriers unchanged.

- [ ] **Step 4: Replace raw type-name validation in `compiler.py`**

Update `_validate_field_types(...)` so it:
- parses authored type strings once via `type_expressions.py`;
- accepts named types through existing visible/prelude/import rules;
- rejects bad arity, unknown generic heads, schema names in nested positions, and non-`String` map keys with deterministic diagnostics;
- does not silently pass collection strings through the old `field.type_name in available_type_names` path.

If a new diagnostic code is introduced, classify it in `diagnostics.py` under the existing type or lowering phases instead of leaving it unclassified.

- [ ] **Step 5: Re-run the focused definition/type-resolution tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_collection_types.py -q
python -m pytest tests/test_workflow_lisp_definitions.py -k 'collection or schema_used_as_type' -q
```

Expected:
- PASS for collection parsing and type resolution;
- schema misuse still reports `schema_used_as_type`;
- invalid `Map` keys report `collection_key_type_invalid`.

### Task 3: Enforce Workflow-Boundary Collection Rejection

**Files:**
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Fixture: `tests/fixtures/workflow_lisp/invalid/workflow_boundary_collection_invalid.orc`

- [ ] **Step 1: Add failing workflow-boundary tests**

Add tests that prove collection types are rejected in:
- workflow params;
- workflow return types;
- `WorkflowRef[...]` signatures that would transport collections.

Pin the diagnostic code:

```python
with pytest.raises(LispFrontendCompileError) as excinfo:
    compile_stage3_module(FIXTURE, validate_shared=False, workspace_root=tmp_path)
assert excinfo.value.diagnostics[0].code == "workflow_boundary_collection_unsupported"
```

- [ ] **Step 2: Run the focused workflow-boundary selector and confirm failure**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -k 'collection or workflow_boundary' -q
```

Expected:
- failure because collection-bearing boundaries are not rejected explicitly today.

- [ ] **Step 3: Implement explicit boundary rejection without widening flattening**

Add one shared helper at the frontend/contract boundary that walks `TypeRef`s recursively and rejects any collection-bearing workflow boundary before lowering to flattened contracts. Keep the current boundary model unchanged:
- records and unions still flatten only through the existing scalar/enum/relpath compatibility seam;
- collections do not gain any runtime transport encoding in this slice.

Also reject `WorkflowRef[...]` signatures whose params or return type recursively contain collections.

- [ ] **Step 4: Re-run the workflow-boundary selector**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -k 'collection or workflow_boundary' -q
```

Expected:
- PASS with deterministic `workflow_boundary_collection_unsupported` diagnostics.

### Task 4: Lower Recursive Collection Schemas for Structured Results

**Files:**
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Create: `tests/fixtures/workflow_lisp/valid/collection_structured_result.orc`

- [ ] **Step 1: Add failing lowering tests for recursive collection schemas**

Add tests that compile a collection-typed structured-result fixture and assert emitted contracts use recursive schemas such as:

```python
{
    "name": "owners",
    "json_pointer": "/owners",
    "type": "optional",
    "item": {"type": "string"},
}

{
    "name": "attempt_ids",
    "json_pointer": "/attempt_ids",
    "type": "list",
    "items": {"type": "integer"},
}

{
    "name": "reports",
    "json_pointer": "/reports",
    "type": "map",
    "keys": {"type": "string"},
    "values": {"type": "relpath", "under": "artifacts/work", "must_exist_target": True},
}
```

Also add a negative lowering test that a collection containing `Json`, `Provider`, `Prompt`, `RecordTypeRef`, or `UnionTypeRef` fails with `collection_element_type_unsupported`.

- [ ] **Step 2: Run the lowering selector and confirm failure**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k 'collection or structured_result' -q
```

Expected:
- failure because structured-result contracts only lower scalar/enum/relpath leaves today.

- [ ] **Step 3: Implement recursive schema derivation in `contracts.py`**

Keep top-level record and union lowering shapes unchanged, but make field schema derivation recursive:
- `OptionalTypeRef` -> `{"type": "optional", "item": ...}`
- `ListTypeRef` -> `{"type": "list", "items": ...}`
- `MapTypeRef` -> `{"type": "map", "keys": {"type": "string"}, "values": ...}`

Important rules:
- top-level field count stays one per authored field path; do not flatten list/map internals into synthetic field names;
- union shared-field and variant-field lowering must call the same recursive helper;
- unsupported nested element/value types fail during frontend lowering, not later in shared validation.

- [ ] **Step 4: Re-run the lowering selector**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k 'collection or structured_result' -q
```

Expected:
- PASS with recursive field-schema payloads in emitted `output_bundle` and `variant_output` contracts.

### Task 5: Validate and Render Recursive Collection Contracts

**Files:**
- Modify: `orchestrator/contracts/output_contract.py`
- Modify: `orchestrator/contracts/prompt_contract.py`
- Create: `tests/test_output_contract_collections.py`

- [ ] **Step 1: Add failing shared-contract tests**

Add tests for both runtime parsing and prompt rendering:

```python
def test_validate_output_bundle_optional_field_missing_returns_none(tmp_path: Path) -> None:
    artifacts = validate_output_bundle(bundle, workspace=tmp_path)
    assert artifacts["owner"] is None


def test_validate_output_bundle_list_and_map_fields_validate_recursively(tmp_path: Path) -> None:
    artifacts = validate_output_bundle(bundle, workspace=tmp_path)
    assert artifacts["attempt_ids"] == [1, 2, 3]
    assert artifacts["reports"] == {"main": "artifacts/work/report.md"}


def test_render_output_bundle_contract_block_renders_nested_collection_schema() -> None:
    rendered = render_output_bundle_contract_block(bundle)
    assert "type: optional" in rendered
    assert "type: list" in rendered
    assert "type: map" in rendered
```

Also cover `variant_output` shared fields and selected-variant fields with collection schemas.

- [ ] **Step 2: Run the shared-contract tests and confirm failure**

Run:

```bash
python -m pytest tests/test_output_contract_collections.py -q
```

Expected:
- failure because `output_contract.py` only understands scalar/enum/bool/integer/relpath bundle leaves;
- prompt rendering lacks recursive output for nested schemas.

- [ ] **Step 3: Implement recursive output validation and prompt rendering**

Update `output_contract.py` so `_parse_output_bundle_value(...)` becomes recursive:
- `optional`
  - missing pointer or explicit JSON `null` -> return `None`;
  - present non-null value -> validate against `item`;
- `list`
  - require a JSON array and validate each element through `items`;
- `map`
  - require a JSON object, keep string keys, and validate each value through `values`.

Preserve these semantics:
- optional structured fields must still appear in returned artifacts with value `None`;
- violation types remain stable and path/json-pointer context stays attached;
- validation stays authoritative on bundle JSON, not prose.

Update `prompt_contract.py` to render nested `item`, `items`, `keys`, and `values` blocks recursively for both `output_bundle` and `variant_output`.

- [ ] **Step 4: Re-run the shared-contract tests**

Run:

```bash
python -m pytest tests/test_output_contract_collections.py -q
```

Expected:
- PASS with recursive bundle parsing and nested prompt-contract rendering.

### Task 6: Fixture Compile Proof and Final Verification

**Files:**
- Verify: `tests/fixtures/workflow_lisp/valid/collection_structured_result.orc`
- Verify: `tests/test_workflow_lisp_collection_types.py`
- Verify: `tests/test_output_contract_collections.py`
- Verify: `tests/test_workflow_lisp_workflows.py`
- Verify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Add the compile fixture and keep it minimal**

Create `collection_structured_result.orc` with:
- one enum used inside a collection value;
- one relpath type used inside a collection value;
- one record result carrying representative fields:
  - `owner Optional[String]`
  - `attempt_ids List[Int]`
  - `reports Map[String, WorkReport]`
  - `review_states List[Optional[ReviewDecision]]`
- one workflow named `orchestrate` that emits a provider or command structured result using those fields.

Keep the fixture compile-only. Do not add runtime semantics, macros, or workflow-boundary collection transport.

- [ ] **Step 2: Run the required collect-only sweep**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_collection_types.py tests/test_output_contract_collections.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py -q
```

Expected:
- all newly added or renamed tests collect successfully.

- [ ] **Step 3: Run the required focused verification commands**

Run exactly these recorded commands:

```bash
python -m pytest tests/test_workflow_lisp_collection_types.py -q
python -m pytest tests/test_output_contract_collections.py -q
python -m pytest tests/test_workflow_lisp_workflows.py -k 'collection or workflow_boundary' -q
python -m pytest tests/test_workflow_lisp_lowering.py -k 'collection or structured_result' -q
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/collection_structured_result.orc --entry-workflow orchestrate --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
```

Expected:
- all focused tests pass;
- the compile command succeeds and emits deterministic lowered contracts for collection-typed structured results.

- [ ] **Step 4: Record verification evidence and stop**

Capture in the implementation handoff or completion note:
- which files changed;
- the exact commands run;
- whether the compile proof succeeded;
- any intentionally deferred cases that remain out of scope, especially workflow-boundary transport and unsupported nested semantic types.

## Acceptance Checklist

- [ ] `Optional[T]`, `List[T]`, and `Map[String,T]` are readable in authored type positions.
- [ ] The frontend resolves collection types into explicit `TypeRef` classes rather than raw string escape hatches.
- [ ] Invalid generic heads, invalid arity, non-`String` map keys, and schema misuse inside collections fail with deterministic frontend diagnostics.
- [ ] Workflow-boundary params, returns, and workflow-ref transport still reject collection types explicitly.
- [ ] Structured-result lowering emits recursive optional/list/map schemas without changing top-level bundle shape.
- [ ] Shared output-bundle validation returns typed Python values for collection fields, including `None` for missing or JSON-null optional values.
- [ ] Prompt-contract rendering shows the same recursive schema the runtime enforces.
- [ ] The required focused `pytest` selectors and compile proof pass.
