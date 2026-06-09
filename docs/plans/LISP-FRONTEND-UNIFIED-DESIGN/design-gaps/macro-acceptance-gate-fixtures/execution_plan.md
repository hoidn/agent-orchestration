# Macro Acceptance-Gate Fixtures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bounded fixture-backed acceptance coverage for unified-design Section 52 so Workflow Lisp macros are proven to preserve hidden-command rejection, compile-time callable transport rejection, executable/source-map lineage validation, and stable nested-expansion diagnostics without adding new macro semantics or a second safety subsystem.

**Architecture:** Keep all macro behavior on the existing frontend pipeline: macro expansion -> type/effect validation -> lowering -> shared validation -> executable/source-map validation. Add a focused invalid-fixture taxonomy plus targeted regression tests that reuse `macro_hidden_effect`, `proc_ref_runtime_transport_forbidden`, `source_map_executable_node_unmapped` / `source_map_generated_effect_invalid` / `source_map_missing`, and existing `ExpansionFrame` provenance. The hidden-command slice must assert existing required-lint/effect/frontend ownership metadata, and the nested-diagnostics slice must assert the full two-frame call-site/definition-site rendering order rather than only generic note presence. Only touch `orchestrator/workflow_lisp/diagnostics.py`, `compiler.py`, or `source_map.py` if the new tests prove the current note ordering or lineage remap is unstable.

**Tech Stack:** Python 3, Workflow Lisp frontend modules under `orchestrator/workflow_lisp/`, `pytest`, existing fixture/build helpers, and one public `python -m orchestrator compile ...` smoke check against the existing macro fixture surface.

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_unified_frontend_design.md`
  - Sections 47-52
- `docs/design/workflow_lisp_frontend_specification.md`
  - macro pipeline and source-map sections
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-acceptance-gate-fixtures/implementation_architecture.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json`

## Scope Guardrails

- Implement only the selected `macro-acceptance-gate-fixtures` gap.
- Preserve the current macro expander, hygiene rules, hidden-effect linting, shared validation ownership, executable/source-map schema, and compile-time-only callable rules.
- Do not add runtime closures, dynamic dispatch, macro syntax redesign, new executable-node kinds, new command adapters, helper scripts, or a macro-specific transport validator.
- Keep the slice test-first and fixture-first. The point is durable acceptance evidence, not feature growth.
- `progress_ledger.json` is still empty, so assume no partial implementation has already landed.

## Current Checkout Facts

- `orchestrator/workflow_lisp/typecheck.py` already rejects macro-emitted `provider-result` and `command-result` with `macro_hidden_effect`.
- `orchestrator/workflow_lisp/type_env.py`, `workflows.py`, and `loops.py` already reject runtime `ProcRef` transport with `proc_ref_runtime_transport_forbidden`.
- `orchestrator/workflow_lisp/source_map.py` already rejects unmapped executable lineage with `source_map_executable_node_unmapped` and invalid generated-effect lineage with `source_map_generated_effect_invalid`.
- `orchestrator/workflow_lisp/compiler.py` already remaps some missing-lineage failures to `source_map_missing`.
- `tests/test_workflow_lisp_macros.py` already covers hygiene, imported hidden provider effects, and basic command/provider positive macro compilation, but not the bounded command-hidden-effect or runtime-callable-transport acceptance matrix.
- `tests/test_workflow_lisp_diagnostics.py` already renders single-frame macro notes for command/provider/name errors, but not nested multi-frame macro stacks.
- `tests/test_workflow_lisp_source_map.py` already mutates non-macro source-map documents, but not a macro-origin executable-lineage case.
- `tests/test_workflow_lisp_source_map.py` builds source-map documents through a helper that currently compiles with `validate_shared=False`, so executable-node lineage coverage must opt into shared validation or use a validated-bundle build helper explicitly.
- A naive outer-wrapper -> inner-macro-call nested fixture currently collapses to the inner macro frame on the failing node; two-frame regression coverage must instead pass the failing authored body through the outer macro into the inner macro, or else authorize a narrow provenance propagation fix in `orchestrator/workflow_lisp/macros.py`.
- `tests/fixtures/workflow_lisp/` has no dedicated macro runtime-transport fixtures and no nested macro-stack fixtures.

## File Map

**Primary test files**

- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Verify only: `tests/test_workflow_lisp_structured_results.py`

**Fixtures to add**

- Create: `tests/fixtures/workflow_lisp/invalid/macro_hidden_command_effect.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/macro_nested_hidden_command_effect.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/macro_nested_name_unknown.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/macro_proc_ref_runtime_transport.orc`
- Create: `tests/fixtures/workflow_lisp/modules/invalid/import_macro_hidden_command/neurips/entry.orc`
- Create: `tests/fixtures/workflow_lisp/modules/invalid/import_macro_hidden_command/neurips/macros.orc`

**Frontend files to modify only if failing focused tests prove it is necessary**

- Modify if needed for note ordering or metadata stabilization only: `orchestrator/workflow_lisp/diagnostics.py`
- Modify if needed for nested macro provenance propagation only: `orchestrator/workflow_lisp/macros.py`
- Modify if needed for macro-origin executable validation remap only: `orchestrator/workflow_lisp/compiler.py`
- Modify if needed for macro-origin source-map provenance validation only: `orchestrator/workflow_lisp/source_map.py`

## Required Behaviors To Prove

- Macro-emitted hidden command effects fail with `macro_hidden_effect`, preserve `required_lint` / `effect` / `frontend` ownership metadata, and preserve macro provenance in both same-file and imported-macro paths.
- Macro-emitted runtime transport of `ProcRef[...]` still fails with the existing `proc_ref_runtime_transport_forbidden` diagnostic rather than a macro-only code path.
- Macro-origin executable/source-map lineage tampering fails deterministically through the existing source-map validators and still points back to authored macro provenance.
- Nested macro expansions preserve the full two-frame expansion stack and render exactly-once call-site / definition-site note pairs in deterministic order for both effect-owned failures and downstream non-effect failures.
- Existing positive macro cases and existing authored command-boundary behavior remain green.

### Task 1: Add The Hidden Command-Effect Fixture Matrix

**Files:**

- Create: `tests/fixtures/workflow_lisp/invalid/macro_hidden_command_effect.orc`
- Create: `tests/fixtures/workflow_lisp/modules/invalid/import_macro_hidden_command/neurips/entry.orc`
- Create: `tests/fixtures/workflow_lisp/modules/invalid/import_macro_hidden_command/neurips/macros.orc`
- Modify: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Add failing tests for same-file and imported hidden command effects**

Add two focused selectors in `tests/test_workflow_lisp_macros.py` that mirror the existing provider-hidden-effect ownership assertions:

```python
def test_compile_stage3_rejects_macro_introduced_command_effects_as_macro_hidden_effect(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "invalid" / "macro_hidden_command_effect.orc",
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_hidden_effect"
    assert "hidden command effect" in diagnostic.message
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-command-workflow"
    payload = serialize_diagnostic(diagnostic)
    assert payload["diagnostic_kind"] == "required_lint"
    assert payload["validation_pass"] == "effect"
    assert payload["authority_layer"] == "frontend"


def test_compile_stage3_entrypoint_rejects_imported_macros_that_introduce_hidden_command_effects(
    tmp_path: Path,
) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint")
    source_root = MODULE_FIXTURES / "invalid" / "import_macro_hidden_command"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_fn(
            source_root / "neurips" / "entry.orc",
            source_roots=(source_root,),
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_hidden_effect"
    assert diagnostic.span.start.path.endswith("modules/invalid/import_macro_hidden_command/neurips/macros.orc")
    payload = serialize_diagnostic(diagnostic)
    assert payload["diagnostic_kind"] == "required_lint"
    assert payload["validation_pass"] == "effect"
    assert payload["authority_layer"] == "frontend"
```

- [ ] **Step 2: Add the invalid fixtures that emit `command-result` only through macros**

Implementation requirements:

- `macro_hidden_command_effect.orc` should mirror the existing provider-hidden-effect fixture pattern, but emit a `defworkflow` whose body is a macro-produced `command-result`.
- `import_macro_hidden_command/.../entry.orc` should import one exported macro and trigger the same hidden-command path through `compile_stage3_entrypoint(...)`.
- Keep the command shape aligned with `docs/design/workflow_command_adapter_contract.md`: named command boundary, stable command path, no inline shell/Python escape hatch.

- [ ] **Step 3: Run collection and the narrow macro selector**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_macros.py -k "hidden_command or imported_macros_that_introduce_hidden_command_effects" -q
pytest tests/test_workflow_lisp_macros.py -k "hidden_command or imported_macros_that_introduce_hidden_command_effects" -v
```

Expected: the new tests fail first because the fixtures and selectors do not exist yet, then pass after the fixture matrix lands.

- [ ] **Step 4: If the imported case surfaces unstable metadata, stabilize only the existing diagnostic path**

Allowed fixes only if the focused tests require them:

- preserve `macro_hidden_effect` as the code;
- preserve `diagnostic_kind == "required_lint"`, `validation_pass == "effect"`, and `authority_layer == "frontend"` on both the same-file and imported-macro failures;
- do not add a command-specific macro lint or alternate validator.

- [ ] **Step 5: Commit the slice**

Run:

```bash
git add tests/test_workflow_lisp_macros.py \
  tests/fixtures/workflow_lisp/invalid/macro_hidden_command_effect.orc \
  tests/fixtures/workflow_lisp/modules/invalid/import_macro_hidden_command/neurips/entry.orc \
  tests/fixtures/workflow_lisp/modules/invalid/import_macro_hidden_command/neurips/macros.orc
git commit -m "test: add macro hidden command effect fixtures"
```

### Task 2: Add Macro ProcRef Runtime-Transport Rejection Coverage

**Files:**

- Create: `tests/fixtures/workflow_lisp/invalid/macro_proc_ref_runtime_transport.orc`
- Modify: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Add a failing workflow-boundary regression that arrives through a macro**

Add a focused test near the existing `proc_ref_runtime_transport_forbidden` coverage:

```python
def test_workflow_boundary_rejects_macro_emitted_proc_ref_transport(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "invalid" / "macro_proc_ref_runtime_transport.orc",
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    _assert_diagnostic_code(excinfo, "proc_ref_runtime_transport_forbidden")
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-proc-ref-workflow"
```

- [ ] **Step 2: Author the invalid fixture so the rejection stays owned by the existing transport validator**

Implementation requirements:

- the macro should emit a runtime-facing workflow surface that transports `ProcRef[...]`;
- prefer a workflow input/output or record-field surface over inventing a fake runtime-closure construct;
- do not add a macro-only transport code or a new validator branch.

Suggested fixture shape:

```lisp
(emit-proc-ref-workflow helper)
(defmacro emit-proc-ref-workflow (name)
  (defworkflow name
    ((runner ProcRef[WorkflowInput -> WorkflowOutput]))
    -> WorkflowOutput
    (record WorkflowOutput :value "bad")))
```

- [ ] **Step 3: Run collection and the focused transport selector**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_workflows.py -k "macro_emitted_proc_ref or proc_ref_runtime_transport" -q
pytest tests/test_workflow_lisp_workflows.py -k "macro_emitted_proc_ref or proc_ref_runtime_transport" -v
```

Expected: first failure proves the new macro fixture path is uncovered today; final pass proves macros cannot smuggle compile-time callables into runtime boundaries.

- [ ] **Step 4: Keep the fix on existing transport code paths only**

If the new fixture exposes a gap, fix it only in existing `ProcRef` runtime-transport ownership layers. Do not add macro-special transport logic.

- [ ] **Step 5: Commit the slice**

Run:

```bash
git add tests/test_workflow_lisp_workflows.py \
  tests/fixtures/workflow_lisp/invalid/macro_proc_ref_runtime_transport.orc
git commit -m "test: cover macro proc-ref transport rejection"
```

### Task 3: Add Macro-Origin Executable / Source-Map Lineage Rejection Coverage

**Files:**

- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify if needed: `orchestrator/workflow_lisp/source_map.py`
- Modify if needed: `orchestrator/workflow_lisp/compiler.py`

- [ ] **Step 1: Extend the source-map test helper so executable-node coverage can opt into shared validation, then add the failing macro-origin mutation test**

First, make `_compile(...)` and `_build_source_map_document(...)` accept a
`validate_shared: bool = False` parameter while keeping existing callers on the
current default. Then add the executable-lineage mutation test against
`VALID_ALIAS_FIXTURE` with `selected_name="command_checks"` and
`validate_shared=True`, because that macro-expanded workflow produces one
runtime executable node only after the validated bundle is available:

```python
def test_source_map_validator_rejects_macro_origin_executable_node_without_origin(
    tmp_path: Path,
) -> None:
    source_map_module, document, workflow_name = _build_source_map_document(
        FIXTURES / "valid" / "macro_workflow_alias.orc",
        tmp_path=tmp_path,
        selected_name="command_checks",
        validate_shared=True,
    )
    workflow = document.workflows[workflow_name]
    assert workflow.executable_nodes
    broken_node = replace(workflow.executable_nodes[0], origin_key="missing-origin")
    broken_document = replace(
        document,
        workflows={
            **dict(document.workflows),
            workflow_name: replace(
                workflow,
                executable_nodes=(broken_node,) + workflow.executable_nodes[1:],
            ),
        },
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        source_map_module.validate_source_map_document(broken_document)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "source_map_executable_node_unmapped"
    assert diagnostic.span.start.path.endswith("tests/fixtures/workflow_lisp/valid/macro_workflow_alias.orc")
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "defworkflow-alias"
```

- [ ] **Step 2: Run collection and the narrow source-map selector**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_source_map.py -k "macro_origin or executable_node" -q
pytest tests/test_workflow_lisp_source_map.py -k "macro_origin or executable_node" -v
```

Expected: the new selector fails first because executable-node coverage is not
available through the existing helper and/or because source-map diagnostics do
not yet preserve the macro workflow-origin expansion frames. Final pass proves
the macro-expanded executable lineage can be tampered with only by triggering
deterministic validator rejection.

- [ ] **Step 3: Stabilize only the existing source-map / executable remap path if required**

Allowed fixes:

- thread `entry.expansion_stack` and any existing authored notes through
  `source_map.py::_diagnostic_for_entry(...)` if the validator currently drops
  macro workflow-origin provenance on `source_map_executable_node_unmapped`;
- preserve `source_map_executable_node_unmapped` when the source-map validator owns the failure;
- preserve `source_map_missing` only for true remap failures where no origin can be recovered;
- keep the authored macro workflow origin and expansion frames as the provenance source.

Do not add a macro-specific source-map validator or new persisted schema fields.

- [ ] **Step 4: Commit the slice**

Run:

```bash
git add tests/test_workflow_lisp_source_map.py \
  orchestrator/workflow_lisp/source_map.py \
  orchestrator/workflow_lisp/compiler.py
git commit -m "test: cover macro source-map lineage rejection"
```

If neither frontend file changes, omit it from `git add`.

### Task 4: Add Nested Expansion Diagnostic Fixtures And Rendering Assertions

**Files:**

- Create: `tests/fixtures/workflow_lisp/invalid/macro_nested_hidden_command_effect.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/macro_nested_name_unknown.orc`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify if needed: `orchestrator/workflow_lisp/diagnostics.py`
- Modify only if the body-passthrough fixture shape still loses one frame: `orchestrator/workflow_lisp/macros.py`

- [ ] **Step 1: Add failing nested-expansion rendering tests for one effect failure and one downstream failure**

Add focused tests that assert the full two-frame `expansion_stack`,
exactly-once call-site / definition-site note pairs, and deterministic pair
ordering for each frame. The expected order must match the current renderer's
frame iteration order: outer macro first, then inner macro.

```python
def test_compile_stage3_renders_nested_macro_notes_for_hidden_command_effect(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "invalid" / "macro_nested_hidden_command_effect.orc",
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    rendered = render_diagnostic(excinfo.value.diagnostics[0])
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_hidden_effect"
    assert [frame.macro_name for frame in diagnostic.expansion_stack] == [
        "emit-command-wrapper",
        "emit-command-workflow",
    ]
    outer_call = "expanded from macro `emit-command-wrapper` call at"
    inner_call = "expanded from macro `emit-command-workflow` call at"
    definition_note = "macro definition at"
    assert rendered.count(outer_call) == 1
    assert rendered.count(inner_call) == 1
    assert rendered.count(definition_note) == 2
    outer_call_index = rendered.index(outer_call)
    outer_def_index = rendered.index(definition_note, outer_call_index)
    inner_call_index = rendered.index(inner_call, outer_def_index)
    inner_def_index = rendered.index(definition_note, inner_call_index)
    assert outer_call_index < outer_def_index < inner_call_index < inner_def_index


def test_compile_stage3_renders_nested_macro_notes_for_downstream_name_unknown(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "invalid" / "macro_nested_name_unknown.orc",
            validate_shared=False,
            workspace_root=tmp_path,
        )

    rendered = render_diagnostic(excinfo.value.diagnostics[0])
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "name_unknown"
    assert [frame.macro_name for frame in diagnostic.expansion_stack] == [
        "emit-record-wrapper",
        "emit-record-workflow",
    ]
    outer_call = "expanded from macro `emit-record-wrapper` call at"
    inner_call = "expanded from macro `emit-record-workflow` call at"
    definition_note = "macro definition at"
    assert rendered.count(outer_call) == 1
    assert rendered.count(inner_call) == 1
    assert rendered.count(definition_note) == 2
    outer_call_index = rendered.index(outer_call)
    outer_def_index = rendered.index(definition_note, outer_call_index)
    inner_call_index = rendered.index(inner_call, outer_def_index)
    inner_def_index = rendered.index(definition_note, inner_call_index)
    assert outer_call_index < outer_def_index < inner_call_index < inner_def_index
```

- [ ] **Step 2: Author the nested fixtures with the known two-frame body-passthrough pattern**

Implementation requirements:

- one fixture should produce a hidden `command-result` by having an outer
  wrapper macro pass the failing body form as an argument into an inner macro
  that emits the `defworkflow`;
- the second fixture should produce a downstream `name_unknown` through the
  same outer-wrapper/body-passthrough/inner-defworkflow pattern;
- do not use the naive "outer wrapper emits only an inner macro call with no
  carried body form" shape, because current expansion semantics collapse that
  case to the inner frame on the failing node;
- keep the fixtures same-file unless the focused test proves imported nesting is required for stability.

Suggested hidden-command fixture shape:

```lisp
(emit-command-wrapper broken)
(defmacro emit-command-wrapper (name)
  (emit-command-workflow name
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns ChecksResult)))
(defmacro emit-command-workflow (name body)
  (defworkflow name
    ((report_path WorkReport))
    -> ChecksResult
    body))
```

Suggested downstream-name fixture shape:

```lisp
(emit-record-wrapper broken)
(defmacro emit-record-wrapper (name)
  (emit-record-workflow name
    (record Out :value missing_name)))
(defmacro emit-record-workflow (name body)
  (defworkflow name
    ()
    -> Out
    body))
```

- [ ] **Step 3: Run collection and the narrow diagnostics selector**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_diagnostics.py -k "nested_macro or macro_expansion_notes" -q
pytest tests/test_workflow_lisp_diagnostics.py -k "nested_macro or macro_expansion_notes" -v
```

Expected: failures should initially show the missing nested fixtures or unstable note ordering; final pass should lock the current `ExpansionFrame` rendering order into regression coverage.

- [ ] **Step 4: Stabilize note rendering only if the tests prove instability**

Allowed changes:

- deterministic ordering of the existing two-frame expansion-stack notes;
- preserving call-site and definition-site note pairs exactly once per frame;
- keeping the actionable authored span on the emitted form or call site.

If the body-passthrough fixtures still lose one of the two expected frames,
stabilize provenance at the macro expansion ownership layer in
`orchestrator/workflow_lisp/macros.py` before changing rendering in
`diagnostics.py`.

Do not invent a new diagnostic format or collapse nested stacks into one synthesized note.

- [ ] **Step 5: Commit the slice**

Run:

```bash
git add tests/test_workflow_lisp_diagnostics.py \
  tests/fixtures/workflow_lisp/invalid/macro_nested_hidden_command_effect.orc \
  tests/fixtures/workflow_lisp/invalid/macro_nested_name_unknown.orc \
  orchestrator/workflow_lisp/macros.py \
  orchestrator/workflow_lisp/diagnostics.py
git commit -m "test: add nested macro diagnostic fixtures"
```

If `macros.py` or `diagnostics.py` is unchanged, omit it from `git add`.

## Final Verification

- [ ] Run collection for every touched test module:

```bash
pytest --collect-only tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_workflows.py -q
```

- [ ] Run the targeted acceptance selectors:

```bash
pytest tests/test_workflow_lisp_macros.py -k "hidden_command or imported_macros_that_introduce_hidden_command_effects" -v
pytest tests/test_workflow_lisp_workflows.py -k "macro_emitted_proc_ref or proc_ref_runtime_transport" -v
pytest tests/test_workflow_lisp_source_map.py -k "macro_origin or executable_node" -v
pytest tests/test_workflow_lisp_diagnostics.py -k "nested_macro or macro_expansion_notes" -v
pytest tests/test_workflow_lisp_structured_results.py -k "macro_emitted_command_result" -v
```

- [ ] Run the full touched-module regression sweep:

```bash
pytest tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_structured_results.py -q
```

- [ ] Run one public CLI compile smoke to prove the existing valid macro surface still compiles through the real orchestrator entrypoint:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/macro_workflow_alias.orc \
  --entry-workflow command_checks \
  --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json \
  --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json \
  --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json \
  --emit-debug-yaml .orchestrate/tmp/macro-acceptance-gate-fixtures/expanded.debug.yaml \
  --emit-core-ast .orchestrate/tmp/macro-acceptance-gate-fixtures/core_workflow_ast.json \
  --emit-semantic-ir .orchestrate/tmp/macro-acceptance-gate-fixtures/semantic_ir.json \
  --emit-source-map .orchestrate/tmp/macro-acceptance-gate-fixtures/source_map.json
```

Expected: compile succeeds, emits the requested artifacts, and the new negative acceptance fixtures do not break the existing valid macro alias workflow.

## Completion Criteria

- The repo has a durable fixture taxonomy for the four accepted macro-safety proof areas: hidden command effects, compile-time callable transport rejection, macro-origin source-map rejection, and nested expansion diagnostics.
- All new failures reuse existing validator ownership and diagnostic codes; no macro-only transport or source-map subsystem is introduced.
- Positive macro coverage remains green, including the existing command-boundary contract behavior for authored code.
- The implementation summary records exactly which fixtures/tests were added, whether any narrow provenance-stability fixes were required in frontend modules, and the verification commands above with their outcomes.
