"""Decimal literals in expressions: rule N1 of the numeric surface, at target 2.34.

Contract: docs/design/workflow_lisp_numeric_surface.md, rule N1 and sections 6 and 7;
Task 3 of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md.

Each literal form runs through the public run entry in five positions. A literal that
does not fit a finite double is refused when the module is read. Target 2.33 keeps
today's refusals, and no token reads differently at 2.33.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import (
    SyntaxFloat,
    SyntaxIdentifier,
    SyntaxInt,
    build_syntax_module,
    syntax_node_datum,
)
from tests.test_workflow_lisp_generic_unions_runtime import (
    _compile,
    _public_run,
    _public_run_files,
    _write_sources,
)


LITERALS = [
    ("1.5", 1.5),
    ("-0.25", -0.25),
    ("2e-3", 0.002),
    ("1.0E6", 1000000.0),
    (".5", 0.5),
    ("5.", 5.0),
    ("-1.25e+2", -125.0),
]

LOOP = """(loop/recur :max 2
      :state (loop-state (v Float {lit}) (turn Int 0))
      :on-exhausted 0.0
      (fn (state)
        (if (= state.turn 0)
          (continue (loop-state :like state :turn 1))
          (done state.v))))"""

# position: (result type, workflow body, expected result from the literal's value)
POSITIONS = {
    "let-binding": ("Float", "(let* ((v {lit})) v)", lambda value: value),
    "record-field": ("Float", "(let* ((w (record Wrap :v {lit}))) w.v)", lambda value: value),
    "ordering-operand": ("Bool", "(< {lit} 0.1)", lambda value: value < 0.1),
    "loop-state-seed": ("Float", LOOP, lambda value: value),
    "workflow-result": ("Float", "{lit}", lambda value: value),
}


def _source(body: str, *, result: str = "Float", target: str = "2.34") -> str:
    return (
        f'(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "{target}")\n'
        "  (defmodule grt/entry)\n  (export run)\n  (defrecord Wrap (v Float))\n"
        f"  (defworkflow run () -> {result}\n    {body}))\n"
    )


def _refusal(root: Path, source: str):
    _write_sources(root, {"grt/entry.orc": source})
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(root)
    diagnostic = excinfo.value.diagnostics[0]
    return diagnostic.code, diagnostic.span.start.line, diagnostic.span.start.column


def _column_of(source: str, line: int, needle: str) -> int:
    return source.splitlines()[line - 1].index(needle) + 1


@pytest.mark.parametrize("position", sorted(POSITIONS))
@pytest.mark.parametrize(("literal", "value"), LITERALS, ids=[literal for literal, _ in LITERALS])
def test_literal_runs_in_position(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, literal: str, value: float, position: str
) -> None:
    result, body, expected = POSITIONS[position]
    _write_sources(tmp_path, {"grt/entry.orc": _source(body.format(lit=literal), result=result)})
    monkeypatch.chdir(tmp_path)

    outcome = _public_run(_public_run_files(tmp_path, {}))

    assert (outcome.exit_code, dict(outcome.workflow_outputs)) == (0, {"__result__": expected(value)})


@pytest.mark.parametrize(
    "literal",
    ["1e400", "-1e400", "1.5E+309", "1" + "0" * 400 + ".0", "-." + "9" * 20 + "e999"],
    ids=["exponent", "negative-exponent", "signed-exponent", "400-digits", "negative-leading-dot"],
)
def test_literal_that_is_not_a_finite_double_is_refused_when_read(tmp_path: Path, literal: str) -> None:
    source = _source(f"(let* ((v {literal})) v)")

    assert _refusal(tmp_path, source) == ("float_literal_not_finite", 8, _column_of(source, 8, literal))


def test_literal_that_is_not_a_finite_double_is_refused_before_elaboration(tmp_path: Path) -> None:
    """The literal sits in an unused definition; reading the module refuses it anyway."""

    source = _source("1.5").replace(
        "  (defworkflow run", "  (defun unused ((x Float)) -> Float (+ x 1e999))\n  (defworkflow run"
    )

    assert _refusal(tmp_path, source) == ("float_literal_not_finite", 7, _column_of(source, 7, "1e999"))


@pytest.mark.parametrize(
    ("literal", "code"),
    [("1.5", "frontend_parse_error"), (".5", "frontend_parse_error"), ("1e5", "name_unknown"), ("2e-3", "name_unknown")],
)
def test_target_233_keeps_todays_refusal(tmp_path: Path, literal: str, code: str) -> None:
    source = _source(f"(let* ((v {literal})) v)", target="2.33")

    assert _refusal(tmp_path, source) == (code, 8, _column_of(source, 8, literal))


def test_target_233_keeps_accepting_a_decimal_parameter_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source("x", target="2.33").replace("(defworkflow run ()", "(defworkflow run ((x Float :default 2.5))")
    _write_sources(tmp_path, {"grt/entry.orc": source})
    monkeypatch.chdir(tmp_path)

    outcome = _public_run(_public_run_files(tmp_path, {}))

    assert (outcome.exit_code, dict(outcome.workflow_outputs)) == (0, {"__result__": 2.5})


def _read_token(token: str, target: str) -> tuple[type, object]:
    text = f'(workflow-lisp (:language "0.1") (:target-dsl "{target}") (probe {token}))'
    module = build_syntax_module(read_sexpr_text(text, source_path="probe.orc"))
    datum = syntax_node_datum(module.forms[0]).items[1]
    if isinstance(datum, SyntaxIdentifier):
        return SyntaxIdentifier, datum.display_name
    return type(datum), datum.value


# token: (how it reads at 2.33, how it reads at 2.34)
TOKENS = {
    "12": ((SyntaxInt, 12), (SyntaxInt, 12)),
    "-7": ((SyntaxInt, -7), (SyntaxInt, -7)),
    "1.": ((SyntaxFloat, 1.0), (SyntaxFloat, 1.0)),
    ".5": ((SyntaxFloat, 0.5), (SyntaxFloat, 0.5)),
    "-.5": ((SyntaxFloat, -0.5), (SyntaxFloat, -0.5)),
    "1e5": ((SyntaxIdentifier, "1e5"), (SyntaxFloat, 100000.0)),
    "1E5": ((SyntaxIdentifier, "1E5"), (SyntaxFloat, 100000.0)),
    "1.e5": ((SyntaxIdentifier, "1.e5"), (SyntaxFloat, 100000.0)),
    ".5e1": ((SyntaxIdentifier, ".5e1"), (SyntaxFloat, 5.0)),
    "-2e-3": ((SyntaxIdentifier, "-2e-3"), (SyntaxFloat, -0.002)),
    "1e+3": ((SyntaxIdentifier, "1e+3"), (SyntaxFloat, 1000.0)),
    "1e-400": ((SyntaxIdentifier, "1e-400"), (SyntaxFloat, 0.0)),
}
# Tokens that read as a symbol at every target.
SYMBOLS = [
    "-", "+", ".", "-.", "1-2", "1e", "1e+", "1e-", "e5", ".e5", "-e5", "1e5x", "x1e5", "1e5.x", "1.2.3",
    "1..5", "a.b", "std/improve", "v1.2", "+1.5", "+1e5", "--1e5", "1_0.5", "1e1_0", "0x1p3", "inf", "-inf",
    "nan", "NaN", "Infinity", "1e5e5", "1ee5", "1e+-5",
]  # fmt: skip


@pytest.mark.parametrize("token", sorted(TOKENS))
def test_token_reads_as_before_at_233_and_as_rule_n1_at_234(token: str) -> None:
    assert (_read_token(token, "2.33"), _read_token(token, "2.34")) == TOKENS[token]


@pytest.mark.parametrize("token", SYMBOLS)
def test_token_reads_as_a_symbol_at_every_target(token: str) -> None:
    assert {_read_token(token, target) for target in ("2.14", "2.33", "2.34")} == {(SyntaxIdentifier, token)}
