"""Numeric operators: rules N2 to N5 of the numeric surface, at target 2.34.

Contract: docs/design/workflow_lisp_numeric_surface.md, rules N2 to N5 and sections 4,
6 and 7; Task 6 of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md.

Operands come from workflow inputs, so the operators run in the generated pure
projection step. A refusal names its operator and prints its operands; with literal
operands the same refusal is a compile error at the expression. Target 2.33 keeps
today's refusals. The fixture of section 4, `branch-score`, gives the double that a
Python reference of the same formula gives.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_lisp_generic_unions_runtime import (
    _compile,
    _public_run,
    _public_run_files,
    _write_sources,
)


INT64_MIN = -(2**63)
BRANCH_SCORE = Path(__file__).parent / "fixtures" / "workflow_lisp" / "numeric_surface" / "branch_score.orc"
EXPR_LINE, EXPR_COLUMN = 8, 5


def _source(expr: str, params: dict[str, object], *, result: str, target: str = "2.34") -> str:
    declared = " ".join(f"({name} {'Int' if type(value) is int else 'Float'})" for name, value in params.items())
    return (
        f'(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "{target}")\n'
        "  (defmodule grt/entry)\n  (export run)\n  (defrecord DivMod (q Int) (r Int) (back Int))\n"
        f"  (defworkflow run ({declared}) -> {result}\n    {expr}))\n"
    )


def _run(root: Path, monkeypatch: pytest.MonkeyPatch, source: str, inputs: dict[str, object]):
    _write_sources(root, {"grt/entry.orc": source})
    files = _public_run_files(root, {})
    input_file = root / "inputs.json"
    input_file.write_text(json.dumps(inputs), encoding="utf-8")
    monkeypatch.chdir(root)
    return _public_run(files, input_file=input_file)


def _refusal_at_compile_time(root: Path, source: str):
    _write_sources(root, {"grt/entry.orc": source})
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(root)
    diagnostic = excinfo.value.diagnostics[0]
    return diagnostic.code, (diagnostic.span.start.line, diagnostic.span.start.column), diagnostic.message


def _failed_step(root: Path, outcome) -> tuple[dict, tuple[int, int]]:
    """The error of the one failed step and the source position the build's source map gives it."""

    state = json.loads((Path(outcome.run_root) / "state.json").read_text(encoding="utf-8"))
    [(name, step)] = [(n, s) for n, s in state["steps"].items() if isinstance(s, dict) and s.get("status") == "failed"]
    [source_map] = (root / ".orchestrate" / "build").glob("*/source_map.json")
    origin = json.loads(source_map.read_text(encoding="utf-8"))["workflows"]["grt/entry::run"]["step_ids"][name]
    return step["error"], (origin["line"], origin["column"])


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
def test_operator_result_through_the_public_run_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expr: str, inputs: dict[str, object], result: object
) -> None:
    outcome = _run(tmp_path, monkeypatch, _source(expr, inputs, result=_type(result)), inputs)

    assert (outcome.exit_code, dict(outcome.workflow_outputs)) == (0, {"__result__": result})
    assert type(outcome.workflow_outputs["__result__"]) is type(result)


DIV_MOD = "(record DivMod :q (int/div i j) :r (int/mod i j) :back (+ (* (int/div i j) j) (int/mod i j)))"


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
def test_int_div_rounds_to_negative_infinity_and_int_mod_takes_the_divisor_sign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, i: int, j: int, q: int, r: int
) -> None:
    outcome = _run(tmp_path, monkeypatch, _source(DIV_MOD, {"i": i, "j": j}, result="DivMod"), {"i": i, "j": j})

    assert (outcome.exit_code, dict(outcome.workflow_outputs)) == (
        0,
        {"return__q": q, "return__r": r, "return__back": i},
    )


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
def test_refusal_at_run_time_names_the_operator_and_prints_the_operands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expr: str, inputs: dict[str, object], result: str, code: str
) -> None:
    outcome = _run(tmp_path, monkeypatch, _source(expr, inputs, result=result), inputs)
    error, position = _failed_step(tmp_path, outcome)
    operator = expr[1:].split(" ", 1)[0]

    assert (outcome.exit_code, error["type"], position) == (1, code, (EXPR_LINE, EXPR_COLUMN))
    metadata = error["context"]["metadata"]
    assert (metadata["operator"], metadata["operands"]) == (operator, list(inputs.values()))
    assert f"`{operator}`" in error["message"]
    assert all(_literal(value) in error["message"] for value in inputs.values())


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


NEW_OPERATORS_AT_233 = (
    "(/ a b)", "(int/div i j)", "(int/mod i j)", "(float/abs a)", "(float/sqrt a)", "(float/log a)",
    "(int/to-float i)", "(float/floor a)", "(float/round a)",
)  # fmt: skip


@pytest.mark.parametrize(
    ("expr", "code", "column"),
    [
        # An unknown operator is reported at its name, a type mismatch at the application.
        *((expr, "pure_expr_operator_unsupported", EXPR_COLUMN + 1) for expr in NEW_OPERATORS_AT_233),
        *(
            (expr, "pure_expr_operand_type_mismatch", EXPR_COLUMN)
            for expr in ("(+ a b)", "(- a b)", "(* a b)", "(min a b)", "(max a b)")
        ),
    ],
)
def test_target_233_keeps_todays_refusals(tmp_path: Path, expr: str, code: str, column: int) -> None:
    source = _source(expr, FLOATS_AND_INTS, result="Float", target="2.33")

    observed, position, _ = _refusal_at_compile_time(tmp_path, source)

    assert (observed, position) == (code, (EXPR_LINE, column))


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
def test_branch_score_gives_the_double_of_its_python_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, total: float, visits: int, all_visits: int, weight: float
) -> None:
    shutil.copy(BRANCH_SCORE, tmp_path / "branch_score.orc")
    files = {**_public_run_files(tmp_path, {}), "source": tmp_path / "branch_score.orc"}
    input_file = tmp_path / "inputs.json"
    inputs = {"total": total, "visits": visits, "all-visits": all_visits, "weight": weight}
    input_file.write_text(json.dumps(inputs), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    outcome = _public_run(files, input_file=input_file)

    assert (outcome.exit_code, dict(outcome.workflow_outputs)) == (
        0,
        {"__result__": branch_score(total, visits, all_visits, weight)},
    )
