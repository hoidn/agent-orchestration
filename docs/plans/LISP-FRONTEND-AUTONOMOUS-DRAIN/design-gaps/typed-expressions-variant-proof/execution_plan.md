# Typed Expressions And Variant Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Workflow Lisp Stage 2 expression layer required by the MVP: bounded expression elaboration and type/proof checking for literals, names, record construction, dotted field access, `let*`, and exhaustive `match`, while keeping the entire slice frontend-local and pre-lowering.

**Architecture:** Reuse the existing Stage 1 pipeline as the only type authority: `reader.py` builds parse trees, `syntax.py` provides `SyntaxNode`, and `definitions.py` plus `compiler.py` produce a validated `WorkflowLispModule`. Layer three new modules on top of that boundary: `expressions.py` for shape-only expression elaboration, `type_env.py` for resolved type lookups derived from Stage 1 definitions and the prelude, and `typecheck.py` for lexical type checking plus frontend-local variant-proof scopes. Do not add runtime behavior, loader integration, or Core Workflow AST lowering in this slice.

**Tech Stack:** Python 3 dataclasses and frozen records, existing `orchestrator.workflow_lisp` Stage 1 modules, `pathlib.Path`, pytest, `read_sexpr_text(...)` for inline expression fixtures, and the existing `.orc` definition fixtures under `tests/fixtures/workflow_lisp/`.

---

## Context And Boundaries

Read these inputs before implementation:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Current baseline to assume:

- Stage 1 code already exists in `orchestrator/workflow_lisp/` with `compiler.py`, `definitions.py`, `diagnostics.py`, `reader.py`, `sexpr.py`, `spans.py`, and `syntax.py`.
- Stage 1 tests already exist in `tests/test_workflow_lisp_reader.py`, `tests/test_workflow_lisp_definitions.py`, and `tests/test_workflow_lisp_diagnostics.py`.
- `progress_ledger.json` is currently empty, so treat the repo state and passing checks as the source of truth rather than any recorded partial progress.

Hard scope limits:

- Implement only the Stage 2 typed-expression and variant-proof slice described in the work-item context.
- Keep Stage 1 definitions as the only top-level type authority for this tranche.
- Support only these authored expression forms:
  - string, int, and bool literals
  - lexical name references
  - dotted field access
  - `(record Type :field expr ...)`
  - `(let* ((name expr) ...) body)`
  - `(match subject ((VARIANT binding) body) ...)`
- Keep the entire public API pure and pre-lowering.
- Preserve typed diagnostics with authored spans and form paths.

Explicit non-goals:

- No `defworkflow`, `defproc`, `call`, `provider-result`, `command-result`, or any effectful expression form.
- No Core Workflow AST lowering, semantic IR, executable IR, runtime execution, YAML generation, or `WorkflowLoader` integration.
- No macros, imports/exports, module resolution, higher-order workflow refs, or standard-library phase procedures.
- No new top-level test-only authoring forms.
- No command adapters, legacy adapters, inline command glue, or runtime-owned proof/state behavior.

Semantic rules this plan must preserve:

- `let*` is sequential. Each binding can reference earlier bindings and is visible in the body. Duplicate names inside a single `let*` binding list are rejected. Nested scopes may shadow outer names normally.
- Dotted symbol resolution is lexical-name first. If the full dotted token is bound, keep it as a `NameExpr`. Only split on `.` when the first segment names a bound value and the full token is not bound.
- `(record Type ...)` requires a known record type, every required field exactly once, no unknown fields, no duplicate fields, and exact field-type matches.
- `match` requires a union subject, one arm per declared variant, no unknown variants, no duplicate arms, and one common result type across all arm bodies.
- Variant-specific fields are available only inside proof contexts established by `match`. Access outside proof fails with `variant_ref_unproved`. Access under the wrong variant proof fails with `variant_ref_wrong_variant`.
- Proof is frontend-local in this slice. It narrows authored expressions during checking only and does not claim any shared runtime or IR-level proof representation yet.

## File Map

Create:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_variant_proofs.py`

Modify:

- `orchestrator/workflow_lisp/__init__.py`

Reuse without broadening scope:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/sexpr.py`
- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `tests/test_workflow_lisp_reader.py`
- `tests/test_workflow_lisp_definitions.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/fixtures/workflow_lisp/valid/type_definitions.orc`

Do not modify unless a targeted failing test proves it is necessary:

- `orchestrator/loader.py`
- `orchestrator/workflow/`
- CLI/runtime/demo workflow code

## Concrete Public Surface

Implement the minimum reusable surface needed by later workflow-body slices.

Resolved type references in `orchestrator/workflow_lisp/type_env.py`:

```python
@dataclass(frozen=True)
class PrimitiveTypeRef:
    name: str


@dataclass(frozen=True)
class PathTypeRef:
    name: str
    definition: PathDef


@dataclass(frozen=True)
class RecordTypeRef:
    name: str
    definition: RecordDef


@dataclass(frozen=True)
class UnionTypeRef:
    name: str
    definition: UnionDef


@dataclass(frozen=True)
class VariantCaseTypeRef:
    union_name: str
    variant_name: str
    definition: UnionVariant
```

Environment entrypoints:

```python
class FrontendTypeEnvironment:
    @classmethod
    def from_module(cls, module: WorkflowLispModule) -> "FrontendTypeEnvironment": ...

    def resolve_type(self, name: str, *, span: SourceSpan, form_path: tuple[str, ...]) -> TypeRef: ...
    def record_field(
        self,
        record_type: RecordTypeRef | VariantCaseTypeRef,
        field_name: str,
        *,
        span: SourceSpan,
        form_path: tuple[str, ...],
    ) -> TypeRef: ...
    def union_variant(
        self,
        union_type: UnionTypeRef,
        variant_name: str,
        *,
        span: SourceSpan,
        form_path: tuple[str, ...],
    ) -> VariantCaseTypeRef: ...
```

Use a single internal alias:

```python
TypeRef = PrimitiveTypeRef | PathTypeRef | RecordTypeRef | UnionTypeRef | VariantCaseTypeRef
```

Expression AST in `orchestrator/workflow_lisp/expressions.py`:

```python
@dataclass(frozen=True)
class NameExpr:
    name: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class LiteralExpr:
    value: str | int | bool
    literal_kind: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class FieldAccessExpr:
    base: NameExpr
    fields: tuple[str, ...]
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class RecordExpr:
    type_name: str
    fields: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class LetStarExpr:
    bindings: tuple[tuple[str, "ExprNode"], ...]
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class MatchArm:
    variant_name: str
    binding_name: str
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class MatchExpr:
    subject: "ExprNode"
    arms: tuple[MatchArm, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
```

Elaboration entrypoint:

```python
ExprNode = NameExpr | LiteralExpr | FieldAccessExpr | RecordExpr | LetStarExpr | MatchExpr


def elaborate_expression(node: SyntaxNode, *, bound_names: frozenset[str]) -> ExprNode: ...
```

Typed checking surface in `orchestrator/workflow_lisp/typecheck.py`:

```python
@dataclass(frozen=True)
class TypedExpr:
    expr: ExprNode
    type_ref: TypeRef
    span: SourceSpan
    form_path: tuple[str, ...]


ValueEnvironment = Mapping[str, TypeRef]


@dataclass(frozen=True)
class ProofFact:
    subject_name: str
    variant_name: str
    variant_type: VariantCaseTypeRef


@dataclass(frozen=True)
class ProofScope:
    facts: Mapping[str, ProofFact]
```

Checker entrypoint:

```python
def typecheck_expression(
    expr: ExprNode,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: ValueEnvironment,
    proof_scope: ProofScope | None = None,
) -> TypedExpr: ...
```

Required diagnostics for this tranche:

```text
expression_form_unknown
binding_duplicate
match_subject_not_union
type_unknown
type_mismatch
record_field_unknown
record_field_missing
record_field_duplicate
union_variant_unknown
union_match_non_exhaustive
variant_ref_unproved
variant_ref_wrong_variant
```

Implementation constraints:

- Reuse `LispFrontendCompileError` and `LispFrontendDiagnostic` for every failure.
- Keep every new dataclass `frozen=True`.
- Carry authored `span` and `form_path` on every new node.
- Report dotted-access errors at the full dotted token span because the reader does not preserve per-segment spans.
- Keep exact type equality in this slice. Do not invent structural subtyping, type coercions, or contract weakening.
- Use `tests/fixtures/workflow_lisp/valid/type_definitions.orc` as the shared Stage 1 type-authority fixture unless a failing test demonstrates an actual gap.

## Task 1: Add The Resolved Type Environment

**Files:**

- Create: `orchestrator/workflow_lisp/type_env.py`
- Create: `tests/test_workflow_lisp_expressions.py`

- [ ] **Step 1: Write failing environment tests first**

Add tests that compile `tests/fixtures/workflow_lisp/valid/type_definitions.orc` through `compile_stage1_module(...)`, build `FrontendTypeEnvironment.from_module(...)`, and assert:

- every Stage 1 prelude type in `PRELUDE_TYPE_NAMES` resolves as `PrimitiveTypeRef`;
- `ChecksResult` resolves as `RecordTypeRef`;
- `ImplementationState` resolves as `UnionTypeRef`;
- `WorkReport` resolves as `PathTypeRef`;
- `union_variant(...)` returns `VariantCaseTypeRef` with the expected payload fields.

Use these test names:

```python
def test_frontend_type_environment_resolves_stage1_definitions() -> None: ...
def test_frontend_type_environment_exposes_union_variant_payloads() -> None: ...
```

- [ ] **Step 2: Implement resolved refs and environment helpers**

Implementation requirements:

- derive the environment strictly from `WorkflowLispModule.definitions` plus the existing prelude names;
- centralize type lookup in `FrontendTypeEnvironment` instead of scattering raw string lookups through the checker;
- when a lookup fails, raise `LispFrontendCompileError` with `type_unknown`, anchored to the caller-provided `span` and `form_path`.

- [ ] **Step 3: Run the expressions test module**

Run:

```bash
python -m pytest tests/test_workflow_lisp_expressions.py -q
```

Expected: the environment tests pass; later expression tests may still fail.

## Task 2: Elaborate The Bounded Expression AST

**Files:**

- Create: `orchestrator/workflow_lisp/expressions.py`
- Modify: `tests/test_workflow_lisp_expressions.py`

- [ ] **Step 1: Add failing elaboration tests before implementation**

Use `read_sexpr_text(...)` plus a manually constructed `SyntaxNode` for one expression per test. Do not introduce fake top-level `.orc` forms just to host expressions. Cover:

- string, int, and bool literals;
- exact bound-name lookup beating dotted splitting;
- dotted access elaborating as `FieldAccessExpr` when only the first segment is bound;
- `(record ChecksResult :status "ok" :report report-path)`;
- `(let* ((first report-path) (second first)) second)`;
- `(match attempt ((COMPLETED completed) completed.execution_report) ((BLOCKED blocked) blocked.progress_report))`;
- unknown expression heads failing with `expression_form_unknown`.

Use these test names:

```python
def test_elaborate_expression_handles_literals_names_records_and_letstar() -> None: ...
def test_elaborate_expression_prefers_exact_bound_names_over_field_access() -> None: ...
def test_elaborate_expression_builds_match_arms_with_spans_and_form_paths() -> None: ...
def test_elaborate_expression_rejects_unknown_expression_forms() -> None: ...
```

- [ ] **Step 2: Implement `elaborate_expression(...)`**

Implementation requirements:

- keep elaboration shape-only; leave semantic typing to `typecheck.py`;
- accept an existing `SyntaxNode` and `bound_names`;
- thread updated `bound_names` into nested `let*` bodies and `match` arm bodies so dotted-name resolution obeys the approved lexical-first rule;
- preserve the authored `form_path` from the incoming `SyntaxNode` on every produced node.

- [ ] **Step 3: Re-run the expressions test module**

Run:

```bash
python -m pytest tests/test_workflow_lisp_expressions.py -q
```

Expected: elaboration tests pass; type-check tests may still fail.

## Task 3: Typecheck Literals, Names, Records, Field Access, And `let*`

**Files:**

- Create: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `tests/test_workflow_lisp_expressions.py`

- [ ] **Step 1: Add failing non-proof type-check tests**

Extend `tests/test_workflow_lisp_expressions.py` to cover:

- literal inference to `String`, `Int`, and `Bool`;
- exact name lookup from an explicit initial `value_env`;
- record construction success with exact required field coverage;
- missing required record fields failing with `record_field_missing`;
- duplicate record fields failing with `record_field_duplicate`;
- unknown record fields failing with `record_field_unknown`;
- field access success from a record-typed value;
- `let*` binding order and later-binding visibility;
- duplicate `let*` bindings failing with `binding_duplicate`;
- mismatched record field types failing with `type_mismatch`.

Use these test names:

```python
def test_typecheck_expression_validates_record_exactness() -> None: ...
def test_typecheck_expression_supports_sequential_letstar_bindings() -> None: ...
def test_typecheck_expression_rejects_duplicate_letstar_bindings() -> None: ...
def test_typecheck_expression_rejects_record_field_type_mismatches() -> None: ...
```

- [ ] **Step 2: Implement the base checker**

Implementation requirements:

- typecheck against `FrontendTypeEnvironment` plus a caller-supplied lexical `value_env`;
- allow field access on `RecordTypeRef` and `VariantCaseTypeRef`;
- if dotted access is rooted at a union-typed subject outside proof, emit `variant_ref_unproved` instead of pretending the field is simply missing;
- keep `let*` environments lexical and deterministic, with each binding extending the environment for later bindings and the body;
- compare types by exact resolved type identity for this tranche.

- [ ] **Step 3: Re-run the expressions test module**

Run:

```bash
python -m pytest tests/test_workflow_lisp_expressions.py -q
```

Expected: all non-proof expression tests pass.

## Task 4: Add Exhaustive `match` Checking And Variant Proof Narrowing

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Create: `tests/test_workflow_lisp_variant_proofs.py`

- [ ] **Step 1: Write failing proof-focused tests first**

Cover these cases:

- `match` subject must be a union, otherwise `match_subject_not_union`;
- every declared variant must appear exactly once, otherwise `union_match_non_exhaustive`;
- unknown variant names fail with `union_variant_unknown`;
- arm binding type narrows to `VariantCaseTypeRef`;
- the matched subject itself is also narrowed inside each arm;
- `attempt.execution_report` outside proof fails with `variant_ref_unproved`;
- access to a field from the wrong proven variant fails with `variant_ref_wrong_variant`;
- all arm bodies must resolve to the same type, otherwise `type_mismatch`.

Use these test names:

```python
def test_typecheck_match_requires_union_subject_and_exhaustive_variants() -> None: ...
def test_typecheck_match_narrows_binding_and_subject_inside_each_arm() -> None: ...
def test_typecheck_variant_field_access_requires_proof_context() -> None: ...
def test_typecheck_match_requires_consistent_arm_result_types() -> None: ...
```

- [ ] **Step 2: Implement proof-scope tracking and `match` checking**

Implementation requirements:

- represent proof scope as a frontend-local mapping from subject name to a proven `ProofFact`;
- create a fresh proof scope per arm that narrows both the original subject name and the arm alias to the selected variant;
- reject proof leakage by restoring the outer scope after each arm;
- keep arm result-type comparison exact and deterministic;
- preserve stable diagnostic ordering when multiple `match` errors are present.

- [ ] **Step 3: Run the proof test module**

Run:

```bash
python -m pytest tests/test_workflow_lisp_variant_proofs.py -q
```

Expected: PASS for exhaustive `match` and variant-proof behavior.

## Task 5: Export The Public Surface And Run The Required Regression Checks

**Files:**

- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_variant_proofs.py`

- [ ] **Step 1: Export only the stable Stage 2 surface**

Export from `orchestrator/workflow_lisp/__init__.py`:

- all resolved type-ref dataclasses plus `FrontendTypeEnvironment`;
- expression AST nodes plus `elaborate_expression`;
- `TypedExpr`, `ProofFact`, `ProofScope`, and `typecheck_expression`.

Do not export internal helper functions.

- [ ] **Step 2: Run the exact collect-only command recorded for this work item**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py -q
```

Expected: collection succeeds and includes the new test modules.

- [ ] **Step 3: Run the exact focused verification commands from `check_commands.json`**

Run exactly:

```bash
python -m pytest tests/test_workflow_lisp_expressions.py -q
python -m pytest tests/test_workflow_lisp_variant_proofs.py -q
python -m pytest tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py -q
```

Expected:

- the new expression tests pass;
- the new proof tests pass;
- the existing Stage 1 reader, definitions, and diagnostics suites still pass unchanged.

- [ ] **Step 4: Record implementation evidence in the execution handoff**

The execution handoff must state:

- which files changed;
- which semantic rules were implemented exactly as planned;
- the exact pytest commands run and whether they passed;
- any intentionally deferred edge cases that remain out of scope.

## Notes For The Implementer

- Favor small local helpers in `typecheck.py` over a large recursive function with mixed elaboration and type resolution responsibilities.
- Keep `expressions.py` unaware of `WorkflowLispModule`; it should work from `SyntaxNode` plus `bound_names` only.
- Keep `type_env.py` ignorant of proof scopes; it should only answer definition-derived type questions.
- Keep `typecheck.py` ignorant of top-level module compilation; it should consume already elaborated expressions and an already built `FrontendTypeEnvironment`.
- If a test suggests changing Stage 1 reader or definition behavior, stop and confirm the failure is a real Stage 2 dependency instead of scope creep.

## Verification Notes

- No orchestrator or demo smoke run is required for this work item because it does not modify workflows, prompts, artifact contracts, runtime loading, or execution semantics.
- Do not claim success from inspection alone. The exact commands in `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json` are the required visible evidence.
- Keep verification narrow. If unrelated tests fail, determine whether the failure is a genuine regression before broadening scope.
