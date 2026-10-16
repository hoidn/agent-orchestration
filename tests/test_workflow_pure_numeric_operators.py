"""Numeric operators: rules N2 to N5 of the numeric surface, at the current typed target.

Contract: docs/design/workflow_lisp_numeric_surface.md, rules N2 to N5 and sections 4,
6 and 7; Task 6 of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md.

Operands come from workflow inputs, so the operators run in the generated pure
projection step. A refusal names its operator and prints its operands; with literal
operands the same refusal is a compile error at the expression. today's refusals. The fixture of section 4, `branch-score`, gives the double that a
Python reference of the same formula gives.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.workflow_evaluated_totality_helpers import (
    _write_sources,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow.pure_expr import evaluate_pure_operator, PureExprEvaluationError


INT64_MIN = -(2**63)
EXPR_LINE, EXPR_COLUMN = 8, 5


def _source(expr: str, params: dict[str, object], *, result: str, target: str = "2.35") -> str:
    declared = " ".join(f"({name} {'Int' if type(value) is int else 'Float'})" for name, value in params.items())
    return (
        f'(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "{target}")\n'
        "  (defmodule grt/entry)\n  (export run)\n  (defrecord DivMod (q Int) (r Int) (back Int))\n"
        f"  (defworkflow run ({declared}) -> {result}\n    {expr}))\n"
    )


def _refusal_at_compile_time(root: Path, source: str):
    _write_sources(root, {"grt/entry.orc": source})
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(root / "grt/entry.orc", source_roots=(root,))
    diagnostic = excinfo.value.diagnostics[0]
    return diagnostic.code, (diagnostic.span.start.line, diagnostic.span.start.column), diagnostic.message


def _type(value: object) -> str:
    return {bool: "Bool", int: "Int", float: "Float"}[type(value)]


# (expression, inputs, result)
RESULTS = [
    ("(+ a b c)", {"a": 1.5, "b": 2.25, "c": 0.125}, 3.875),
    ("(+ i j)", {"i": 2, "j": 3}, 5),
    ("(* a b c)", {"a": 1.5, "b": 2.25, "c": -2.0}, -6.75),
    ("(* i j)", {"i": -4, "j": 3}, -12),
    ("(- a b)", {"a": 1.5, "b": 2.25}, -0.75),
    ("(- i j)", {"i": 2, "j": 5}, -3),
    ("(/ a b)", {"a": 7.5, "b": 2.0}, 3.75),
    ("(/ a b)", {"a": 1.0, "b": 3.0}, 1.0 / 3.0),
    ("(min a b c)", {"a": 1.5, "b": -2.25, "c": 0.125}, -2.25),
    ("(max a b c)", {"a": 1.5, "b": -2.25, "c": 0.125}, 1.5),
    ("(min i j)", {"i": 4, "j": -1}, -1),
    ("(max i j)", {"i": 4, "j": -1}, 4),
    ("(float/abs a)", {"a": -2.5}, 2.5),
    ("(float/abs a)", {"a": 2.5}, 2.5),
    ("(float/sqrt a)", {"a": 2.25}, 1.5),
    ("(float/sqrt a)", {"a": 2.0}, math.sqrt(2.0)),
    ("(float/log a)", {"a": 1.0}, 0.0),
    ("(float/log a)", {"a": 10.0}, math.log(10.0)),
    ("(int/to-float i)", {"i": 3}, 3.0),
    ("(int/to-float i)", {"i": 2**53 + 1}, 9007199254740992.0),
    ("(int/to-float i)", {"i": INT64_MIN}, -9223372036854775808.0),
    ("(float/floor a)", {"a": 2.5}, 2),
    ("(float/floor a)", {"a": -2.5}, -3),
    ("(float/floor a)", {"a": -9223372036854774784.0}, -9223372036854774784),
    ("(float/floor a)", {"a": -9223372036854775808.0}, INT64_MIN),
    ("(float/round a)", {"a": 2.4}, 2),
    ("(float/round a)", {"a": 2.6}, 3),
    ("(float/round a)", {"a": 0.5}, 0),
    ("(float/round a)", {"a": 1.5}, 2),
    ("(float/round a)", {"a": 2.5}, 2),
    ("(float/round a)", {"a": -2.5}, -2),
    ("(float/round a)", {"a": -3.5}, -4),
    ("(int/div i j)", {"i": 7, "j": 2}, 3),
    ("(int/mod i j)", {"i": 7, "j": 2}, 1),
]


@pytest.mark.parametrize(("expr", "inputs", "result"), RESULTS, ids=[f"{e}{list(i.values())}" for e, i, _ in RESULTS])
def test_numeric_catalog_operator_result(expr: str, inputs: dict[str, object], result: object) -> None:
    operator = expr[1:].split(" ", 1)[0]
    descriptor, observed = evaluate_pure_operator(operator, [({"kind": "primitive", "name": _type(value)}, value) for value in inputs.values()])
    assert descriptor == {"kind": "primitive", "name": _type(result)}
    assert observed == result
    assert type(observed) is type(result)


@pytest.mark.parametrize(
    ("i", "j", "q", "r"),
    [
        (7, 2, 3, 1),
        (-7, 2, -4, 1),
        (7, -2, -4, -1),
        (-7, -2, 3, -1),
        (6, 3, 2, 0),
        (-6, 3, -2, 0),
        (-1, 5, -1, 4),
        (INT64_MIN + 1, 2, -(2**62), 1),
        (-(2**63) + 1, -2, 2**62 - 1, -1),
        (2**63 - 1, 2, 2**62 - 1, 1),
    ],
)
def test_int_div_rounds_to_negative_infinity_and_int_mod_takes_the_divisor_sign(i: int, j: int, q: int, r: int) -> None:
    integer = {"kind": "primitive", "name": "Int"}
    quotient_type, quotient = evaluate_pure_operator("int/div", [(integer, i), (integer, j)])
    remainder_type, remainder = evaluate_pure_operator("int/mod", [(integer, i), (integer, j)])
    _, product = evaluate_pure_operator("*", [(quotient_type, quotient), (integer, j)])
    _, reconstructed = evaluate_pure_operator("+", [(integer, product), (remainder_type, remainder)])
    assert (quotient, remainder, reconstructed) == (q, r, i)


# (expression, inputs, result type, code)
REFUSALS = [
    ("(/ a b)", {"a": 7.5, "b": 0.0}, "Float", "pure_expr_division_by_zero"),
    ("(/ a b)", {"a": 7.5, "b": -0.0}, "Float", "pure_expr_division_by_zero"),
    ("(int/div i j)", {"i": 7, "j": 0}, "Int", "pure_expr_division_by_zero"),
    ("(int/mod i j)", {"i": 7, "j": 0}, "Int", "pure_expr_division_by_zero"),
    ("(float/sqrt a)", {"a": -1.0}, "Float", "pure_expr_float_domain"),
    ("(float/log a)", {"a": 0.0}, "Float", "pure_expr_float_domain"),
    ("(float/log a)", {"a": -1.0}, "Float", "pure_expr_float_domain"),
    ("(+ a b)", {"a": 1.7e308, "b": 1.7e308}, "Float", "pure_expr_float_not_finite"),
    ("(- a b)", {"a": -1.7e308, "b": 1.7e308}, "Float", "pure_expr_float_not_finite"),
    ("(* a b)", {"a": 1e308, "b": 10.0}, "Float", "pure_expr_float_not_finite"),
    ("(/ a b)", {"a": 1e308, "b": 1e-10}, "Float", "pure_expr_float_not_finite"),
    ("(float/floor a)", {"a": 9223372036854775808.0}, "Int", "pure_expr_overflow"),
    ("(float/round a)", {"a": -9.3e18}, "Int", "pure_expr_overflow"),
    ("(int/div i j)", {"i": INT64_MIN, "j": -1}, "Int", "pure_expr_overflow"),
    ("(* i j)", {"i": 2**62, "j": 2}, "Int", "pure_expr_overflow"),
    ("(+ i j)", {"i": 2**63 - 1, "j": 1}, "Int", "pure_expr_overflow"),
]
REFUSAL_IDS = [f"{e}{list(i.values())}" for e, i, _, _ in REFUSALS]


def _literal(value: object) -> str:
    return repr(value) if type(value) is float else str(value)


@pytest.mark.parametrize(("expr", "inputs", "result", "code"), REFUSALS, ids=REFUSAL_IDS)
def test_numeric_catalog_refusal_names_operator_and_operands(expr: str, inputs: dict[str, object], result: str, code: str) -> None:
    operator = expr[1:].split(" ", 1)[0]
    with pytest.raises(PureExprEvaluationError) as exc_info:
        evaluate_pure_operator(operator, [({"kind": "primitive", "name": _type(value)}, value) for value in inputs.values()])
    assert exc_info.value.code == code
    assert exc_info.value.metadata["operator"] == operator
    assert exc_info.value.metadata["operands"] == list(inputs.values())
    assert f"`{operator}`" in str(exc_info.value)
    assert all(_literal(value) in str(exc_info.value) for value in inputs.values())


@pytest.mark.parametrize(("expr", "inputs", "result", "code"), REFUSALS, ids=REFUSAL_IDS)
def test_refusal_with_literal_operands_is_a_compile_error_at_the_expression(
    tmp_path: Path, expr: str, inputs: dict[str, object], result: str, code: str
) -> None:
    literal_expr = expr
    for name, value in inputs.items():
        literal_expr = literal_expr.replace(f" {name}", f" {_literal(value)}")
    source = _source(literal_expr, {}, result=result)
    operator = expr[1:].split(" ", 1)[0]

    observed_code, position, message = _refusal_at_compile_time(tmp_path, source)

    assert (observed_code, position) == (code, (EXPR_LINE, EXPR_COLUMN))
    assert f"`{operator}`" in message
    assert all(_literal(value) in message for value in inputs.values())


def test_literal_refusal_inside_a_run_time_expression_is_a_compile_error_at_the_literal_application(
    tmp_path: Path,
) -> None:
    source = _source("(+ a (/ 7.5 0.0))", {"a": 1.0}, result="Float")

    code, position, _ = _refusal_at_compile_time(tmp_path, source)

    assert (code, position) == ("pure_expr_division_by_zero", (EXPR_LINE, EXPR_COLUMN + len("(+ a ")))


FLOATS_AND_INTS = {"a": 1.5, "b": 2.5, "i": 1, "j": 2}


@pytest.mark.parametrize(
    "expr",
    [
        "(+ a i)", "(* i a)", "(- a i)", "(min a i)", "(max i a)", "(+ a 1)", "(+ 1.5 1)", "(< a i)",
        "(/ i j)", "(/ a i)", "(int/div a b)", "(int/mod a i)", "(float/abs i)", "(float/sqrt i)",
        "(float/log i)", "(int/to-float a)", "(float/floor i)", "(float/round i)",
        "(- a b a)", "(/ a b a)", "(float/sqrt a b)", "(int/to-float i j)", "(+ a)", "(min a)",
    ],
)  # fmt: skip
def test_mixed_or_wrong_operands_are_refused_at_compile_time(tmp_path: Path, expr: str) -> None:
    code, position, _ = _refusal_at_compile_time(tmp_path, _source(expr, FLOATS_AND_INTS, result="Float"))

    assert (code, position) == ("pure_expr_operand_type_mismatch", (EXPR_LINE, EXPR_COLUMN))


@pytest.mark.parametrize("expr", ["(= a b)", "(!= a 1.5)", "(= 1.5 1.5)", "(!= (/ a b) a)"])
def test_float_equality_stays_refused(tmp_path: Path, expr: str) -> None:
    code, position, _ = _refusal_at_compile_time(tmp_path, _source(expr, FLOATS_AND_INTS, result="Bool"))

    assert (code, position) == ("pure_expr_float_equality_forbidden", (EXPR_LINE, EXPR_COLUMN))






def branch_score(total: float, visits: int, all_visits: int, weight: float) -> float:
    """The Python reference of `branch-score` (numeric surface design, section 4)."""

    return total / float(visits) + weight * math.sqrt(math.log(float(all_visits)) / float(visits))


BRANCH_SCORE_ROWS = [
    (0.0, 1, 1, 1.0),
    (1.0, 1, 2, 1.4142135623730951),
    (3.5, 2, 10, 1.0),
    (-2.75, 3, 10, 0.5),
    (10.0, 5, 100, 0.0),
    (-100.0, 7, 1000, 2.0),
    (0.125, 1, 1000000, 1.0),
    (123456.789, 1000, 5000, 0.7),
    (-0.001, 1, 3, 0.3),
    (5000000.0, 1000000, 1000000000, 1.4142135623730951),
    (1.0, 9007199254740993, 9007199254740993, 1.0),
    (-1e300, 3, 17, 1e10),
    (0.0, 2, 2, 0.0),
    (7.0, 3, 3, 1.0),
    (1e-300, 1, 7, 1e-5),
    (-42.0, 42, 4242, 0.25),
    (99.99, 100, 101, 3.0),
    (2.0, 4, 16, -1.0),
    (-0.5, 1, 9223372036854775807, 1.0),
    (3.141592653589793, 7, 22, 2.718281828459045),
    (1e15, 3, 1000, 0.1),
    (-7.25, 1, 1, 0.0),
    (-3.0, 4611686018427387904, 9223372036854775807, 1e18),
]


@pytest.mark.parametrize(("total", "visits", "all_visits", "weight"), BRANCH_SCORE_ROWS)
def test_numeric_catalog_branch_score_agrees_with_python_reference(total: float, visits: int, all_visits: int, weight: float) -> None:
    integer = {"kind": "primitive", "name": "Int"}
    floating = {"kind": "primitive", "name": "Float"}
    visits_type, visits_float = evaluate_pure_operator("int/to-float", [(integer, visits)])
    all_type, all_float = evaluate_pure_operator("int/to-float", [(integer, all_visits)])
    mean_type, mean = evaluate_pure_operator("/", [(floating, total), (visits_type, visits_float)])
    log_type, logarithm = evaluate_pure_operator("float/log", [(all_type, all_float)])
    ratio_type, ratio = evaluate_pure_operator("/", [(log_type, logarithm), (visits_type, visits_float)])
    sqrt_type, root = evaluate_pure_operator("float/sqrt", [(ratio_type, ratio)])
    weighted_type, weighted = evaluate_pure_operator("*", [(floating, weight), (sqrt_type, root)])
    _, observed = evaluate_pure_operator("+", [(mean_type, mean), (weighted_type, weighted)])
    assert observed == branch_score(total, visits, all_visits, weight)
