"""A constructor field's bindings stay scoped to that field when a sibling field is a `match`.

Each program runs through `run_workflow` and asserts the value it returns. The
control runs the same program with every `match` replaced by its subject's
field value, which takes the other constructor path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workflow_lisp_elaborated_prefixes import _scope_files
from tests.workflow_evaluated_totality_helpers import _write_sources, public_run

MODULE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule grt/entry)
  (export run)
  (defrecord Tri (a Int) (b Int) (c Int))
  (defrecord Box (p Tri) (q Int))
  (defunion Shape (CIRCLE (r Int)) (SQUARE (s Int)))
  (defunion Choice (YES (x Int) (y Int) (z Int)) (NO (v Int)))
  (defworkflow run ((n Int)) -> RETURNS
    BODY))
"""


def _match(subject_value: str) -> str:
    return f"(match (variant Shape CIRCLE :r {subject_value}) ((CIRCLE c) c.r) ((SQUARE s) 0))"


# name: (returns, body with `M(x)` for a `match` that returns `x`, value at n = 3)
PROGRAMS = {
    "record-later-field": ("Tri", "(let* ((y 1)) (record Tri :a (let* ((y 7)) y) :b y :c M(n)))", {"a": 7, "b": 1, "c": 3}),
    "record-match-first": ("Tri", "(let* ((y 1)) (record Tri :c M(n) :a (let* ((y 7)) y) :b y))", {"a": 7, "b": 1, "c": 3}),
    "record-earlier-field": ("Tri", "(let* ((y 1)) (record Tri :a y :b (let* ((y 7)) y) :c M(n)))", {"a": 1, "b": 7, "c": 3}),
    "variant": (
        "Choice",
        "(let* ((y 1)) (variant Choice YES :x (let* ((y 7)) y) :y y :z M(n)))",
        {"variant": "YES", "x": 7, "y": 1, "z": 3},
    ),
    "nested-constructor": (
        "Box",
        "(let* ((y 1)) (record Box :p (record Tri :a (let* ((y 7)) y) :b 0 :c 0) :q M(y)))",
        {"p": {"a": 7, "b": 0, "c": 0}, "q": 1},
    ),
    "workflow-parameter": ("Tri", "(record Tri :a (let* ((n 7)) n) :b n :c M(n))", {"a": 7, "b": 3, "c": 3}),
    "match-reads-the-shadowed-name": ("Tri", "(let* ((y 1)) (record Tri :a (let* ((y 7)) y) :b 0 :c M(y)))", {"a": 7, "b": 0, "c": 1}),
    "two-match-fields": ("Tri", "(let* ((y 1)) (record Tri :a M(n) :b (let* ((y 7)) y) :c M(y)))", {"a": 3, "b": 7, "c": 1}),
    "name-bound-by-a-match-arm": ("Tri", "(let* ((c 1)) (record Tri :a (let* ((c 7)) c) :b c :c M(n)))", {"a": 7, "b": 1, "c": 3}),
    "match-arm-binding-does-not-leak": ("Tri", "(let* ((c 1)) (record Tri :a 0 :c M(n) :b c))", {"a": 0, "b": 1, "c": 3}),
    "match-subject-binding-does-not-leak": (
        "Tri",
        "(let* ((c 1)) (record Tri :a 0 :c M((let* ((c n)) c)) :b c))",
        {"a": 0, "b": 1, "c": 3},
    ),
}


def _body(template: str, *, with_match: bool) -> str:
    """Replace each `M(x)` (balanced parentheses) with a `match` returning `x`, or with `x`."""

    out, rest = "", template
    while "M(" in rest:
        head, tail = rest.split("M(", 1)
        depth, end = 1, 0
        while depth:
            depth += {"(": 1, ")": -1}.get(tail[end], 0)
            end += 1
        argument = tail[: end - 1]
        out += head + (_match(argument) if with_match else argument)
        rest = tail[end:]
    return out + rest


def _returned(root: Path, monkeypatch: pytest.MonkeyPatch, returns: str, body: str) -> tuple[int, dict]:
    _write_sources(root, {"grt/entry.orc": MODULE.replace("RETURNS", returns).replace("BODY", body)})
    input_file = root / "inputs.json"
    input_file.write_text(json.dumps({"n": 3}), encoding="utf-8")
    monkeypatch.chdir(root)
    result = public_run(_scope_files(root, {}), input_file=input_file)
    return result.exit_code, dict(result.workflow_outputs or {})


@pytest.mark.parametrize("name", list(PROGRAMS))
def test_a_field_binding_keeps_its_scope_beside_a_match_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    returns, template, value = PROGRAMS[name]

    assert _returned(tmp_path, monkeypatch, returns, _body(template, with_match=True)) == (0, value)


@pytest.mark.parametrize("name", list(PROGRAMS))
def test_control_the_same_program_without_a_match_field_returns_the_same_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    returns, template, value = PROGRAMS[name]

    assert _returned(tmp_path, monkeypatch, returns, _body(template, with_match=False)) == (0, value)
