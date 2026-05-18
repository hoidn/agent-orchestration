# Workflow Core AST Lowering And Structured Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing Workflow Lisp Stage 1 and Stage 2 frontend into the bounded Stage 3 compile-and-validate slice: elaborate typed `defworkflow` definitions, typecheck same-file `call` / `provider-result` / `command-result` forms, derive deterministic structured-result contracts, lower directly into shared workflow handoff records, and remap shared-validation failures back to authored `.orc` spans.

**Architecture:** Keep `orchestrator/workflow_lisp/` as the isolated frontend package and reuse Stage 1 definitions plus Stage 2 expression/proof checking as the only type authority. Add a narrow workflow-definition layer in `workflows.py`, structured contract derivation in `contracts.py`, and a lowering bridge in `lowering.py` that constructs `SurfaceWorkflow` / `SurfaceStep` / `SurfaceContract` records without generating YAML text, then runs shared validation through an in-memory bridge and remaps any generated-step failures through a frontend-owned origin map.

**Tech Stack:** Python 3 frozen dataclasses, existing `orchestrator.workflow_lisp` Stage 1/2 modules, `orchestrator.workflow.surface_ast`, `orchestrator.workflow.lowering`, `orchestrator.loader.WorkflowLoader` validation helpers used via an in-memory bridge, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Context And Boundaries

Read these inputs before implementation:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Current baseline to assume:

- Stage 1 files already exist: `spans.py`, `diagnostics.py`, `sexpr.py`, `reader.py`, `syntax.py`, `definitions.py`, `compiler.py`.
- Stage 2 files already exist: `expressions.py`, `type_env.py`, `typecheck.py`.
- The current `progress_ledger.json` is empty, so trust the repository state and passing checks rather than ledger history.
- `orchestrator/workflow_lisp/__init__.py` currently exports only Stage 1 and Stage 2 APIs and will need Stage 3 additions without breaking current imports.

Hard scope limits:

- Implement only the Stage 3 workflow-lowering architecture layer from the approved work-item context.
- Support bounded same-file `defworkflow`, `call`, `provider-result`, and `command-result`.
- Generate deterministic `output_bundle` and `variant_output` contracts from record and union result types only.
- Lower directly to shared typed workflow handoff records and run shared validation without `.orc` loader or CLI integration.
- Preserve authored span and `form_path` fidelity through frontend diagnostics and remapped shared-validation failures.

Explicit non-goals:

- No `defproc`, macros, imports/modules, higher-order workflow refs, standard-library phase procedures, or one real phase translation.
- No runtime loader/CLI support for `.orc` workflows.
- No new runtime execution semantics, no pointer-authority redesign, no Semantic IR redesign, and no debug YAML renderer.
- No legacy adapters, report parsing, adapter registries, or runtime-native effect work.
- No broad changes under `orchestrator/workflow/` unless a tiny validation seam extraction is strictly required to reuse existing behavior.

Semantic rules to keep fixed:

- Same-file workflow signatures register before any body is typechecked so forward calls work deterministically.
- Workflow parameters seed the lexical `ValueEnvironment`; body types must exactly match the declared return type.
- `call` bindings must match the callee signature exactly by keyword and by resolved type.
- `provider-result` requires a `Provider` expression, a `Prompt` expression, typed input expressions, and a record or union return type.
- `command-result` requires a record or union return type and explicit argv elements that do not hide semantic glue behind `python -c`, `python -`, `bash -c`, `sh -c`, or equivalent one-string shell wrappers.
- Structured bundles are authoritative. Markdown reports may be referenced as relpath values inside the structured bundle, but report text is never parsed for semantic state.
- Shared validation remains authoritative for path safety, output-bundle shape, variant-output shape, and workflow-boundary compatibility. The frontend must not fork that logic.

## File Map

Create:

- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/lowering.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/fixtures/workflow_lisp/valid/workflow_definitions.orc`
- `tests/fixtures/workflow_lisp/valid/structured_results.orc`
- `tests/fixtures/workflow_lisp/invalid/duplicate_workflow_definition.orc`
- `tests/fixtures/workflow_lisp/invalid/duplicate_workflow_param.orc`
- `tests/fixtures/workflow_lisp/invalid/workflow_return_type_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/unknown_callee.orc`
- `tests/fixtures/workflow_lisp/invalid/provider_result_bad_return.orc`
- `tests/fixtures/workflow_lisp/invalid/command_result_bad_return.orc`
- `tests/fixtures/workflow_lisp/invalid/inline_python_command_result.orc`
- `tests/fixtures/workflow_lisp/invalid/inline_shell_command_result.orc`
- `tests/fixtures/workflow_lisp/invalid/shared_validation_remap.orc`

Modify:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`

Reuse without widening ownership:

- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/loader.py`
- `orchestrator/contracts/output_contract.py`
- existing Stage 1 and Stage 2 tests plus existing fixtures under `tests/fixtures/workflow_lisp/`

Do not modify unless a focused failing test proves it is unavoidable:

- `orchestrator/loader.py`
- `orchestrator/workflow/elaboration.py`
- runtime execution code outside the narrow validation bridge
- CLI commands and workflow examples

## Concrete Public Surface

Implement the minimum reusable Stage 3 surface so later translation work does not rediscover these shapes.

Workflow-definition layer in `orchestrator/workflow_lisp/workflows.py`:

```python
@dataclass(frozen=True)
class WorkflowParam:
    name: str
    type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowDef:
    name: str
    params: tuple[WorkflowParam, ...]
    return_type_name: str
    body: SyntaxNode
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowSignature:
    name: str
    params: tuple[tuple[str, TypeRef], ...]
    return_type_ref: RecordTypeRef | UnionTypeRef
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class TypedWorkflowDef:
    definition: WorkflowDef
    signature: WorkflowSignature
    typed_body: TypedExpr


@dataclass(frozen=True)
class WorkflowCatalog:
    signatures_by_name: Mapping[str, WorkflowSignature]
    definitions_by_name: Mapping[str, WorkflowDef]
```

Required entrypoints:

```python
def elaborate_workflow_definitions(module_syntax: WorkflowLispSyntaxModule) -> tuple[WorkflowDef, ...]: ...
def build_workflow_catalog(
    module: WorkflowLispModule,
    workflow_defs: tuple[WorkflowDef, ...],
    type_env: FrontendTypeEnvironment,
) -> WorkflowCatalog: ...
def typecheck_workflow_definitions(
    workflow_defs: tuple[WorkflowDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    workflow_catalog: WorkflowCatalog,
) -> tuple[TypedWorkflowDef, ...]: ...
```

Effectful expression nodes in `orchestrator/workflow_lisp/expressions.py`:

```python
@dataclass(frozen=True)
class CallExpr:
    callee_name: str
    bindings: tuple[tuple[str, ExprNode], ...]
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class ProviderResultExpr:
    provider: ExprNode
    prompt: ExprNode
    inputs: tuple[ExprNode, ...]
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class CommandResultExpr:
    step_name: str
    argv: tuple[ExprNode, ...]
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
```

Keep one alias:

```python
ExprNode = (
    NameExpr
    | LiteralExpr
    | FieldAccessExpr
    | RecordExpr
    | LetStarExpr
    | MatchExpr
    | CallExpr
    | ProviderResultExpr
    | CommandResultExpr
)
```

Structured contract helpers in `orchestrator/workflow_lisp/contracts.py`:

```python
@dataclass(frozen=True)
class GeneratedBundleContract:
    contract_kind: str  # "output_bundle" | "variant_output"
    path: str
    payload: Mapping[str, Any]
    type_ref: RecordTypeRef | UnionTypeRef


@dataclass(frozen=True)
class FlattenedContractField:
    generated_name: str
    source_path: tuple[str, ...]
    contract_definition: Mapping[str, Any]
```

Required entrypoints:

```python
def derive_structured_result_contract(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    workflow_name: str,
    step_id: str,
) -> GeneratedBundleContract: ...

def derive_workflow_signature_contracts(
    signature: WorkflowSignature,
) -> tuple[Mapping[str, SurfaceContract], Mapping[str, SurfaceContract], tuple[FlattenedContractField, ...]]: ...
```

Lowering bridge in `orchestrator/workflow_lisp/lowering.py`:

```python
@dataclass(frozen=True)
class LoweringOriginMap:
    workflow_spans: Mapping[str, SourceSpan]
    step_spans: Mapping[str, SourceSpan]
    bundle_path_spans: Mapping[str, SourceSpan]
    contract_field_spans: Mapping[str, SourceSpan]


@dataclass(frozen=True)
class LoweredWorkflow:
    typed_workflow: TypedWorkflowDef
    surface: SurfaceWorkflow
    origin_map: LoweringOriginMap
```

Required entrypoints:

```python
def lower_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
) -> tuple[LoweredWorkflow, ...]: ...

def validate_lowered_workflows(
    lowered: tuple[LoweredWorkflow, ...],
    *,
    workspace_root: Path,
) -> None: ...
```

Compiler entrypoint in `orchestrator/workflow_lisp/compiler.py`:

```python
@dataclass(frozen=True)
class Stage3CompileResult:
    module: WorkflowLispModule
    workflow_catalog: WorkflowCatalog
    typed_workflows: tuple[TypedWorkflowDef, ...]
    lowered_workflows: tuple[LoweredWorkflow, ...]


def compile_stage3_module(
    path: Path,
    *,
    validate_shared: bool = True,
    workspace_root: Path | None = None,
) -> Stage3CompileResult: ...
```

Required diagnostics for this tranche:

```text
workflow_definition_duplicate
workflow_param_duplicate
workflow_return_type_invalid
workflow_call_unknown
workflow_signature_mismatch
return_type_mismatch
provider_result_return_type_invalid
command_result_return_type_invalid
command_result_argv_invalid
inline_python_command_in_workflow
inline_shell_command_in_workflow
source_map_missing
```

Reuse existing codes where the meaning already matches:

```text
type_unknown
type_mismatch
variant_ref_unproved
variant_ref_wrong_variant
record_field_unknown
record_field_missing
union_variant_unknown
```

## Deterministic Lowering Rules

Keep these implementation choices fixed so the engineer does not have to re-decide them during execution.

Workflow definition syntax:

- Require one body expression per `defworkflow`.
- Register every workflow name before typechecking any body so same-file forward calls work.
- Reject duplicate workflow names with `workflow_definition_duplicate`.
- Reject duplicate parameter names within one workflow with `workflow_param_duplicate`.

Workflow return types:

- Allow only `RecordTypeRef` or `UnionTypeRef` as Stage 3 workflow return types.
- Reject primitive, enum, or path returns with `workflow_return_type_invalid`.

`call` lowering:

- Lower one `call` expression to one `SurfaceStep` with `kind=SurfaceStepKind.CALL`.
- Use `call_alias` equal to the callee workflow name.
- Lower authored keyword bindings into `call_bindings`.
- The typed result of the expression is the callee return type ref.
- Keep same-version checking inside the shared validation bridge; compile-time checks still ensure the callee exists and binding types match the signature.

`provider-result` lowering:

- Lower record returns to `SurfaceStepKind.PROVIDER` with `output_bundle`.
- Lower union returns to `SurfaceStepKind.PROVIDER` with `variant_output`.
- Set `inject_output_contract=True` so existing prompt-contract injection remains authoritative.
- Do not parse stdout or markdown. The structured contract alone defines the semantic output.

`command-result` lowering:

- Lower record returns to `SurfaceStepKind.COMMAND` with `output_bundle`.
- Lower union returns to `SurfaceStepKind.COMMAND` with `variant_output`.
- Reject argv forms that encode shell glue:
  - `("python" "-c" ...)`
  - `("python" "-" ...)`
  - `("bash" "-c" ...)`
  - `("sh" "-c" ...)`
  - one-string wrappers that imply shell parsing instead of stable executable arguments
- Allow stable script and executable launches such as `("python" "scripts/run_checks.py" "--out" out-path)`.

Structured result contracts:

- Record type -> `output_bundle`.
- Union type -> `variant_output`.
- Use `variant` with JSON pointer `/variant` as the discriminant field name for union outputs.
- Keep `shared_fields` empty in this slice; Stage 1/2 types do not model shared union fields separately.

Generated bundle paths:

- Use one deterministic compiler-owned scheme:

```text
.orchestrate/workflow_lisp/<workflow-name>/<step-id>/result.json
```

- Base the path only on authored workflow identity and deterministic step ids.
- Do not use timestamps, counters, or runtime state paths.

Workflow boundary flattening:

- Keep structured parameter and return types authoritative in frontend artifacts.
- Localize temporary flattening for `SurfaceWorkflow.inputs` / `outputs` to `contracts.py`.
- Use deterministic generated names such as `<param>__<field>` for flattened record leaves.
- Record every flattened field mapping in the lowering origin map so shared-validation failures can be remapped to the authored parameter or return field span.

Shared validation bridge:

- Construct `SurfaceWorkflow` and `SurfaceStep` records directly.
- Reuse existing shared validation logic through an in-memory bridge only. Do not emit YAML text or round-trip through YAML parsing.
- If a tiny adapter is needed, keep it frontend-local in `orchestrator/workflow_lisp/lowering.py` or `compiler.py` and feed in-memory dict projections to `WorkflowLoader` helper methods only after the authoritative `SurfaceWorkflow` exists.
- Any shared validation failure against a generated step id, contract field, or bundle path must be remapped to a `LispFrontendDiagnostic` using the origin map before being raised.

## Task 1: Add Workflow Definitions And Signature Registration

**Files:**

- Create: `orchestrator/workflow_lisp/workflows.py`
- Create: `tests/test_workflow_lisp_workflows.py`
- Create: `tests/fixtures/workflow_lisp/valid/workflow_definitions.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/duplicate_workflow_definition.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/duplicate_workflow_param.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/workflow_return_type_invalid.orc`

- [ ] **Step 1: Write failing workflow-definition tests first**

Cover:

- elaboration of one module with multiple `defworkflow` forms;
- same-file forward signature registration;
- duplicate workflow names failing with `workflow_definition_duplicate`;
- duplicate parameter names failing with `workflow_param_duplicate`;
- invalid non-record/non-union return types failing with `workflow_return_type_invalid`.

Use these test names:

```python
def test_elaborate_workflow_definitions_builds_same_file_catalog() -> None: ...
def test_build_workflow_catalog_rejects_duplicate_workflow_names() -> None: ...
def test_typecheck_workflow_definitions_rejects_duplicate_parameter_names() -> None: ...
def test_typecheck_workflow_definitions_requires_record_or_union_return_type() -> None: ...
```

- [ ] **Step 2: Add `.orc` fixtures for valid and invalid Stage 3 workflow headers**

Fixture requirements:

- `workflow_definitions.orc` must include at least two workflows where the first calls the second by name.
- One valid workflow should use record parameters plus a union return type so later tasks can reuse the same fixture.
- Invalid fixtures should isolate exactly one failure mode each.

- [ ] **Step 3: Implement `WorkflowDef`, `WorkflowSignature`, catalog building, and definition elaboration**

Implementation requirements:

- reuse `WorkflowLispSyntaxModule` from Stage 1 instead of reparsing or rebuilding syntax objects;
- keep `WorkflowDef.body` as a `SyntaxNode` so Stage 2/3 expression elaboration still has full span metadata;
- resolve parameter and return types through `FrontendTypeEnvironment`;
- reject duplicate workflow names and duplicate parameter names deterministically;
- export the new Stage 3 symbols from `__init__.py` only after this task compiles cleanly.

- [ ] **Step 4: Run the workflow-definition test module**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -q
```

Expected: workflow-definition tests still fail on missing effectful expression and lowering support, but elaboration and catalog tests pass.

## Task 2: Extend The Expression Layer For `call`, `provider-result`, And `command-result`

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Create: `tests/fixtures/workflow_lisp/valid/structured_results.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/unknown_callee.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/provider_result_bad_return.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/command_result_bad_return.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/inline_python_command_result.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/inline_shell_command_result.orc`

- [ ] **Step 1: Add failing expression-elaboration tests for the new effectful forms**

Cover:

- `(call helper :arg value ...)` elaborates to `CallExpr`;
- `(provider-result provider-expr :prompt prompt-expr :inputs (...) :returns ReturnType)` elaborates to `ProviderResultExpr`;
- `(command-result step-name :argv (...) :returns ReturnType)` elaborates to `CommandResultExpr`;
- malformed keyword shapes fail with stable frontend diagnostics rather than generic Python errors.

Use these test names:

```python
def test_elaborate_expression_supports_call_provider_result_and_command_result() -> None: ...
def test_elaborate_expression_rejects_malformed_effectful_forms() -> None: ...
```

- [ ] **Step 2: Implement the new expression nodes and elaboration branches**

Implementation requirements:

- preserve all Stage 2 behavior for existing expression forms;
- keep elaboration shape-only and typed-agnostic;
- store effectful form spans on the full authored form, not just the head symbol;
- do not introduce a general list-literal feature just to support `:inputs` or `:argv`;
- keep `call` bindings as ordered pairs to preserve authored determinism.

- [ ] **Step 3: Re-run the workflow-expression tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -q
```

Expected: elaboration tests pass; typing/lowering tests still fail.

## Task 3: Typecheck Workflow Bodies And Enforce Stage 3 Command Rules

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Create: `tests/test_workflow_lisp_structured_results.py`

- [ ] **Step 1: Add failing typing tests for workflow calls and structured-result forms**

Cover:

- `call` succeeds when keyword bindings match the callee signature exactly;
- unknown callees fail with `workflow_call_unknown`;
- binding type mismatches fail with `workflow_signature_mismatch` or `type_mismatch`;
- workflow bodies whose typed result differs from the declared return type fail with `return_type_mismatch`;
- `provider-result` rejects non-record/non-union `:returns` types with `provider_result_return_type_invalid`;
- `command-result` rejects non-record/non-union `:returns` types with `command_result_return_type_invalid`;
- `provider-result` provider and prompt operands must resolve as `Provider` and `Prompt`;
- `command-result` rejects inline Python and shell glue with the hard error codes from the command-adapter contract.

Use these test names:

```python
def test_typecheck_workflow_definitions_validates_same_file_call_signatures() -> None: ...
def test_typecheck_workflow_definitions_rejects_unknown_callees() -> None: ...
def test_typecheck_workflow_definitions_rejects_return_type_mismatches() -> None: ...
def test_typecheck_provider_result_requires_record_or_union_return_types() -> None: ...
def test_typecheck_command_result_rejects_inline_shell_and_python_glue() -> None: ...
```

- [ ] **Step 2: Extend the typechecker to understand effectful forms**

Implementation requirements:

- keep current Stage 2 tests passing unchanged;
- accept an optional `workflow_catalog` parameter rather than duplicating the Stage 2 checker in a second code path;
- seed the initial `ValueEnvironment` for each workflow body from its parameters;
- typecheck nested input and argv expressions using the same proof-aware checker used for pure expressions;
- add focused argv validation helpers that classify rejected glue patterns before any lowering occurs.

- [ ] **Step 3: Implement workflow-definition typechecking**

Implementation requirements:

- typecheck every workflow body after the full catalog is built;
- keep the body result type equal to the declared return type exactly;
- preserve authored `span` and `form_path` on all emitted diagnostics;
- do not add structural subtyping, implicit coercions, or workflow defaults in this tranche.

- [ ] **Step 4: Run the workflow and structured-result test modules**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py -q
```

Expected: typing tests pass; lowering-origin tests may still fail.

## Task 4: Derive Deterministic Structured Contracts

**Files:**

- Create: `orchestrator/workflow_lisp/contracts.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`

- [ ] **Step 1: Add failing contract-derivation tests**

Cover:

- record return type generates an `output_bundle` payload with deterministic `path` and one field per record field;
- union return type generates a `variant_output` payload with `variant` discriminant at `/variant` and one field list per variant;
- generated bundle paths are stable across repeated compilations of the same module;
- workflow signature flattening for record parameters/returns is deterministic and reversible through recorded field metadata.

Use these test names:

```python
def test_derive_structured_result_contract_builds_output_bundle_for_record_results() -> None: ...
def test_derive_structured_result_contract_builds_variant_output_for_union_results() -> None: ...
def test_generated_bundle_paths_are_deterministic() -> None: ...
def test_workflow_signature_contract_flattening_records_origin_metadata() -> None: ...
```

- [ ] **Step 2: Implement `contracts.py`**

Implementation requirements:

- map frontend primitive/path types onto the shared workflow contract vocabulary already accepted by `WorkflowLoader`;
- keep `output_bundle` / `variant_output` generation centralized here, not scattered across lowering code;
- localize all record-field flattening to this module;
- keep the flattening metadata explicit so later runtime-integrated work can replace it without rediscovering the mapping.

- [ ] **Step 3: Run the structured-result contract tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_structured_results.py -q
```

Expected: contract derivation tests pass; surface-lowering and remap tests may still fail.

## Task 5: Lower Typed Workflows Into Shared Handoff Records And Remap Validation Failures

**Files:**

- Create: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Create: `tests/fixtures/workflow_lisp/invalid/shared_validation_remap.orc`

- [ ] **Step 1: Add failing lowering tests before implementation**

Cover:

- one typed `defworkflow` lowers to one `SurfaceWorkflow` with `version="2.14"`;
- `call` lowers to a `SurfaceStepKind.CALL` step with deterministic `call_alias`, `step_id`, and `call_bindings`;
- `provider-result` and `command-result` lower to provider/command steps with the generated structured contract attached;
- origin maps include workflow name, step id, generated bundle path, and flattened boundary contract field coverage;
- a deliberately invalid lowered contract produces a remapped `LispFrontendDiagnostic` anchored to the original `.orc` span rather than an opaque generated step id.

Use these test names:

```python
def test_lower_workflow_definitions_builds_surface_workflows_without_yaml_text() -> None: ...
def test_lower_workflow_definitions_attaches_origin_map_for_generated_steps_and_contracts() -> None: ...
def test_validate_lowered_workflows_remaps_shared_validation_failures_to_authored_spans() -> None: ...
```

- [ ] **Step 2: Implement surface lowering and origin-map recording**

Implementation requirements:

- construct `SurfaceWorkflow`, `SurfaceStep`, `SurfaceStepCommonConfig`, and `SurfaceContract` records directly;
- derive deterministic workflow names, authored ids, and step ids from the workflow name plus expression position;
- keep generated bundle paths and flattened boundary fields in the origin map;
- call `lower_surface_workflow(surface)` only after shared validation passes.

- [ ] **Step 3: Implement the shared-validation bridge**

Implementation requirements:

- keep the authoritative lowered object as `SurfaceWorkflow`;
- if the existing shared validation entrypoints only operate on mapping-shaped data, add a minimal in-memory projection from `SurfaceWorkflow` to the required validation shape inside the frontend bridge;
- do not write temporary YAML files and do not invoke YAML parsing;
- catch shared validation errors and convert them to `LispFrontendDiagnostic` records by consulting `LoweringOriginMap`;
- if any validation message refers to a generated id with no origin entry, raise `source_map_missing` instead of surfacing an untraceable failure.

- [ ] **Step 4: Run the lowering test module**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -q
```

Expected: lowering and remap tests pass.

## Task 6: Add The Stage 3 Compiler Entrypoint And Full Frontend Verification

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Add failing compiler-entrypoint tests**

Cover:

- `compile_stage3_module(...)` returns the typed Stage 3 result object when validation succeeds;
- `validate_shared=False` skips the shared-validation bridge but still returns lowered `SurfaceWorkflow` objects;
- `validate_shared=True` runs the remapping bridge and raises one `LispFrontendCompileError` containing the remapped diagnostics tuple on failure.

Use these test names:

```python
def test_compile_stage3_module_returns_lowered_workflow_artifacts() -> None: ...
def test_compile_stage3_module_can_skip_shared_validation() -> None: ...
def test_compile_stage3_module_surfaces_remapped_shared_validation_failures() -> None: ...
```

- [ ] **Step 2: Implement `compile_stage3_module(...)`**

Implementation requirements:

- reuse `compile_stage1_module(...)` rather than forking definition validation;
- obtain the syntax module from the same parsed tree used for Stage 1 so spans stay aligned;
- sequence the pipeline exactly as: Stage 1 compile -> workflow elaboration -> catalog build -> workflow body typecheck -> contract derivation -> lowering -> optional shared validation;
- keep the raised exception type as `LispFrontendCompileError`.

- [ ] **Step 3: Export the Stage 3 public APIs**

Add only the new Stage 3 names required by tests and later slices to `__init__.py`. Do not rename or remove the existing Stage 1 and Stage 2 exports.

- [ ] **Step 4: Run collect-only on the new test modules**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
```

Expected: collection succeeds and discovers the new Stage 3 tests.

- [ ] **Step 5: Run the narrow Stage 3 suites in the approved order**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -q
python -m pytest tests/test_workflow_lisp_structured_results.py -q
python -m pytest tests/test_workflow_lisp_lowering.py -q
```

Expected: all three Stage 3 modules pass.

- [ ] **Step 6: Run the frontend regression pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
```

Expected: the existing Stage 1 and Stage 2 suites still pass alongside the new Stage 3 suites.

## Verification Sequence

Use this exact command order during execution:

1. `python -m pytest --collect-only tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q`
2. `python -m pytest tests/test_workflow_lisp_workflows.py -q`
3. `python -m pytest tests/test_workflow_lisp_structured_results.py -q`
4. `python -m pytest tests/test_workflow_lisp_lowering.py -q`
5. `python -m pytest tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q`

If any new test file names change during implementation, update the selectors and also re-run the collect-only command before claiming completion.

## Acceptance Checklist

Treat the work item as complete only when all of these are true:

- bounded `defworkflow` definitions elaborate into a dedicated workflow-definition layer with same-file signature registration;
- `call`, `provider-result`, and `command-result` typecheck against Stage 1 and Stage 2 type authority rather than ad hoc dict inspection or prompt text;
- record and union result types generate deterministic `output_bundle` or `variant_output` contracts with compiler-owned bundle paths;
- lowered workflows produce shared typed handoff records directly, not YAML text;
- the shared-validation bridge runs without `.orc` loader or CLI integration;
- generated-step, generated-contract, and generated-bundle-path validation failures remap back to authored `.orc` spans;
- `command-result` rejects inline Python and shell glue per the command-adapter contract;
- the full Stage 1 + Stage 2 + Stage 3 frontend regression command passes.

## Risks And Guardrails

- Risk: Stage 3 quietly forks the existing validation rules.
  Guardrail: keep output-contract and workflow-boundary validation delegated to shared code and treat frontend checks as a narrow prefilter only.

- Risk: workflow boundary flattening leaks into the source language as an author-facing rule.
  Guardrail: localize flattening to `contracts.py` / `lowering.py` and record every generated field in the origin map.

- Risk: lowering falls back to YAML-shaped strings or temporary files because the shared validation seam is awkward.
  Guardrail: forbid YAML serialization in tests; assert that lowering returns `SurfaceWorkflow` records directly and validate through an in-memory bridge only.

- Risk: inline command glue sneaks back in under permissive argv handling.
  Guardrail: add dedicated invalid fixtures and hard-error tests for `python -c`, `python -`, `bash -c`, and `sh -c`.

- Risk: remapped diagnostics lose source fidelity when generated ids are involved.
  Guardrail: require origin-map assertions in lowering tests and emit `source_map_missing` if any generated validation failure lacks a source entry.
