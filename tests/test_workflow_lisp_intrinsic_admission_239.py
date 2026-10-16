from __future__ import annotations

import re
from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    FinalizeSelectedItemExpr,
    GeneratedRelpathSeedExpr,
    WithPhaseExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import (
    ExpansionFrame,
    SyntaxNode,
    build_syntax_module,
    syntax_node_datum,
)
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding


PHASE_SCOPE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "phase_scope_stdlib_targets.orc"
)
DRAIN_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "drain_stdlib_backlog_drain_parent_terminal_reprojection.orc"
)


def _expression_node(expression: str, target: str) -> tuple[SyntaxNode, frozenset[str]]:
    source = f'''(workflow-lisp
      (:language "0.1")
      (:target-dsl "{target}")
      (defmodule expression_test)
      (export run)
      (defworkflow run () -> String {expression}))'''
    module = build_syntax_module(
        read_sexpr_text(source, source_path="expression_test.orc")
    )
    workflow = syntax_node_datum(module.forms[-1])
    body = workflow.items[-1]
    return (
        SyntaxNode(
            datum=body,
            span=body.span,
            module_path=module.module_path,
            form_path=("workflow-lisp", "defworkflow", "run"),
        ),
        frozenset({"ctx", "selected", "transition", "roadmap", "plan", "implementation"}),
    )


def _elaborate(expression: str, target: str):
    node, bound_names = _expression_node(expression, target)
    return elaborate_expression(
        node,
        bound_names=bound_names,
        target_dsl_version=target,
    )


def _write_module(root: Path, module: str, source: str) -> Path:
    path = root.joinpath(*module.split("/")).with_suffix(".orc")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _compile(
    path: Path,
    root: Path,
    *,
    command_boundaries: dict[str, CertifiedAdapterBinding] | None = None,
):
    return compile_stage3_entrypoint(
        path,
        source_roots=(root,),
        command_boundaries=command_boundaries or {},
        workspace_root=root,
        validate_shared=False,
    )


def _diagnostics_for_private_rejection(path: Path, root: Path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(path, root)
    diagnostics = caught.value.diagnostics
    codes = {diagnostic.code for diagnostic in diagnostics}
    assert "private_form_not_admitted" in codes, tuple(
        (diagnostic.code, diagnostic.message) for diagnostic in diagnostics
    )
    return next(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.code == "private_form_not_admitted"
    )


@pytest.mark.parametrize(
    "expression",
    (
        "(__with-phase__ ctx implementation \"body\")",
        '(__generated-relpath-seed__ MissingType "artifacts/out.md" "seed")',
    ),
)
def test_target_239_refuses_direct_private_expansion_heads(expression: str) -> None:
    with pytest.raises(LispFrontendCompileError) as caught:
        _elaborate(expression, "2.39")

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "private_form_not_admitted"
    assert diagnostic.span.start.path == "expression_test.orc"


@pytest.mark.parametrize(
    ("expression", "expected_type"),
    (
        ('(with-phase ctx implementation "body")', WithPhaseExpr),
        (
            '(__with-phase__ ctx implementation "body")',
            WithPhaseExpr,
        ),
        (
            '(__generated-relpath-seed__ MissingType "artifacts/out.md" "seed")',
            GeneratedRelpathSeedExpr,
        ),
        (
            "(finalize-selected-item :ctx ctx :selected selected "
            ":queue-transition transition :roadmap roadmap :plan plan "
            ":implementation implementation)",
            FinalizeSelectedItemExpr,
        ),
    ),
)
@pytest.mark.parametrize("target", ("2.35", "2.36", "2.37", "2.38"))
def test_targets_235_through_238_keep_existing_intrinsic_routes(
    expression: str,
    expected_type: type,
    target: str,
) -> None:
    assert isinstance(_elaborate(expression, target), expected_type)


@pytest.mark.parametrize("target", ("2.38", "2.39"))
def test_completion_hides_private_and_fallback_heads_only_for_target_239(
    tmp_path: Path,
    target: str,
) -> None:
    from orchestrator.lsp.navigation import (
        build_navigation_index,
        project_form_completion_rows,
    )
    from orchestrator.workflow_lisp.form_registry import registered_form_heads

    source = PHASE_SCOPE_FIXTURE.read_text(encoding="utf-8").replace(
        '(:target-dsl "2.35")', f'(:target-dsl "{target}")'
    )
    path = _write_module(tmp_path, "phase_scope_stdlib_targets", source)
    result = _compile(path, tmp_path)
    index = build_navigation_index(
        result,
        frozen_form_completions=project_form_completion_rows(
            tuple(registered_form_heads(target_dsl_version=None))
        ),
    )
    module_path = result.graph.modules_by_name["phase_scope_stdlib_targets"].path.resolve()
    completions = dict(index.completions_by_path)[module_path]
    hidden = {
        "__with-phase__",
        "__generated-relpath-seed__",
        "with-phase",
        "finalize-selected-item",
    }

    if target == "2.39":
        assert hidden.isdisjoint({completion.label for completion in completions})
    else:
        assert hidden <= {completion.label for completion in completions}


@pytest.mark.parametrize(
    "expression",
    (
        '(with-phase ctx implementation "body")',
        "(finalize-selected-item :ctx ctx :selected selected "
        ":queue-transition transition :roadmap roadmap :plan plan "
        ":implementation implementation)",
    ),
)
def test_target_239_refuses_bare_compatibility_heads(expression: str) -> None:
    with pytest.raises(LispFrontendCompileError) as caught:
        _elaborate(expression, "2.39")

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "stdlib_import_route_required"
    assert diagnostic.span.start.path == "expression_test.orc"


def test_target_239_accepts_packaged_phase_template_nested_under_user_macro(
    tmp_path: Path,
) -> None:
    source = PHASE_SCOPE_FIXTURE.read_text(encoding="utf-8").replace(
        '(:target-dsl "2.35")', '(:target-dsl "2.39")'
    )
    source = source.replace(
        "  (export PhaseScopeSurface phase-scope-demo)",
        "  (export PhaseScopeSurface phase-scope-demo)\n"
        "  (defmacro wrapped-phase-scope (name ctx-key ctx phase-key phase-name)\n"
        "    (phase-scope name ctx-key ctx phase-key phase-name))",
    )
    source = source.replace(
        "(phase-scope implementation-scope :ctx phase-ctx :phase implementation)",
        "(wrapped-phase-scope implementation-scope :ctx phase-ctx :phase implementation)",
    )
    path = _write_module(tmp_path, "phase_scope_stdlib_targets", source)

    result = _compile(path, tmp_path)

    assert result.compiled_results_by_name["phase_scope_stdlib_targets"].typed_workflows


@pytest.mark.parametrize("nested", (False, True), ids=("imported", "user-wrapped"))
def test_target_239_with_phase_build_readback_and_phase_target_runtime(
    tmp_path: Path,
    nested: bool,
) -> None:
    from tests.test_workflow_lisp_closed_phase_target import _context, _source
    from tests.workflow_lisp_closed_program_helpers import build

    source = _source().replace("TARGET", "2.39")
    if nested:
        source = source.replace(
            "(export run)",
            "(export run)\n"
            "  (defmacro wrap (ctx phase body) (with-phase ctx phase body))",
        ).replace(
            "(with-phase request.ctx implementation",
            "(wrap request.ctx implementation",
        )

    program = build(
        tmp_path,
        source,
        boundaries={},
        providers={},
        prompts={},
    )
    restored = ClosedProgram.from_artifact(program.artifact())
    assert restored.digest == program.digest

    result = evaluate_closed_program(
        restored,
        {"request": {"ctx": _context()}},
    )

    assert result.json_value() == "artifacts/work/implementation/execution-report.md"


@pytest.mark.parametrize(
    ("macro_name", "params", "macro_body", "call"),
    (
        (
            "with-phase",
            "ctx phase body",
            "(__with-phase__ ctx implementation body)",
            '(with-phase "ctx" implementation "body")',
        ),
        (
            "invent-seed",
            "",
            '(__generated-relpath-seed__ MissingType "artifacts/out.md" "seed")',
            "(invent-seed)",
        ),
    ),
)
def test_target_239_refuses_user_macro_private_head_synthesis_with_origin_span(
    tmp_path: Path,
    macro_name: str,
    params: str,
    macro_body: str,
    call: str,
) -> None:
    source = f'''(workflow-lisp
      (:language "0.1")
      (:target-dsl "2.39")
      (defmodule user_macro)
      (export run)
      (defmacro {macro_name} ({params}) {macro_body})
      (defworkflow run () -> String {call}))'''
    path = _write_module(tmp_path, "user_macro", source)

    diagnostic = _diagnostics_for_private_rejection(path, tmp_path)

    assert Path(diagnostic.span.start.path) == path
    assert diagnostic.expansion_stack
    assert isinstance(diagnostic.expansion_stack[-1], ExpansionFrame)
    assert diagnostic.expansion_stack[-1].definition_span.start.path == str(path)


def test_target_239_refuses_caller_spliced_private_head_inside_real_stdlib_macro(
    tmp_path: Path,
) -> None:
    source = '''(workflow-lisp
      (:language "0.1")
      (:target-dsl "2.39")
      (defmodule caller_splice)
      (import std/phase :only (with-phase))
      (export run)
      (defmacro wrap-phase (ctx phase body) (with-phase ctx phase body))
      (defworkflow run ((ctx String)) -> String
        (wrap-phase ctx implementation (__with-phase__ ctx implementation "body"))))'''
    path = _write_module(tmp_path, "caller_splice", source)

    diagnostic = _diagnostics_for_private_rejection(path, tmp_path)

    assert Path(diagnostic.span.start.path) == path
    assert any(
        isinstance(frame, ExpansionFrame)
        and Path(frame.definition_span.start.path)
        == (Path(__file__).resolve().parents[1]
            / "orchestrator/workflow_lisp/stdlib_modules/std/phase.orc")
        for frame in diagnostic.expansion_stack
    )


def test_target_239_rejects_fake_std_phase_private_form_origin(tmp_path: Path) -> None:
    source = '''(workflow-lisp
      (:language "0.1")
      (:target-dsl "2.39")
      (defmodule std/phase)
      (export run)
      (defmacro with-phase (ctx phase body) (__with-phase__ ctx phase body))
      (defworkflow run () -> String (with-phase "ctx" implementation "body")))'''
    path = _write_module(tmp_path, "std/phase", source)

    diagnostic = _diagnostics_for_private_rejection(path, tmp_path)

    assert Path(diagnostic.span.start.path) == path
    assert diagnostic.expansion_stack[-1].definition_span.start.path == str(path)


def test_target_239_preserves_packaged_drain_seed_expansion(
    tmp_path: Path,
) -> None:
    from tests.test_workflow_lisp_drain_stdlib import _command_boundaries

    source = DRAIN_FIXTURE.read_text(encoding="utf-8").replace(
        '(:target-dsl "2.35")', '(:target-dsl "2.39")'
    )
    source = re.sub(r"\s*:lowering inline", "", source)
    module = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module is not None
    path = _write_module(tmp_path, module.group(1), source)

    result = _compile(
        path,
        tmp_path,
        command_boundaries=_command_boundaries(
            gap_output_type_name="GapResult"
        ).bindings_by_name,
    )

    assert result.compiled_results_by_name[module.group(1)].typed_workflows


def test_target_239_refuses_fake_std_module_shadowing_packaged_phase(
    tmp_path: Path,
) -> None:
    fake_phase = '''(workflow-lisp
      (:language "0.1")
      (:target-dsl "2.39")
      (defmodule std/phase)
      (export with-phase)
      (defmacro with-phase (ctx phase body) (__with-phase__ ctx phase body)))'''
    _write_module(tmp_path, "std/phase", fake_phase)
    entry = _write_module(
        tmp_path,
        "entry",
        '''(workflow-lisp
          (:language "0.1")
          (:target-dsl "2.39")
          (defmodule entry)
          (import std/phase :only (with-phase))
          (export run)
          (defworkflow run () -> String (with-phase "ctx" implementation "body")))''',
    )

    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(entry, tmp_path)

    assert caught.value.diagnostics[0].code == "module_import_ambiguous"
