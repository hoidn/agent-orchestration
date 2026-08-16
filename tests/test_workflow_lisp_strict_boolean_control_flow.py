"""Target-2.26 strict Boolean control-flow admission and `cond` reservation."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow_lisp.compiler import (
    compile_stage1_module,
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    serialize_diagnostic,
)
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs, walk_expr
from orchestrator.workflow_lisp.expressions import (
    CallExpr,
    CommandResultExpr,
    EnumMemberExpr,
    FunctionCallExpr,
    IfExpr,
    LetStarExpr,
    ListMapEffectExpr,
    ListMapExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    ProviderResultExpr,
    PureOpExpr,
    UnionVariantTagExpr,
    WithLiveProviderPeersExpr,
    WithLiveProvidersExpr,
    WithPhaseExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


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

def _typed_body(
    source: str,
    tmp_path: Path,
    *,
    command_names=(),
    provider_externs=None,
    prompt_externs=None,
):
    path = tmp_path / "strict_bool.orc"
    path.write_text(source, encoding="utf-8")
    boundaries = {
        name: ExternalToolBinding(
            name=name,
            stable_command=("python", f"scripts/{name}.py"),
        )
        for name in command_names
    }
    result = compile_stage3_module(
        path,
        command_boundaries=boundaries,
        provider_externs=provider_externs or {},
        prompt_externs=prompt_externs or {},
        validate_shared=False,
        workspace_root=tmp_path,
    )
    return result.typed_workflows[-1].typed_body.expr


def _cond_pure_ops(expr) -> list[PureOpExpr]:
    return [
        node
        for node in walk_expr(expr)
        if isinstance(node, PureOpExpr) and node.operator in {"and", "or"}
    ]


def _command_nodes(expr) -> int:
    return sum(
        1 for node in walk_expr(expr) if isinstance(node, CommandResultExpr)
    )


def test_strict_linear_extraction_normalizes(tmp_path: Path) -> None:
    """An inline enum comparison hoists its effect into one compiler binding."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule linear)",
                "  (export decide)",
                "  (defenum ReviewDecision",
                "    APPROVE",
                "    REVISE)",
                "  (defworkflow decide",
                "    ()",
                "    -> Bool",
                "    (if (= (command-result probe",
                '             :argv ("python" "scripts/probe.py")',
                "             :returns ReviewDecision)",
                "           ReviewDecision.APPROVE)",
                "        (command-result accept",
                '          :argv ("python" "scripts/accept.py")',
                "          :returns Bool)",
                "        (command-result revise",
                '          :argv ("python" "scripts/revise.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("probe", "accept", "revise"),
    )

    assert isinstance(body, LetStarExpr)
    assert len(body.bindings) == 1
    binding_name, binding_expr = body.bindings[0]
    assert binding_name.startswith("__cond_effect_")
    assert isinstance(binding_expr, CommandResultExpr)
    assert isinstance(body.body, IfExpr)
    assert isinstance(body.body.condition_expr, PureOpExpr)
    assert body.body.condition_expr.operator == "="
    assert _cond_pure_ops(body) == []


def test_short_circuit_and_normalizes_to_nested_if(tmp_path: Path) -> None:
    """`and` folds into nested `if` with no residual pure `and` operator."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule sc_and)",
                "  (defworkflow gate",
                "    ()",
                "    -> Bool",
                "    (if (and (command-result probe",
                '              :argv ("python" "scripts/probe.py")',
                "              :returns Bool)",
                "             (command-result later",
                '              :argv ("python" "scripts/later.py")',
                "              :returns Bool))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("probe", "later", "yes", "no"),
    )

    assert isinstance(body, LetStarExpr)
    assert _cond_pure_ops(body) == []
    # The nested short-circuit boundary is a structured IfExpr whose then
    # branch carries the later operand; the terminal condition is a ref.
    outer = body.body
    assert isinstance(outer, IfExpr)
    assert isinstance(outer.condition_expr, NameExpr)


def test_short_circuit_or_normalizes_to_nested_if(tmp_path: Path) -> None:
    """`or` folds into nested `if` with no residual pure `or` operator."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule sc_or)",
                "  (defworkflow gate",
                "    ()",
                "    -> Bool",
                "    (if (or (command-result probe",
                '             :argv ("python" "scripts/probe.py")',
                "             :returns Bool)",
                "            (command-result later",
                '             :argv ("python" "scripts/later.py")',
                "             :returns Bool))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("probe", "later", "yes", "no"),
    )

    assert isinstance(body, LetStarExpr)
    assert _cond_pure_ops(body) == []
    outer = body.body
    assert isinstance(outer, IfExpr)
    assert isinstance(outer.condition_expr, NameExpr)


def test_nested_control_value_binds_once(tmp_path: Path) -> None:
    """A nested effectful `if` value is bound once before the outer route."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule nested)",
                "  (defworkflow route",
                "    ()",
                "    -> Bool",
                "    (if (= (if (command-result choose",
                '                :argv ("python" "scripts/choose.py")',
                "                :returns Bool)",
                "             (command-result left",
                '               :argv ("python" "scripts/left.py")',
                "               :returns Int)",
                "             (command-result right",
                '               :argv ("python" "scripts/right.py")',
                "               :returns Int))",
                "           1)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("choose", "left", "right", "yes", "no"),
    )

    assert isinstance(body, LetStarExpr)
    assert _cond_pure_ops(body) == []
    # The condition effect is bound exactly once as a command; the nested
    # control value is bound once (remaining bindings are pure aliases).
    assert len([n for n in walk_expr(body) if isinstance(n, CommandResultExpr) and n.step_name == "choose"]) == 1
    assert _cond_pure_ops(body) == []
    outer = body.body
    assert isinstance(outer, IfExpr)
    assert isinstance(outer.condition_expr, PureOpExpr)
    assert outer.condition_expr.operator == "="


@pytest.mark.parametrize(
    ("condition", "prelude"),
    [
        ("1", ""),
        ('"x"', ""),
        ("ReviewDecision.APPROVE", "(defenum ReviewDecision APPROVE REVISE)"),
        ("(record Summary :approved true)", "(defrecord Summary (approved Bool))"),
    ],
)
def test_strict_non_bool_conditions_rejected(
    tmp_path: Path,
    condition: str,
    prelude: str,
) -> None:
    """Non-``Bool`` conditions fail with ``if_condition_not_bool`` at 2.26."""

    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.26")',
            "  (defmodule reject)",
            "  (export reject)",
            f"  {prelude}" if prelude else "  (defrecord Ignored (approved Bool))",
            "  (defworkflow reject",
            "    ()",
            "    -> Bool",
            f"    (if {condition}",
            "        true",
            "        false)))",
        ]
    )
    path = tmp_path / "reject.orc"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            command_boundaries={},
            provider_externs={},
            prompt_externs={},
            lowering_route="legacy",
            validate_shared=False,
            workspace_root=tmp_path,
        )
    assert excinfo.value.diagnostics[0].code == "if_condition_not_bool"


def test_strict_direct_workflow_bool_admitted(tmp_path: Path) -> None:
    """A same-file workflow call returning ``Bool`` is an admitted condition."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule direct_call)",
                "  (export outer)",
                "  (defworkflow inner",
                "    ()",
                "    -> Bool",
                "    (command-result probe",
                '      :argv ("python" "scripts/probe.py")',
                "      :returns Bool))",
                "  (defworkflow outer",
                "    ()",
                "    -> Bool",
                "    (if (call inner)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("probe", "yes", "no"),
    )

    assert isinstance(body, LetStarExpr)
    assert _cond_pure_ops(body) == []


def test_short_circuit_helper_argument_effectful_and_normalized(tmp_path: Path) -> None:
    """An effectful `and` inside a helper argument is normalized, not eager."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule helper_arg)",
                "  (export outer)",
                "  (defun identity-bool",
                "    ((value Bool))",
                "    -> Bool",
                "    value)",
                "  (defworkflow outer",
                "    ()",
                "    -> Bool",
                "    (if (identity-bool",
                "          (and false",
                "               (command-result must_not_run",
                '                 :argv ("python" "scripts/must_not_run.py")',
                "                 :returns Bool)))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("must_not_run", "yes", "no"),
    )

    assert _cond_pure_ops(body) == []


def test_short_circuit_match_arm_effectful_and_normalized(tmp_path: Path) -> None:
    """An effectful `and` inside a `match` arm body is normalized, not eager."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule match_arm)",
                "  (export outer)",
                "  (defunion Subject",
                "    (A (flag Bool))",
                "    (B (flag Bool)))",
                "  (defworkflow outer",
                "    ()",
                "    -> Bool",
                "    (if (match (command-result subject",
                '                 :argv ("python" "scripts/subject.py")',
                "                 :returns Subject)",
                "          ((A a)",
                "           (and false",
                "                (command-result must_not_run",
                '                  :argv ("python" "scripts/must_not_run.py")',
                "                  :returns Bool)))",
                "          ((B b) false))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("subject", "must_not_run", "yes", "no"),
    )

    assert _cond_pure_ops(body) == []


def test_strict_macro_cloned_effect_distinct_bindings(tmp_path: Path) -> None:
    """Macro-cloned equal-provenance effects get distinct operand-path names."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule macro_clone)",
                "  (export outer)",
                "  (defmacro twice (x)",
                "    (and x x))",
                "  (defworkflow outer",
                "    ()",
                "    -> Bool",
                "    (if (twice (command-result probe",
                '                 :argv ("python" "scripts/probe.py")',
                "                 :returns Bool))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("probe", "yes", "no"),
    )

    assert isinstance(body, LetStarExpr)
    assert _cond_pure_ops(body) == []
    effect_bindings = [
        name
        for node in walk_expr(body)
        if isinstance(node, LetStarExpr)
        for name, _ in node.bindings
        if name.startswith("__cond_effect_")
    ]
    assert len(effect_bindings) == 2
    assert len(set(effect_bindings)) == 2


def test_strict_no_effectful_and_or_reaches_pure_op(tmp_path: Path) -> None:
    """The normalized union carries no residual ``and``/``or`` pure operator."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule invariant)",
                "  (export outer)",
                "  (defun identity-bool",
                "    ((value Bool))",
                "    -> Bool",
                "    value)",
                "  (defunion Subject",
                "    (A (flag Bool))",
                "    (B (flag Bool)))",
                "  (defworkflow outer",
                "    ()",
                "    -> Bool",
                "    (if (and (= (command-result probe",
                '                  :argv ("python" "scripts/probe.py")',
                "                  :returns Bool)",
                "                true)",
                "             (or (identity-bool",
                "                   (and false",
                "                        (command-result must_not_run",
                '                          :argv ("python" "scripts/must_not_run.py")',
                "                          :returns Bool)))",
                "                 (match (command-result subject",
                '                          :argv ("python" "scripts/subject.py")',
                "                          :returns Subject)",
                "                   ((A a) false)",
                "                   ((B b) true))))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("probe", "must_not_run", "subject", "yes", "no"),
    )

    assert isinstance(body, LetStarExpr)
    assert _cond_pure_ops(body) == []


def test_strict_helper_body_and_or_normalized(tmp_path: Path) -> None:
    """A pure `and`/`or` authored in a helper body is normalized after expansion."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule helper_body)",
                "  (export outer)",
                "  (defun both",
                "    ((a Bool) (b Bool))",
                "    -> Bool",
                "    (and a b))",
                "  (defworkflow outer",
                "    ()",
                "    -> Bool",
                "    (if (both true false)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("yes", "no"),
    )

    assert _cond_pure_ops(body) == []


def test_strict_direct_procedure_bool_admitted(tmp_path: Path) -> None:
    """A same-file procedure returning ``Bool`` is admitted as a condition."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule direct_proc)",
                "  (export outer)",
                "  (defproc ready-proc",
                "    ()",
                "    -> Bool",
                "    :effects ((uses-command probe))",
                "    (command-result probe",
                '      :argv ("python" "scripts/probe.py")',
                "      :returns Bool))",
                "  (defworkflow outer",
                "    ()",
                "    -> Bool",
                "    (if (ready-proc)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("probe", "yes", "no"),
    )

    assert _cond_pure_ops(body) == []


def test_strict_nested_helper_call_in_procedure_arg_expands(tmp_path: Path) -> None:
    """A pure `defun` call nested in a procedure argument expands before lowering."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule nested_helper)",
                "  (export outer)",
                "  (defun both",
                "    ((a Bool) (b Bool))",
                "    -> Bool",
                "    (and a b))",
                "  (defproc identity-proc",
                "    ((value Bool))",
                "    -> Bool",
                "    :effects ()",
                "    value)",
                "  (defworkflow outer",
                "    ()",
                "    -> Bool",
                "    (if (identity-proc (both true false))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("yes", "no"),
    )

    assert _cond_pure_ops(body) == []
    assert not [
        node
        for node in walk_expr(body)
        if isinstance(node, FunctionCallExpr)
    ]


def test_strict_effectful_not_normalized(tmp_path: Path) -> None:
    """`not` over an effectful operand evaluates the operand once and inverts."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule not_effect)",
                "  (export outer)",
                "  (defworkflow outer",
                "    ()",
                "    -> Bool",
                "    (if (not (command-result probe",
                '               :argv ("python" "scripts/probe.py")',
                "               :returns Bool))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("probe", "yes", "no"),
    )

    assert _cond_pure_ops(body) == []
    assert isinstance(body, LetStarExpr)
    assert any(isinstance(v, CommandResultExpr) for _, v in body.bindings)
    assert isinstance(body.body, IfExpr)
    assert isinstance(body.body.condition_expr, PureOpExpr)
    assert body.body.condition_expr.operator == "not"


@pytest.mark.parametrize(
    ("condition", "prelude"),
    [
        ("(variant Subject A :flag true)", "(defunion Subject (A (flag Bool)) (B (flag Bool)))"),
    ],
)
def test_strict_union_value_rejected(
    tmp_path: Path,
    condition: str,
    prelude: str,
) -> None:
    """Union and Value conditions are rejected with ``if_condition_not_bool``."""

    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.26")',
            "  (defmodule reject)",
            "  (export reject)",
            f"  {prelude}",
            "  (defworkflow reject",
            "    ()",
            "    -> Bool",
            f"    (if {condition}",
            "        true",
            "        false)))",
        ]
    )
    path = tmp_path / "reject.orc"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            command_boundaries={},
            provider_externs={},
            prompt_externs={},
            validate_shared=False,
            workspace_root=tmp_path,
        )
    assert excinfo.value.diagnostics[0].code == "if_condition_not_bool"


def test_strict_value_condition_rejected(tmp_path: Path) -> None:
    """A ``Value``-typed condition is rejected with ``if_condition_not_bool``."""

    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.26")',
            "  (defmodule reject_value)",
            "  (export reject)",
            "  (defworkflow reject ((payload Value)) -> Bool",
            "    (if payload",
            "        true",
            "        false)))",
        ]
    )
    path = tmp_path / "reject_value.orc"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            command_boundaries={},
            provider_externs={},
            prompt_externs={},
            validate_shared=False,
            workspace_root=tmp_path,
        )
    assert excinfo.value.diagnostics[0].code == "if_condition_not_bool"


def test_strict_with_live_provider_peers_member_scope_preserved(tmp_path: Path) -> None:
    """Peer members stay provider performs; the group is bound exactly once."""

    (tmp_path / "prompts").mkdir()
    for name in ("planner", "reviewer"):
        (tmp_path / "prompts" / f"{name}.md").write_text("Prompt.\n", encoding="utf-8")
    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule peers)",
                "  (export gate)",
                "  (defworkflow gate () -> Bool",
                "    (if (with-live-provider-peers",
                "          ((planner",
                "             (provider-result providers.planner",
                "               :prompt prompts.planner :inputs ()",
                "               :timeout-sec 30 :returns String))",
                "           (reviewer",
                "             (provider-result providers.reviewer",
                "               :prompt prompts.reviewer :inputs ()",
                "               :timeout-sec 20 :returns Bool)))",
                "          reviewer)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("yes", "no"),
        provider_externs={
            "providers.planner": "planner-provider",
            "providers.reviewer": "reviewer-provider",
        },
        prompt_externs={
            "prompts.planner": "prompts/planner.md",
            "prompts.reviewer": "prompts/reviewer.md",
        },
    )

    assert _cond_pure_ops(body) == []
    peer_nodes = [
        node for node in walk_expr(body) if isinstance(node, WithLiveProviderPeersExpr)
    ]
    assert len(peer_nodes) == 1
    members = [binding.value_expr for binding in peer_nodes[0].bindings]
    assert all(isinstance(member, ProviderResultExpr) for member in members)
    assert isinstance(peer_nodes[0].body, NameExpr)


def test_strict_with_live_providers_member_scope_preserved(tmp_path: Path) -> None:
    """Supervision members stay provider performs; the group is bound once."""

    (tmp_path / "prompts").mkdir()
    for name in ("worker", "supervisor"):
        (tmp_path / "prompts" / f"{name}.md").write_text("Prompt.\n", encoding="utf-8")
    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule supervision)",
                "  (export gate)",
                "  (defworkflow gate () -> Bool",
                "    (if (with-live-providers",
                "          ((worker",
                "             (provider-result providers.worker",
                "               :prompt prompts.worker :inputs ()",
                "               :timeout-sec 30 :returns Value))",
                "           (supervisor",
                "             (provider-result providers.supervisor",
                "               :prompt prompts.supervisor :inputs ()",
                "               :timeout-sec 20 :returns ProviderSteeringDirective)",
                "             :observes worker))",
                "          true)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("yes", "no"),
        provider_externs={
            "providers.worker": "worker-provider",
            "providers.supervisor": "supervisor-provider",
        },
        prompt_externs={
            "prompts.worker": "prompts/worker.md",
            "prompts.supervisor": "prompts/supervisor.md",
        },
    )

    assert _cond_pure_ops(body) == []
    supervision_nodes = [
        node for node in walk_expr(body) if isinstance(node, WithLiveProvidersExpr)
    ]
    assert len(supervision_nodes) == 1
    members = [binding.value_expr for binding in supervision_nodes[0].bindings]
    assert all(isinstance(member, ProviderResultExpr) for member in members)
    assert isinstance(supervision_nodes[0].body, LiteralExpr)

def test_strict_non_condition_live_member_projection_stays_straight_line(
    tmp_path: Path,
) -> None:
    """An authored non-condition pure ``and``/``or`` live-member projection is
    not post-folded into ``IfExpr`` (exact helper-clone provenance only)."""

    (tmp_path / "prompts").mkdir()
    for name in ("worker", "supervisor"):
        (tmp_path / "prompts" / f"{name}.md").write_text("Prompt.\n", encoding="utf-8")
    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule projection)",
                "  (export orchestrate)",
                "  (defworkflow orchestrate () -> Bool",
                "    (with-live-providers",
                "      ((worker",
                "         (provider-result providers.worker",
                "           :prompt prompts.worker :inputs ()",
                "           :timeout-sec 30 :returns Bool))",
                "       (supervisor",
                "         (provider-result providers.supervisor",
                "           :prompt prompts.supervisor :inputs ()",
                "           :timeout-sec 20 :returns ProviderSteeringDirective)",
                "         :observes worker))",
                "      (and worker true))))",
            ]
        ),
        tmp_path,
        provider_externs={
            "providers.worker": "worker-provider",
            "providers.supervisor": "supervisor-provider",
        },
        prompt_externs={
            "prompts.worker": "prompts/worker.md",
            "prompts.supervisor": "prompts/supervisor.md",
        },
    )

    live = next(
        node for node in walk_expr(body) if isinstance(node, WithLiveProvidersExpr)
    )
    # The settlement projection stays a straight-line pure `and` (no `IfExpr`).
    assert isinstance(live.body, PureOpExpr)
    assert live.body.operator == "and"
    assert not [
        node for node in walk_expr(body) if isinstance(node, IfExpr)
    ]




def test_strict_nested_let_shadowing_preserved(tmp_path: Path) -> None:
    """A nested authored ``let*`` keeps its bindings in the nested scope."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule shadow)",
                "  (export decide)",
                "  (defworkflow decide () -> Bool",
                "    (if (let* ((outer (command-result first",
                '                        :argv ("python" "scripts/first.py")',
                "                        :returns Bool)))",
                "          (let* ((outer (command-result second",
                '                          :argv ("python" "scripts/second.py")',
                "                          :returns Bool)))",
                "            outer))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("first", "second", "yes", "no"),
    )

    assert _cond_pure_ops(body) == []
    assert isinstance(body, LetStarExpr)
    # The authored `outer` names stay nested, never flattened into the outer
    # condition prefix.
    assert all(not name.startswith("outer") for name, _ in body.bindings)
    first_count = sum(
        1
        for node in walk_expr(body)
        if isinstance(node, CommandResultExpr) and node.step_name == "first"
    )
    second_count = sum(
        1
        for node in walk_expr(body)
        if isinstance(node, CommandResultExpr) and node.step_name == "second"
    )
    assert first_count == 1 and second_count == 1
    outer_lets = [
        node
        for node in walk_expr(body)
        if isinstance(node, LetStarExpr)
        and any(name == "outer" for name, _ in node.bindings)
    ]
    assert len(outer_lets) == 2


def test_strict_list_map_binder_scope_preserved(tmp_path: Path) -> None:
    """A ``list/map`` body ``and`` folds inside the binder scope, not hoisted."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule list_scope)",
                "  (export gate)",
                "  (defworkflow gate ((bools List[Bool])) -> Bool",
                "    (if (let* ((flags (list/map ((f bools)) (and f true)))",
                "               (probe (command-result probe",
                '                        :argv ("python" "scripts/probe.py")',
                "                        :returns Bool)))",
                "          probe)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("probe", "yes", "no"),
    )

    assert _cond_pure_ops(body) == []
    list_maps = [node for node in walk_expr(body) if isinstance(node, ListMapExpr)]
    assert len(list_maps) == 1
    # The folded short-circuit binding stays inside the list-map body.
    assert isinstance(list_maps[0].body_expr, LetStarExpr)


def test_strict_effectful_callee_body_and_or_stays_atomic(tmp_path: Path) -> None:
    """A Bool workflow whose body is effectful ``and``, called as a condition,
    binds the call atomically and leaves the callee's ``and`` as its return."""

    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.26")',
            "  (defmodule callee_and)",
            "  (export outer)",
            "  (defworkflow gate () -> Bool",
            "    (and (command-result a",
            '           :argv ("python" "scripts/a.py")',
            "           :returns Bool)",
            "         (command-result b",
            '           :argv ("python" "scripts/b.py")',
            "           :returns Bool)))",
            "  (defworkflow outer () -> Bool",
            "    (if (call gate)",
            "        (command-result yes",
            '          :argv ("python" "scripts/yes.py")',
            "          :returns Bool)",
            "        (command-result no",
            '          :argv ("python" "scripts/no.py")',
            "          :returns Bool))))",
        ]
    )
    path = tmp_path / "callee_and.orc"
    path.write_text(source, encoding="utf-8")
    boundaries = {
        name: ExternalToolBinding(
            name=name,
            stable_command=("python", f"scripts/{name}.py"),
        )
        for name in ("a", "b", "yes", "no")
    }
    result = compile_stage3_module(
        path,
        command_boundaries=boundaries,
        provider_externs={},
        prompt_externs={},
        validate_shared=False,
        workspace_root=tmp_path,
    )
    gate = next(w for w in result.typed_workflows if w.definition.name == "gate")
    outer = next(w for w in result.typed_workflows if w.definition.name == "outer")
    # The outer condition binds the workflow call exactly once (atomic).
    calls = [
        node
        for node in walk_expr(outer.typed_body.expr)
        if isinstance(node, CallExpr)
    ]
    assert len(calls) == 1
    # The callee body keeps its effectful `and` as the workflow return, not
    # folded into a raw-effect `if` (outside Task 2's condition scope).
    assert _cond_pure_ops(gate.typed_body.expr) != []


def test_strict_loop_body_and_exhaustion_normalize_in_scope(tmp_path: Path) -> None:
    """A Bool ``loop/recur`` folds state-dependent body/exhaustion ``and`` in
    scope, preserving the ``done``/``continue`` spine."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule loop_bool)",
                "  (export gate)",
                "  (defworkflow gate () -> Bool",
                "    (if (loop/recur",
                "          :max 1",
                "          :state (loop-state (count Int 0) (done Bool false))",
                "          :on-exhausted (and false false)",
                "          (fn (state)",
                "            (if (and (= state.count 0) (= state.done false))",
                "                (done true)",
                "                (continue (loop-state :like state :count 1 :done true)))))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("yes", "no"),
    )

    assert _cond_pure_ops(body) == []
    loops = [node for node in walk_expr(body) if isinstance(node, LoopRecurExpr)]
    assert len(loops) == 1
    # Exhaustion `and` folds inside the exhaustion branch, not the prefix.
    assert isinstance(loops[0].on_exhausted_result_expr, LetStarExpr)
    # Body `and` folds inside the loop body.
    assert isinstance(loops[0].body_expr, LetStarExpr)


def test_strict_command_traversal_includes_adapter_inputs() -> None:
    """The generic traversal covers certified adapter inputs, not only argv."""

    expr = elaborate_expression(
        _expression_syntax(
            "(command-result normalize_scalars"
            "  :adapter normalize_scalars"
            "  :inputs ((flag (and a b)) (count 1))"
            "  :returns NormalizedPayload)"
        ),
        bound_names=frozenset({"a", "b"}),
    )
    children = iter_child_exprs(expr)
    assert any(
        isinstance(child, PureOpExpr) and child.operator == "and"
        for child in children
    )


def test_strict_with_phase_body_normalizes_in_scope(tmp_path: Path) -> None:
    """A direct exact-Bool ``with-phase`` folds its body ``and`` inside the
    phase scope and binds the complete wrapper once."""

    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.26")',
            "  (defmodule phase_bool)",
            "  (import std/phase :only (with-phase))",
            "  (export gate)",
            "  (defrecord RunCtx",
            "    (run-id RunId)",
            "    (state-root Path.state-root)",
            "    (artifact-root Path.artifact-root))",
            "  (defrecord PhaseCtx",
            "    (run RunCtx)",
            "    (phase-name Symbol)",
            "    (state-root Path.state-root)",
            "    (artifact-root Path.artifact-root))",
            "  (defworkflow gate ((phase-ctx PhaseCtx) (a Bool) (b Bool)) -> Bool",
            "    (if (with-phase phase-ctx implementation",
            "          (and a b))",
            "        (command-result yes",
            '          :argv ("python" "scripts/yes.py")',
            "          :returns Bool)",
            "        (command-result no",
            '          :argv ("python" "scripts/no.py")',
            "          :returns Bool))))",
        ]
    )
    path = tmp_path / "phase_bool.orc"
    path.write_text(source, encoding="utf-8")
    boundaries = {
        name: ExternalToolBinding(
            name=name,
            stable_command=("python", f"scripts/{name}.py"),
        )
        for name in ("yes", "no")
    }
    result = compile_stage3_module(
        path,
        command_boundaries=boundaries,
        provider_externs={},
        prompt_externs={},
        validate_shared=False,
        workspace_root=tmp_path,
    )
    body = result.typed_workflows[-1].typed_body.expr
    assert _cond_pure_ops(body) == []
    phases = [node for node in walk_expr(body) if isinstance(node, WithPhaseExpr)]
    assert len(phases) == 1
    # The folded body `and` stays inside the phase body.
    assert isinstance(phases[0].body, LetStarExpr)


def test_strict_loop_body_if_branch_effect_stays_inside(tmp_path: Path) -> None:
    """An effectful `if` branch inside a loop body keeps its binding inside the
    branch, so an untaken `done`/`continue` branch never executes the effect."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule loop_branch)",
                "  (export gate)",
                "  (defworkflow gate () -> Bool",
                "    (if (loop/recur",
                "          :max 1",
                "          :state (loop-state (count Int 0) (done Bool false))",
                "          :on-exhausted false",
                "          (fn (state)",
                "            (if (= state.done false)",
                "                (done (command-result done_effect",
                '                        :argv ("python" "scripts/done_effect.py")',
                "                        :returns Bool))",
                "                (continue (loop-state :like state :count 1 :done true)))))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("done_effect", "yes", "no"),
    )

    assert _cond_pure_ops(body) == []
    loop = next(node for node in walk_expr(body) if isinstance(node, LoopRecurExpr))
    # The effect binding is wrapped inside the `done` branch, not hoisted to the
    # loop-body prefix.
    assert isinstance(loop.body_expr, IfExpr)
    then_body = loop.body_expr.then_expr
    assert isinstance(then_body, LetStarExpr)
    # Effect-count: the `done` branch holds exactly one command; neither the
    # spine condition nor the untaken `continue` branch carries one.
    assert _command_nodes(then_body) == 1
    assert _command_nodes(loop.body_expr.condition_expr) == 0
    assert _command_nodes(loop.body_expr.else_expr) == 0


def test_strict_loop_body_match_arm_binding_stays_inside(tmp_path: Path) -> None:
    """A loop-body `match` arm effect stays inside its arm, never escaping."""

    body = _typed_body(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule loop_match)",
                "  (export gate)",
                "  (defunion Subject (A (flag Bool)) (B (flag Bool)))",
                "  (defworkflow gate () -> Bool",
                "    (if (loop/recur",
                "          :max 1",
                "          :state (loop-state (count Int 0))",
                "          :on-exhausted false",
                "          (fn (state)",
                "            (match (command-result subject",
                '                     :argv ("python" "scripts/subject.py")',
                "                     :returns Subject)",
                "              ((A a)",
                "               (done (command-result must_not_run",
                '                      :argv ("python" "scripts/must_not_run.py")',
                "                      :returns Bool)))",
                "              ((B b)",
                "               (continue (loop-state :like state :count 1))))))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        tmp_path,
        command_names=("subject", "must_not_run", "yes", "no"),
    )
    assert _cond_pure_ops(body) == []
    loop = next(node for node in walk_expr(body) if isinstance(node, LoopRecurExpr))
    match = next(node for node in walk_expr(loop.body_expr) if isinstance(node, MatchExpr))
    arm_a = match.arms[0]
    assert isinstance(arm_a.body, LetStarExpr)
    # Effect-count: the `A` arm holds exactly one command (`must_not_run`); it
    # never escapes into the loop-body prefix or the sibling arm.
    assert _command_nodes(arm_a.body) == 1
    assert _command_nodes(match.arms[1].body) == 0


_EFFECTFUL_IF_FORMS = (
    "(defpath WorkReport",
    '  :kind relpath',
    '  :under "artifacts/work"',
    "  :must-exist true)",
    "(defrecord ReadyResult",
    "  (ready Bool))",
    "(defrecord ImplementationSummary",
    "  (report WorkReport))",
    "(defworkflow invalid-if-condition-effectful",
    "  ((report_path WorkReport)",
    "   (fallback_path WorkReport))",
    "  -> ImplementationSummary",
    "  (if",
    "    (let* ((ready-result",
    "             (command-result run_checks",
    '               :argv ("python" "scripts/run_checks.py" report_path)',
    "               :returns ReadyResult)))",
    "      ready-result.ready)",
    "    (record ImplementationSummary",
    "      :report report_path)",
    "    (record ImplementationSummary",
    "      :report fallback_path)))",
)
_NONPROJECTABLE_IF_FORMS = (
    "(defpath WorkReport",
    '  :kind relpath',
    '  :under "artifacts/work"',
    "  :must-exist true)",
    "(defrecord ImplementationSummary",
    "  (report WorkReport))",
    "(defun identity-bool",
    "  ((value Bool))",
    "  -> Bool",
    "  value)",
    "(defworkflow invalid-if-condition-not-projectable",
    "  ((ready Bool)",
    "   (report_path WorkReport)",
    "   (fallback_path WorkReport))",
    "  -> ImplementationSummary",
    "  (if (identity-bool ready)",
    "    (record ImplementationSummary",
    "      :report report_path)",
    "    (record ImplementationSummary",
    "      :report fallback_path)))",
)


def _module_for_target(target_dsl: str, forms: tuple[str, ...]) -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target_dsl}")',
            *(f"  {form}" for form in forms),
            ")",
        )
    )


def _serialized_if_diagnostic_bytes(
    tmp_path: Path,
    target_dsl: str,
    forms: tuple[str, ...],
) -> bytes:
    path = tmp_path / "if_diagnostic.orc"
    path.write_text(_module_for_target(target_dsl, forms), encoding="utf-8")
    boundaries = {
        "run_checks": ExternalToolBinding(
            name="run_checks",
            stable_command=("python", "scripts/run_checks.py"),
        )
    }
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            command_boundaries=boundaries,
            validate_shared=False,
            workspace_root=tmp_path,
        )
    payload = serialize_diagnostic(excinfo.value.diagnostics[0])
    # The retained source path is the machine-specific absolute form of the
    # generated file; assert it resolves to the exact generated path, then
    # normalize away only the verified workspace prefix.
    assert Path(payload["path"]).resolve() == path.resolve()
    payload["path"] = path.relative_to(tmp_path).as_posix()
    return canonical_json_bytes(payload)


_EFFECTFUL_IF_DIAGNOSTIC_GOLDEN = (
    b'{"authority_layer":"frontend","code":"if_condition_has_effect",'
    b'"column":7,"diagnostic_kind":"validation","expansion_stack":[],'
    b'"form_path":["workflow-lisp","defworkflow",'
    b'"invalid-if-condition-effectful"],"line":17,'
    b'"message":"`if` condition must be pure","notes":[],'
    b'"path":"if_diagnostic.orc","phase":"typecheck",'
    b'"severity":"error","validation_pass":"type"}'
)

_NONPROJECTABLE_IF_DIAGNOSTIC_GOLDEN = (
    b'{"authority_layer":"frontend","code":"if_condition_not_projectable",'
    b'"column":9,"diagnostic_kind":"validation","expansion_stack":[],'
    b'"form_path":["workflow-lisp","defworkflow",'
    b'"invalid-if-condition-not-projectable"],"line":19,'
    b'"message":"`if` condition must lower from a Bool literal or '
    b'already-typed Bool ref","notes":[],'
    b'"path":"if_diagnostic.orc","phase":"read",'
    b'"severity":"error","validation_pass":"parse"}'
)


def test_target_225_effectful_if_diagnostic_bytes_unchanged(
    tmp_path: Path,
) -> None:
    """Target 2.25 keeps the pre-change effectful-`if` diagnostic byte-for-byte."""

    current = _serialized_if_diagnostic_bytes(
        tmp_path, "2.25", _EFFECTFUL_IF_FORMS
    )
    assert current == _EFFECTFUL_IF_DIAGNOSTIC_GOLDEN


def test_target_225_nonprojectable_if_diagnostic_bytes_unchanged(
    tmp_path: Path,
) -> None:
    """Target 2.25 keeps the pre-change nonprojectable-`if` bytes identical."""

    current = _serialized_if_diagnostic_bytes(
        tmp_path, "2.25", _NONPROJECTABLE_IF_FORMS
    )
    assert current == _NONPROJECTABLE_IF_DIAGNOSTIC_GOLDEN


def test_target_226_admits_effectful_and_nonprojectable_if(
    tmp_path: Path,
) -> None:
    """Target 2.26 admits an effectful and a nonprojectable `if` condition."""

    for forms in (_EFFECTFUL_IF_FORMS, _NONPROJECTABLE_IF_FORMS):
        path = tmp_path / "if_admitted.orc"
        path.write_text(_module_for_target("2.26", forms), encoding="utf-8")
        result = compile_stage3_module(
            path,
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )
        assert result.typed_workflows


# ---------------------------------------------------------------------------
# Task 3A: contextual union tags and discriminant-derived proof
# ---------------------------------------------------------------------------

_PROOF_TYPES_MODULE = "\n".join(
    [
        "(workflow-lisp",
        '  (:language "0.1")',
        '  (:target-dsl "2.26")',
        "  (defmodule proof)",
        '  (defpath WorkReport :kind relpath :under "artifacts/work" :must-exist true)',
        "  (defenum BlockerClass missing_resource unavailable_hardware)",
        "  (defunion ImplementationState",
        "    (COMPLETED (execution_report WorkReport))",
        "    (BLOCKED (progress_report WorkReport) (blocker_class BlockerClass)))",
        "  (defunion ReviewOutcome",
        "    (APPROVED (approval_report WorkReport))",
        "    (REJECTED (rejection_report WorkReport))))",
    ]
)


def _proof_env(tmp_path: Path) -> FrontendTypeEnvironment:
    path = tmp_path / "proof_types.orc"
    path.write_text(_PROOF_TYPES_MODULE, encoding="utf-8")
    return FrontendTypeEnvironment.from_module(compile_stage1_module(path))


def _proof_type(tmp_path: Path, name: str):
    probe = _expression_syntax('"seed"')
    return _proof_env(tmp_path).resolve_type(name, span=probe.span, form_path=probe.form_path)


def _check_226(type_env: FrontendTypeEnvironment, source: str, value_env: dict):
    expr = elaborate_expression(
        _expression_syntax(source),
        bound_names=frozenset(value_env),
        target_dsl_version="2.26",
    )
    return typecheck_expression(expr, type_env=type_env, value_env=value_env)


def _find_if(expr) -> IfExpr:
    return next(
        node
        for node in walk_expr(expr)
        if isinstance(node, IfExpr) and node.true_proof_context is not None
    )


def _variant_set(context, name: str) -> frozenset:
    for identity, possible in (context or {}).items():
        if identity.name == name:
            return frozenset(possible.variants)
    return frozenset()


def _diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError]) -> str:
    return excinfo.value.diagnostics[0].code


def test_strict_requires_variant_local_union_branch_narrows(tmp_path: Path) -> None:
    """A let*-bound union narrowed by `=` authorizes a variant-only field."""
    type_env = _proof_env(tmp_path)
    report = _proof_type(tmp_path, "WorkReport")
    typed = _check_226(
        type_env,
        "(let* ((attempt (variant ImplementationState COMPLETED :execution_report r)))"
        "  (if (= attempt.variant COMPLETED) attempt.execution_report attempt.progress_report))",
        {"r": report},
    )
    assert typed.type_ref.name == "WorkReport"
    if_expr = _find_if(typed.expr)
    assert _variant_set(if_expr.true_proof_context, "attempt") == {"COMPLETED"}
    assert _variant_set(if_expr.false_proof_context, "attempt") == {"BLOCKED"}


def test_strict_input_union_parameter_branch_narrows(tmp_path: Path) -> None:
    """A workflow-input/ordinary-local union narrows and is consumed in branch."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    report = _proof_type(tmp_path, "WorkReport")
    typed = _check_226(
        type_env,
        "(if (= attempt.variant COMPLETED) attempt.execution_report attempt.progress_report)",
        {"attempt": attempt},
    )
    assert typed.type_ref.name == "WorkReport"
    if_expr = _find_if(typed.expr)
    assert _variant_set(if_expr.true_proof_context, "attempt") == {"COMPLETED"}
    assert _variant_set(if_expr.false_proof_context, "attempt") == {"BLOCKED"}


def test_strict_multi_union_leaf_consumes_two_narrowed_fields(tmp_path: Path) -> None:
    """One branch narrows two independent unions and consumes a field of each."""
    type_env = _proof_env(tmp_path)
    report = _proof_type(tmp_path, "WorkReport")
    typed = _check_226(
        type_env,
        "(let* ((attempt (variant ImplementationState COMPLETED :execution_report r))"
        "       (outcome (variant ReviewOutcome APPROVED :approval_report r)))"
        "  (if (and (= attempt.variant COMPLETED) (= outcome.variant APPROVED))"
        "      (let* ((a attempt.execution_report) (b outcome.approval_report)) a)"
        "      r))",
        {"r": report},
    )
    assert typed.type_ref.name == "WorkReport"
    if_expr = _find_if(typed.expr)
    assert _variant_set(if_expr.true_proof_context, "attempt") == {"COMPLETED"}
    assert _variant_set(if_expr.true_proof_context, "outcome") == {"APPROVED"}


def test_strict_variant_proof_equality_symmetric_tag(tmp_path: Path) -> None:
    """`(= COMPLETED attempt.variant)` resolves the tag on either side."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    report = _proof_type(tmp_path, "WorkReport")
    typed = _check_226(
        type_env,
        "(if (= COMPLETED attempt.variant) attempt.execution_report attempt.progress_report)",
        {"attempt": attempt},
    )
    assert typed.type_ref.name == "WorkReport"
    if_expr = _find_if(typed.expr)
    assert _variant_set(if_expr.true_proof_context, "attempt") == {"COMPLETED"}
    assert any(
        isinstance(node, UnionVariantTagExpr) and node.variant_name == "COMPLETED"
        for node in walk_expr(typed.expr)
    )


def test_strict_variant_proof_inequality_excludes_to_singleton(tmp_path: Path) -> None:
    """`(!= attempt.variant BLOCKED)` proves the remaining singleton on true."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    report = _proof_type(tmp_path, "WorkReport")
    typed = _check_226(
        type_env,
        "(if (!= attempt.variant BLOCKED) attempt.execution_report attempt.progress_report)",
        {"attempt": attempt},
    )
    assert typed.type_ref.name == "WorkReport"
    if_expr = _find_if(typed.expr)
    assert _variant_set(if_expr.true_proof_context, "attempt") == {"COMPLETED"}
    assert _variant_set(if_expr.false_proof_context, "attempt") == {"BLOCKED"}


def test_strict_variant_proof_and_or_not_composition(tmp_path: Path) -> None:
    """`and`, `or`, and `not` compose the closed fact algebra."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    report = _proof_type(tmp_path, "WorkReport")

    and_typed = _check_226(
        type_env,
        "(if (and (= attempt.variant COMPLETED) ready)"
        "    attempt.execution_report r)",
        {
            "attempt": attempt,
            "ready": _proof_type(tmp_path, "Bool"),
            "r": report,
        },
    )
    and_if = _find_if(and_typed.expr)
    assert _variant_set(and_if.true_proof_context, "attempt") == {"COMPLETED"}

    or_typed = _check_226(
        type_env,
        "(if (or (!= attempt.variant BLOCKED) (= attempt.variant COMPLETED))"
        "    attempt.execution_report attempt.progress_report)",
        {"attempt": attempt},
    )
    or_if = _find_if(or_typed.expr)
    # The joined true path is still the COMPLETED singleton.
    assert _variant_set(or_if.true_proof_context, "attempt") == {"COMPLETED"}
    assert _variant_set(or_if.false_proof_context, "attempt") == {"BLOCKED"}

    not_typed = _check_226(
        type_env,
        "(if (not (= attempt.variant BLOCKED))"
        "    attempt.execution_report attempt.progress_report)",
        {"attempt": attempt},
    )
    not_if = _find_if(not_typed.expr)
    assert _variant_set(not_if.true_proof_context, "attempt") == {"COMPLETED"}


def test_strict_variant_proof_contradiction_unreachable(tmp_path: Path) -> None:
    """A contradictory conjunction makes the true path unreachable."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    report = _proof_type(tmp_path, "WorkReport")
    typed = _check_226(
        type_env,
        "(if (and (= attempt.variant COMPLETED) (= attempt.variant BLOCKED))"
        "    r r)",
        {"attempt": attempt, "r": report},
    )
    if_expr = _find_if(typed.expr)
    # Unreachable true path stores no facts.
    assert if_expr.true_proof_context == {}


def test_strict_variant_proof_non_recognized_routes_without_narrowing(
    tmp_path: Path,
) -> None:
    """A non-discriminant condition routes without authorizing variant fields."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    report = _proof_type(tmp_path, "WorkReport")
    ready = _proof_type(tmp_path, "Bool")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _check_226(
            type_env,
            "(if ready attempt.execution_report r)",
            {"attempt": attempt, "ready": ready, "r": report},
        )
    assert _diagnostic_code(excinfo) == "variant_ref_unproved"


def test_strict_variant_shadow_same_spelling_distinct_identity(tmp_path: Path) -> None:
    """Shadowed let* binders receive distinct ordinals, never colliding by name."""
    type_env = _proof_env(tmp_path)
    report = _proof_type(tmp_path, "WorkReport")
    typed = _check_226(
        type_env,
        "(let* ((attempt (variant ImplementationState COMPLETED :execution_report r)))"
        "  (let* ((attempt (variant ImplementationState BLOCKED :progress_report r"
        "                     :blocker_class BlockerClass.missing_resource)))"
        "    (if (= attempt.variant BLOCKED) attempt.progress_report r)))",
        {"r": report},
    )
    if_expr = _find_if(typed.expr)
    identities = list(if_expr.true_proof_context)
    assert len(identities) == 1
    assert identities[0].name == "attempt"
    assert identities[0].ordinal == 1


def test_strict_variant_alias_receives_no_proof(tmp_path: Path) -> None:
    """A let* alias is a fresh identity; proof does not propagate to the source."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    report = _proof_type(tmp_path, "WorkReport")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _check_226(
            type_env,
            "(let* ((alias attempt))"
            "  (if (= alias.variant COMPLETED) attempt.execution_report r))",
            {"attempt": attempt, "r": report},
        )
    assert _diagnostic_code(excinfo) == "variant_ref_unproved"


def test_strict_variant_lexical_binding_wins_over_contextual_tag(
    tmp_path: Path,
) -> None:
    """A bound `COMPLETED` name beats contextual tag lookup."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    flag = _proof_type(tmp_path, "Bool")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _check_226(
            type_env,
            "(let* ((COMPLETED ready))"
            "  (if (= attempt.variant COMPLETED) attempt.execution_report r))",
            {
                "attempt": attempt,
                "ready": flag,
                "r": _proof_type(tmp_path, "WorkReport"),
            },
        )
    assert _diagnostic_code(excinfo) == "pure_expr_operand_type_mismatch"


def test_strict_variant_contextual_tag_unknown_fails(tmp_path: Path) -> None:
    """An undeclared tag fails with a dedicated diagnostic."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _check_226(
            type_env,
            "(= attempt.variant MISSING)",
            {"attempt": attempt},
        )
    assert _diagnostic_code(excinfo) == "variant_tag_unknown"


def test_strict_variant_contextual_tag_no_context_fails(tmp_path: Path) -> None:
    """A bare tag paired with a union (not a discriminant) lacks a context."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _check_226(
            type_env,
            "(= attempt COMPLETED)",
            {"attempt": attempt},
        )
    assert _diagnostic_code(excinfo) == "variant_tag_context_missing"


def test_strict_variant_contextual_cross_union_fails(tmp_path: Path) -> None:
    """A tag declared by a different union is rejected."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _check_226(
            type_env,
            "(= attempt.variant APPROVED)",
            {"attempt": attempt},
        )
    assert _diagnostic_code(excinfo) == "variant_tag_unknown"


def test_strict_variant_discriminant_equality_proves_no_variant(tmp_path: Path) -> None:
    """Compatible discriminant-to-discriminant equality routes but proves nothing."""
    type_env = _proof_env(tmp_path)
    attempt = _proof_type(tmp_path, "ImplementationState")
    report = _proof_type(tmp_path, "WorkReport")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _check_226(
            type_env,
            "(if (= attempt.variant other.variant) attempt.execution_report r)",
            {"attempt": attempt, "other": attempt, "r": report},
        )
    assert _diagnostic_code(excinfo) == "variant_ref_unproved"
