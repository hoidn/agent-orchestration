# Let-Proc Compile-Time Local Proc Bindings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bounded V1 Workflow Lisp `let-proc` surface so authors can define one lexical local procedure that closure-converts into a generated private procedure and reuses the existing `defproc` / `ProcRef` / specialization / lowering pipeline without introducing runtime procedure values.

**Architecture:** Treat `let-proc` as a frontend-only normalization step. Elaboration recognizes one local binding plus explicit `:captures`, compiler/typecheck synthesize a deterministic hidden `ProcedureDef` plus metadata, ProcRef resolution exposes the generated callable only to `(proc-ref local-name)` inside the lexical body, and lowering/source-map layers handle the generated procedure exactly like existing hidden procedures while preserving authored `let-proc` provenance.

**Tech Stack:** Python 3, `pytest`, Workflow Lisp frontend modules under `orchestrator/workflow_lisp/`, existing shared workflow validation/source-map pipeline.

---

## Scope Guardrails

- Implement only the selected V1 surface from `docs/design/workflow_lisp_unified_frontend_design.md` and the reviewed implementation architecture.
- Preserve the current baseline semantics for `defproc`, `ProcRef`, `bind-proc`, shared validation, runtime execution, and hidden procedure specialization.
- Do not add nested `let-proc`, multiple local bindings, bare-name local calls, runtime closures, runtime procedure transport, or a second lowering path.
- Keep command/provider/runtime authority unchanged; generated local procedures must obey the same command-boundary and effect visibility rules as ordinary generated `defproc` bodies.

## File Map

**Primary implementation files**
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/procedure_refs.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify if needed for diagnostic classification only: `orchestrator/workflow_lisp/diagnostics.py`

**Primary test files**
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_source_map.py`

**Fixtures to add**
- Create: `tests/fixtures/workflow_lisp/valid/let_proc_proc_ref_forwarding.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_multiple_bindings.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_nested.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_unknown_capture.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_duplicate_capture.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_bare_call.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_scope_escape.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_recursive.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_generated_name_private.orc`
- Create if needed for lowering/runtime-transport coverage: one focused invalid fixture proving local proc values cannot escape through runtime-shaped surfaces.

## Required Behaviors To Prove

- `let-proc` parses only the one-binding V1 shape:

```lisp
(let-proc (run-local ((selected SelectedItem)) -> ImplementationResult
             :captures (design plan impl-provider)
             (call implementation/run
               :selected selected
               :design design
               :plan plan
               :providers impl-provider))
  (call iter-proc
    :execute (proc-ref run-local)
    :input selected))
```

- The local name is visible only to `(proc-ref local-name)` inside the containing body.
- Closure conversion expands captures into leading generated procedure parameters.
- Generated procedures are ordinary hidden procedures that participate in `build_procedure_catalog(...)`, `_typecheck_procedure_definitions(...)`, `_discover_proc_ref_specializations(...)`, `_validate_procedure_effects_and_cycles(...)`, and `lower_workflow_definitions(...)`.
- Runtime-facing artifacts contain no unresolved local procedure value, no closure object, and no authored reference to generated hidden names.
- Diagnostics and source maps point back to authored `let-proc` spans and use deterministic V1 error codes.

### Task 1: Add Fixtures And Elaboration Coverage

**Files:**
- Create: `tests/fixtures/workflow_lisp/valid/let_proc_proc_ref_forwarding.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_multiple_bindings.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_nested.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_unknown_capture.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_duplicate_capture.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/let_proc_bare_call.orc`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`

- [ ] **Step 1: Add failing expression tests for the new authored surface**

```python
def test_elaborate_expression_supports_let_proc() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(let-proc (run-local ((input WorkflowInput)) -> WorkflowOutput "
            "           :captures (fixed) "
            "           (command-result run_checks "
            '             :argv ("python" "scripts/run_checks.py" input.report fixed) '
            "             :returns WorkflowOutput)) "
            "  (proc-ref run-local))"
        ),
        bound_names=frozenset({"fixed"}),
    )
    assert type(expr).__name__ == "LetProcExpr"


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("(let-proc ((a ...) (b ...)) body)", "let_proc_multiple_bindings_unsupported"),
        ("(let-proc (local (...) -> T :captures (ctx.field) body) x)", "let_proc_capture_not_identifier"),
        ("(let-proc (local (...) -> T :captures () body) (local x))", "let_proc_bare_name_invalid"),
    ],
)
def test_elaborate_expression_rejects_invalid_let_proc_forms(source: str, code: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(_expression_syntax(source), bound_names=frozenset({"ctx"}))
    assert excinfo.value.diagnostics[0].code == code
```

- [ ] **Step 2: Run the narrow expression selector and confirm the failures are about missing `let-proc` support**

Run: `pytest tests/test_workflow_lisp_expressions.py -k let_proc -v`

Expected: FAIL with one or more of `unknown expression form`, `procedure_call_unknown`, or missing `LetProcExpr` assertions.

- [ ] **Step 3: Implement elaboration support in `expressions.py`**

Implementation requirements:
- Add `LetProcBinding` and `LetProcExpr` dataclasses to the `ExprNode` union.
- Extend `elaborate_expression(...)` / `_elaborate_list(...)` to recognize `let-proc`.
- Parse exactly one binding with `name`, residual params, `->`, return type, `:captures (...)`, local body, and outer body.
- Track a dedicated lexical local-procedure-name set during elaboration so bare `(run-local input)` becomes `let_proc_bare_name_invalid` instead of `ProcedureCallExpr`.
- Reject nested `let-proc` during elaboration instead of letting later phases rediscover the limitation.

Suggested helper shape:

```python
@dataclass(frozen=True)
class LetProcBinding:
    local_name: str
    params: tuple[ProcedureParam, ...]
    return_type_name: str
    capture_names: tuple[str, ...]
    local_body: ExprNode
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
```

- [ ] **Step 4: Re-run the expression selector**

Run: `pytest tests/test_workflow_lisp_expressions.py -k let_proc -v`

Expected: PASS for the new elaboration tests.

- [ ] **Step 5: Collect the new tests to satisfy the repo rule for added tests**

Run: `pytest --collect-only tests/test_workflow_lisp_expressions.py -k let_proc`

Expected: collected `let_proc` tests with no collection errors.

- [ ] **Step 6: Commit the slice**

Run:

```bash
git add orchestrator/workflow_lisp/expressions.py \
  tests/test_workflow_lisp_expressions.py \
  tests/fixtures/workflow_lisp/valid/let_proc_proc_ref_forwarding.orc \
  tests/fixtures/workflow_lisp/invalid/let_proc_*.orc
git commit -m "test: add let-proc expression coverage"
```

### Task 2: Add Generated Local Procedure Metadata And ProcRef Resolution

**Files:**
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/procedure_refs.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add failing tests for generated-name determinism and lexical ProcRef resolution**

```python
def test_let_proc_resolves_to_hidden_generated_proc_ref(tmp_path: Path) -> None:
    result = _compile(FIXTURES / "valid" / "let_proc_proc_ref_forwarding.orc", tmp_path=tmp_path)
    generated = [p for p in result.typed_procedures if p.definition.name.startswith("%let-proc.")]
    assert len(generated) == 1
    assert generated[0].definition.name == generated[0].signature.name
    assert generated[0].specialization is None


def test_compile_rejects_let_proc_generated_name_authored_reference(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(FIXTURES / "invalid" / "let_proc_generated_name_private.orc", tmp_path=tmp_path)
    assert excinfo.value.diagnostics[0].code == "let_proc_generated_name_private"
```

- [ ] **Step 2: Run the focused procedure selector and confirm failure**

Run: `pytest tests/test_workflow_lisp_procedures.py -k let_proc -v`

Expected: FAIL because no generated `%let-proc.` procedures or lexical local-procedure ProcRef handling exists yet.

- [ ] **Step 3: Implement generated local-procedure metadata and hidden naming**

Implementation requirements:
- In `procedures.py`, add a compiler-private metadata record such as `GeneratedLocalProcedure`.
- Add a deterministic name helper shaped like `%let-proc.<owner>.<local-name>.<hash>`.
- Include enough hash inputs to keep names stable across runs and distinct across owners: module/owner identity, `let-proc` span, local name, residual signature, ordered captures, and local body identity.
- Add helpers that materialize a generated `ProcedureDef` / `ProcedureSignature` from a `LetProcExpr` without creating a new lowering path.

- [ ] **Step 4: Extend ProcRef resolution with a lexical local-procedure layer**

Implementation requirements:
- Extend `ProcRefResolutionContext` and/or the call-site API so active lexical local procedures can be consulted before top-level/imported procedures.
- Return `ProcRefAuthoritySource(kind="lexical_local_procedure", ...)` for `(proc-ref local-name)`.
- Reject authored references to generated hidden names with `let_proc_generated_name_private`.
- Preserve existing imported/top-level/private-import behavior.

- [ ] **Step 5: Re-run the focused procedure selector**

Run: `pytest tests/test_workflow_lisp_procedures.py -k "let_proc or proc_ref" -v`

Expected: PASS for the new `let_proc` resolution tests and no regressions in neighboring `proc_ref` coverage.

- [ ] **Step 6: Collect the new tests**

Run: `pytest --collect-only tests/test_workflow_lisp_procedures.py -k let_proc`

Expected: collected `let_proc` procedure tests with no collection errors.

- [ ] **Step 7: Commit the slice**

Run:

```bash
git add orchestrator/workflow_lisp/procedures.py \
  orchestrator/workflow_lisp/procedure_refs.py \
  tests/test_workflow_lisp_procedures.py
git commit -m "feat: add lexical let-proc proc-ref resolution"
```

### Task 3: Typecheck `let-proc`, Validate Captures, And Feed Generated Procedures Into The Compiler Pipeline

**Files:**
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify if needed for phase/diagnostic metadata only: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add failing compiler/typecheck tests for captures, recursion rejection, and ordinary pipeline reuse**

```python
def test_compile_stage3_supports_let_proc_proc_ref_forwarding_and_shared_validation(tmp_path: Path) -> None:
    result = _compile_validated(FIXTURES / "valid" / "let_proc_proc_ref_forwarding.orc", tmp_path=tmp_path)
    generated = next(p for p in result.typed_procedures if p.definition.name.startswith("%let-proc."))
    assert generated.definition.name in result.procedure_catalog.signatures_by_name
    assert generated.transitive_effect_summary.transitive_effects == frozenset({UsesCommandEffect("run_checks")})


@pytest.mark.parametrize(
    ("fixture_name", "code"),
    [
        ("let_proc_unknown_capture.orc", "let_proc_capture_unknown"),
        ("let_proc_duplicate_capture.orc", "let_proc_capture_duplicate"),
        ("let_proc_recursive.orc", "let_proc_recursive_unsupported"),
        ("let_proc_scope_escape.orc", "let_proc_scope_escape"),
    ],
)
def test_compile_rejects_invalid_let_proc_scopes(tmp_path: Path, fixture_name: str, code: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(FIXTURES / "invalid" / fixture_name, tmp_path=tmp_path)
    assert excinfo.value.diagnostics[0].code == code
```

- [ ] **Step 2: Run the narrow compiler/procedure selector and confirm failure**

Run: `pytest tests/test_workflow_lisp_procedures.py -k let_proc -v`

Expected: FAIL with missing capture diagnostics, missing generated procedures, or unresolved local ProcRef behavior.

- [ ] **Step 3: Implement `LetProcExpr` typing in `typecheck.py`**

Implementation requirements:
- Add a dedicated `if isinstance(expr, LetProcExpr):` branch near the `LetStarExpr` handling.
- Validate capture names against the surrounding lexical `value_env`.
- Reject duplicate captures, capture/parameter collisions, and direct local-name value use.
- Convert capture values into ordinary generated procedure parameters.
- Typecheck the generated local body through the same procedure typing rules used by `_typecheck_procedure_definitions(...)`.
- Install `(proc-ref local-name)` into a temporary local ProcRef environment only while typing the outer lexical body.
- Preserve the rule that `let-proc` itself introduces no direct runtime effect; only ordinary generated-procedure effects should surface later through existing call/selection paths.

- [ ] **Step 4: Teach `compiler.py` to register generated local procedures before effect and specialization passes**

Implementation requirements:
- Discover generated local procedures from typed workflow/procedure bodies before `_infer_stage3_effect_summaries(...)` converges.
- Merge them into the procedure catalog and the typed procedure set before `_discover_proc_ref_specializations(...)` and `_validate_procedure_effects_and_cycles(...)`.
- Reject self-reference via `(proc-ref local-name)` inside the generated local body with `let_proc_recursive_unsupported`.
- Preserve ordinary specialization discovery and cycle detection for generated procedures after closure conversion.

Concrete seams to reuse:
- `_typecheck_procedure_definitions(...)`
- `_discover_proc_ref_specializations(...)`
- `_infer_stage3_effect_summaries(...)`
- `_validate_procedure_effects_and_cycles(...)`

- [ ] **Step 5: Re-run the focused compiler/procedure selector**

Run: `pytest tests/test_workflow_lisp_procedures.py -k let_proc -v`

Expected: PASS for valid and invalid `let_proc` compiler cases.

- [ ] **Step 6: Run adjacent ProcRef regression coverage before moving on**

Run: `pytest tests/test_workflow_lisp_procedures.py -k "proc_ref or let_proc" -v`

Expected: PASS with no regressions in existing `proc_ref` specialization/cycle tests.

- [ ] **Step 7: Collect the new tests**

Run: `pytest --collect-only tests/test_workflow_lisp_procedures.py -k let_proc`

Expected: collected `let_proc` tests with no collection errors.

- [ ] **Step 8: Commit the slice**

Run:

```bash
git add orchestrator/workflow_lisp/typecheck.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/diagnostics.py \
  tests/test_workflow_lisp_procedures.py
git commit -m "feat: typecheck and compile let-proc local procedures"
```

### Task 4: Preserve Lowering Provenance, Source Maps, And Runtime-No-Closure Guarantees

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_source_map.py`

- [ ] **Step 1: Add failing lowering/source-map tests for provenance and runtime artifact shape**

```python
def test_lowering_let_proc_reuses_generated_hidden_procedure_path(tmp_path: Path) -> None:
    result = compile_stage3_module(
        FIXTURES / "valid" / "let_proc_proc_ref_forwarding.orc",
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={"run_checks": ExternalToolBinding(name="run_checks", stable_command=("python", "scripts/run_checks.py"))},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    generated = next(p for p in result.typed_procedures if p.definition.name.startswith("%let-proc."))
    assert all(generated.definition.name != step.get("call") for workflow in result.lowered_workflows for step in workflow.authored_mapping.get("steps", []))


def test_source_map_records_let_proc_authored_lineage(tmp_path: Path) -> None:
    _, document, workflow_name = _build_source_map_document(
        FIXTURES / "valid" / "let_proc_proc_ref_forwarding.orc",
        tmp_path=tmp_path,
        selected_name="orchestrate",
    )
    workflow = document.workflows[workflow_name]
    assert any(
        "let-proc" in note
        for entry in workflow.step_ids.values()
        for note in entry.notes
    )
```

- [ ] **Step 2: Run the narrow selectors and confirm failure**

Run: `pytest tests/test_workflow_lisp_lowering.py -k let_proc -v`

Run: `pytest tests/test_workflow_lisp_source_map.py -k let_proc -v`

Expected: FAIL because no lowering provenance or source-map lineage exists for generated local procedures.

- [ ] **Step 3: Extend lowering provenance for generated local procedures**

Implementation requirements:
- Reuse the existing hidden-procedure lowering path in `_resolve_procedure_lowering(...)` and related provenance-note helpers.
- Add authored notes that mention the `let-proc` origin, local signature, capture lineage, and consuming `(proc-ref local-name)` site.
- Do not create a separate executable lowerer or special runtime representation.
- Ensure shared-validation remap can still point back to authored `let-proc` spans when errors land on generated steps or generated procedure workflows.

- [ ] **Step 4: Extend source-map coverage**

Implementation requirements:
- Ensure generated hidden procedures created from `let-proc` appear in the normal source-map build output.
- Preserve authored lineage for generated steps, validation subjects, and executable nodes through existing origin-map machinery.
- Keep runtime artifacts free of local-procedure payloads; the proof here is compile output plus lowered mapping assertions, not prompt text.

- [ ] **Step 5: Re-run the lowering and source-map selectors**

Run: `pytest tests/test_workflow_lisp_lowering.py -k let_proc -v`

Run: `pytest tests/test_workflow_lisp_source_map.py -k let_proc -v`

Expected: PASS for the new lowering/source-map coverage.

- [ ] **Step 6: Collect the new tests**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_lowering.py -k let_proc
pytest --collect-only tests/test_workflow_lisp_source_map.py -k let_proc
```

Expected: both modules collect the new tests successfully.

- [ ] **Step 7: Commit the slice**

Run:

```bash
git add orchestrator/workflow_lisp/lowering.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_source_map.py
git commit -m "feat: preserve let-proc lowering provenance"
```

### Task 5: Final Integration Verification And Evidence Capture

**Files:**
- Modify only if verification exposes a real gap; otherwise no code changes.

- [ ] **Step 1: Run the focused end-to-end frontend suite for this slice**

Run:

```bash
pytest \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_source_map.py \
  -k let_proc -v
```

Expected: PASS across all `let_proc` coverage.

- [ ] **Step 2: Run the integration check required for a DSL/frontend change**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py::test_compile_stage3_supports_let_proc_proc_ref_forwarding_and_shared_validation -v
```

Expected: PASS with shared validation enabled, proving the generated hidden procedure survives the full compile -> lowering -> validation pipeline.

- [ ] **Step 3: Run one adjacent regression band around existing ProcRef behavior**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py -k "proc_ref or let_proc" -v
```

Expected: PASS, confirming the new lexical local-procedure layer did not weaken current `ProcRef` semantics.

- [ ] **Step 4: Record the implementation evidence**

Capture in the implementation summary / handoff notes:
- which files changed;
- which fixtures were added;
- exact pytest commands run;
- confirmation that runtime artifacts contained no unresolved local procedure values;
- any intentionally deferred items that remain out of scope.

- [ ] **Step 5: Final commit**

Run:

```bash
git add -A
git commit -m "feat: implement workflow lisp let-proc local bindings"
```

## Notes For The Implementer

- Prefer reusing the current `let*` proc-ref environment threading in `typecheck.py` and `_discover_proc_ref_specializations(...)` instead of inventing a second environment model.
- Keep generated local procedures compiler-private. If authored source can reference a `%let-proc...` name directly, that is a bug.
- If `diagnostics.py` does not need explicit code classification for the new diagnostics, do not edit it just to enumerate codes.
- If a valid `let-proc` body cannot lower through the ordinary generated `defproc` path, reject with `let_proc_body_lowering_unsupported` and preserve the underlying authored context in notes.
- Do not add tests that assert prompt text or diagnostic prose beyond stable codes and materially relevant note fragments.
