"""Target-2.26 strict Boolean control-flow admission and `cond` reservation."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    compile_stage1_module,
    compile_stage3_entrypoint,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    FunctionCallExpr,
    LiteralExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode


FORM_PATH = ("workflow-lisp", "strict-boolean-control-flow-test")


def _expressions():
    return importlib.import_module("orchestrator.workflow_lisp.expressions")


def _form_registry():
    return importlib.import_module("orchestrator.workflow_lisp.form_registry")


def _cond_expr_type():
    return getattr(_expressions(), "CondExpr", None)


def _expression_syntax(source: str) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="inline_condition.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_condition.orc",
        form_path=FORM_PATH,
    )


def _defmacro_source(target: str) -> str:
    return (
        '(workflow-lisp (:language "0.1") (:target-dsl "%s") '
        "(defmodule m) (defmacro cond (x) x))\n" % target
    )


def test_cond_version_gate_admits_2_26_and_rejects_2_25() -> None:
    """`cond` is a reserved special form only from target 2.26 onward."""

    registry = _form_registry()

    assert registry.get_form_spec("cond", target_dsl_version="2.25") is None
    spec = registry.get_form_spec("cond", target_dsl_version="2.26")
    assert spec is not None
    assert spec.macro_bindable is False
    assert spec.min_target_dsl_version == "2.26"
    assert spec.elaboration_route == "cond"


def test_cond_syntax_elaborates_special_form_at_2_26() -> None:
    """Target 2.26 selects the `cond` special form and keeps the else marker."""

    cond_expr_type = _cond_expr_type()
    assert cond_expr_type is not None

    expr = elaborate_expression(
        _expression_syntax('(cond (true "yes") (else "no"))'),
        bound_names=frozenset(),
        target_dsl_version="2.26",
    )

    assert isinstance(expr, cond_expr_type)
    assert expr.has_else is True
    assert len(expr.clauses) == 2

    first, second = expr.clauses
    assert first.is_else is False
    assert isinstance(first.condition_expr, LiteralExpr)
    assert first.condition_expr.value is True
    assert isinstance(first.result_expr, LiteralExpr)
    assert first.result_expr.value == "yes"
    assert second.is_else is True
    assert second.condition_expr is None
    assert isinstance(second.result_expr, LiteralExpr)
    assert second.result_expr.value == "no"


def test_cond_syntax_retains_source_spans() -> None:
    """The temporary `cond` node keeps authored clause provenance."""

    cond_expr_type = _cond_expr_type()
    source = '(cond (true "yes") (else "no"))'
    parse_tree = read_sexpr_text(source, source_path="inline_condition.orc")
    assert len(parse_tree.items) == 1
    cond_list = parse_tree.items[0]
    node = SyntaxNode(
        datum=cond_list,
        span=cond_list.span,
        module_path="inline_condition.orc",
        form_path=FORM_PATH,
    )

    expr = elaborate_expression(
        node,
        bound_names=frozenset(),
        target_dsl_version="2.26",
    )

    assert isinstance(expr, cond_expr_type)
    assert expr.span == cond_list.span
    assert len(expr.clauses) == 2
    assert expr.clauses[0].span == cond_list.items[1].span
    assert expr.clauses[1].span == cond_list.items[2].span


def test_cond_version_declared_function_resolves_at_2_25() -> None:
    """A declared function named `cond` still resolves normally below 2.26."""

    expr = elaborate_expression(
        _expression_syntax("(cond 1 2)"),
        bound_names=frozenset(),
        function_names=frozenset({"cond"}),
        target_dsl_version="2.25",
    )

    assert isinstance(expr, FunctionCallExpr)


def test_cond_reservation_blocks_defmacro_at_2_26_only(tmp_path: Path) -> None:
    """`defmacro cond` is reserved at 2.26 but remains bindable below it."""

    source = tmp_path / "cond_macro.orc"
    source.write_text(_defmacro_source("2.26"), encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(source)
    assert excinfo.value.diagnostics[0].code == "macro_reserved_name"

    source.write_text(_defmacro_source("2.25"), encoding="utf-8")
    compile_stage1_module(source)


def test_cond_reservation_rejects_imported_2_25_macro_at_2_26(tmp_path: Path) -> None:
    """A 2.25-exported `cond` macro is reserved for a 2.26 importer, usable at 2.25."""

    (tmp_path / "condlib.orc").write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.25") '
        "(defmodule condlib) (export cond) (defmacro cond (x) x))\n",
        encoding="utf-8",
    )

    importer_226 = tmp_path / "importer226.orc"
    importer_226.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.26") '
        "(defmodule importer226) (import condlib :only (cond)) "
        '(export run) (defworkflow run () -> String "ok"))\n',
        encoding="utf-8",
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            importer_226,
            source_roots=(tmp_path,),
            workspace_root=tmp_path,
        )
    assert excinfo.value.diagnostics[0].code == "macro_reserved_name"

    importer_225 = tmp_path / "importer225.orc"
    importer_225.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.25") '
        "(defmodule importer225) (import condlib :only (cond)) "
        '(export run) (defworkflow run () -> String "ok"))\n',
        encoding="utf-8",
    )
    compile_stage3_entrypoint(
        importer_225,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
    )

@pytest.mark.parametrize(
    ("source", "code"),
    (
        ('(cond (true))', "cond_clause_invalid"),
        ('(cond (true "yes" "extra"))', "cond_clause_invalid"),
        ('(cond "nope")', "cond_clause_invalid"),
        ('(cond (true "yes") (else "no") (else "again"))', "cond_else_invalid"),
        ('(cond (else "no") (true "yes"))', "cond_else_invalid"),
    ),
)
def test_cond_malformed_clauses_diagnose(source: str, code: str) -> None:
    """Malformed `cond` clauses surface stable `cond_*` diagnostics."""

    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax(source),
            bound_names=frozenset(),
            target_dsl_version="2.26",
        )

    assert excinfo.value.diagnostics[0].code == code

def test_cond_non_final_else_with_invalid_nested_result_reports_else_clause() -> None:
    """A non-final `else` is rejected at the else clause even when its result is invalid."""

    source = '(cond (else (bogus-call)) (true "yes"))'
    parse_tree = read_sexpr_text(source, source_path="inline_condition.orc")
    assert len(parse_tree.items) == 1
    cond_list = parse_tree.items[0]
    else_clause = cond_list.items[1]

    node = SyntaxNode(
        datum=cond_list,
        span=cond_list.span,
        module_path="inline_condition.orc",
        form_path=FORM_PATH,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            node,
            bound_names=frozenset(),
            target_dsl_version="2.26",
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "cond_else_invalid"
    assert diagnostic.span == else_clause.span
