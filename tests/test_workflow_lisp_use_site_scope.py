"""Shared defect repairs, Task 15: a pure binding keeps its source scope where it is used.

Plan: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md, Task 15.
Design: docs/design/workflow_lisp_core_calculus_middle_end.md section 9 (a
reference is valid only where its definition dominates it).

Lowering keeps a pure binding as a frontend expression and resolves its free names
where the binding is used. At every target, a binder between the definition and a use
that spells one of those names is renamed, so the names resolve in the scope of the
definition. Below target 2.30 a `defun` call binds its parameters in order; a
parameter that a later argument reads is renamed, so every argument is evaluated in
the caller's scope.

Effects are command probes (`tick`, `choose`) that append their argv to `<probe>.log`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.test_workflow_lisp_hoisted_scope import PROBES, _outputs


MODULE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Pair (left Int) (right Int))
  (defunion Choice (YES (v Int)) (NO (v Int)))
  (defproc tick ((v Int)) -> Int
    :effects ((uses-command tick))
    :lowering inline
    (command-result tick :argv ("python" "TICK" v) :returns Int))
  (defproc choose ((v Int)) -> Choice
    :effects ((uses-command choose))
    :lowering inline
    (command-result choose :argv ("python" "CHOOSE" v) :returns Choice))
  (defproc add-tick ((n Int)) -> Int
    :effects ((uses-command tick))
    :lowering inline
    (let* ((b (tick 5))) (+ n b)))
  (defun select-second ((x Int) (y Int)) -> Int y)
  (defun last-two ((x Int) (y Int) (z Int)) -> Pair (record Pair :left y :right z))
  (defun crossed ((x Int) (y Int)) -> Pair (record Pair :left x :right y))
  (defworkflow run () -> RETURNS
    BODY))
"""


def _outcome(root: Path, monkeypatch: pytest.MonkeyPatch, body: str, *, returns: str, target: str):
    """Run `body` through `run_workflow`; return (exit code, outputs, tick log, choose log)."""

    root.mkdir(parents=True, exist_ok=True)
    probes = {name: _write_probe(root, name, text) for name, text in PROBES.items()}
    source = MODULE.replace("TARGET", target).replace("RETURNS", returns).replace("BODY", body)
    for name, path in probes.items():
        source = source.replace(name.upper(), path.as_posix())
    _write_sources(root, {"grt/entry.orc": source})
    monkeypatch.chdir(root)
    result = _public_run(_public_run_files(root, probes))
    return result.exit_code, dict(result.workflow_outputs or {}), _log(probes["tick"]), _log(probes["choose"])


LOOP = "(loop/recur :max 3 :state (loop-state (n Int 0)) :on-exhausted 0 (fn (state) BODY))"

# Each shape: (returns, body, lexical value, tick log, choose log, oldest accepting
# target). `v` reads the outer `b`; a later binder of `b` sits between `v` and its
# use. The base commit returned the captured value (see the task-15 report).
USE_SITE_SHAPES = {
    "rebinding-let": ("Int", "(let* ((b 1) (v (+ b 1))) (let* ((b 5)) v))", 2, [], [], "2.15"),
    "record-field": (
        "Pair",
        "(let* ((b 1) (v (+ b 1))) (let* ((b 5)) (record Pair :left v :right b)))",
        (2, 5),
        [],
        [],
        "2.14",
    ),
    # `b` is bound inside the first field; the second field's `b` is hoisted over it.
    "record-field-binding-inside-the-first-field": (
        "Pair",
        "(record Pair :left (let* ((b 1) (v (+ b 1))) v) :right (let* ((b 5)) b))",
        (2, 5),
        [],
        [],
        "2.14",
    ),
    "condition": ("Int", "(let* ((b 1) (v (= b 1))) (let* ((b 5)) (if v 10 20)))", 10, [], [], "2.15"),
    "condition-on-the-value": ("Int", "(let* ((b 1) (v (+ b 1))) (let* ((b 5)) (if (= v 6) 1 0)))", 0, [], [], "2.15"),
    "if-branch": ("Int", "(let* ((b 1) (v (+ b 1))) (if (= b 1) (let* ((b 5)) v) 0))", 2, [], [], "2.15"),
    "match-arm": (
        "Int",
        "(let* ((b 1) (v (+ b 1))) (match (choose 3) ((YES c) (let* ((b 5)) v)) ((NO c) v)))",
        2,
        [],
        ["3"],
        "2.15",
    ),
    # The base commit refused this form in lowering (`pure_expr_operand_type_mismatch`):
    # `v` read the arm's `b`, a `Choice` payload.
    "match-arm-binder": (
        "Int",
        "(let* ((b 1) (v (+ b 1))) (match (choose 3) ((YES b) v) ((NO c) v)))",
        2,
        [],
        ["3"],
        "2.15",
    ),
    "loop-body": (
        "Int",
        "(let* ((b 1) (v (+ b 1))) " + LOOP.replace("BODY", "(let* ((b 5)) (done v))") + ")",
        2,
        [],
        [],
        "2.15",
    ),
    # The base commit refused this form in lowering (`pure_expr_operand_type_mismatch`):
    # `v` read the loop parameter `state`, a record.
    "loop-parameter": (
        "Int",
        "(let* ((state 1) (v (+ state 1))) " + LOOP.replace("BODY", "(done v)") + ")",
        2,
        [],
        [],
        "2.15",
    ),
    "loop-body-alias": (
        "Int",
        "(let* ((b 1)) " + LOOP.replace("BODY", "(let* ((v b)) (let* ((b 5)) (done v)))") + ")",
        1,
        [],
        [],
        "2.15",
    ),
    "list-map-body": (
        "List[Int]",
        "(let* ((b 1) (v (+ b 1)) (xs (list 7 8))) (list/map ((x xs)) (let* ((b x)) (+ v b))))",
        (9, 10),
        [],
        [],
        "2.18",
    ),
    # `add-tick` binds `b` to `(tick 5)` and returns `(+ n b)`.
    "effect-call-argument": ("Int", "(let* ((b 1) (v (+ b 1))) (add-tick v))", 7, ["5"], [], "2.15"),
    # The base commit failed with a compiler defect (recursion): the argument read the
    # parameter `n` it was bound to.
    "effect-call-argument-named-like-the-parameter": (
        "Int",
        "(let* ((n 1) (v (+ n 1))) (add-tick v))",
        7,
        ["5"],
        [],
        "2.15",
    ),
    "effect-between-definition-and-use": (
        "Int",
        "(let* ((b 1) (v (+ b 1)) (r (tick 7))) (let* ((b (tick 5))) v))",
        2,
        ["7", "5"],
        [],
        "2.15",
    ),
    "effect-result-read-by-the-binding": (
        "Int",
        "(let* ((b (tick 1)) (v (+ b 1))) (let* ((b (tick 5))) v))",
        2,
        ["1", "5"],
        [],
        "2.15",
    ),
}

# Each shape: (returns, body, lexical value, oldest accepting target). The caller binds
# `x` (and `y`); the callee's parameters have the same names. The oldest targets use the
# legacy `defun` expansion; from 2.30 the hygienic expansion already gave these values.
DEFUN_SHAPES = {
    "one-shadowed-parameter": ("Int", "(let* ((x 9)) (select-second 2 x))", 9, "2.15"),
    "two-shadowed-parameters": ("Pair", "(let* ((x 9) (y 7)) (last-two 2 x y))", (9, 7), "2.14"),
    "two-crossed-parameters": ("Pair", "(let* ((x 9) (y 7)) (crossed y x))", (7, 9), "2.14"),
    "nested-defun-call-argument": ("Int", "(let* ((x 9)) (select-second 2 (select-second 3 x)))", 9, "2.15"),
    "pure-binding-argument": ("Int", "(let* ((x 9) (w (+ x 1))) (select-second 2 w))", 10, "2.15"),
}


def _cases(shapes: dict) -> list[tuple[str, str]]:
    """Each shape at its oldest accepting target (the last item of its spec), 2.32 and 2.33."""

    return [(shape, target) for shape, spec in shapes.items() for target in dict.fromkeys((spec[-1], "2.32", "2.33"))]


@pytest.mark.parametrize(("shape", "target"), _cases(USE_SITE_SHAPES))
def test_a_pure_binding_reads_the_scope_of_its_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, target: str
) -> None:
    returns, body, value, ticks, chooses, _ = USE_SITE_SHAPES[shape]

    assert _outcome(tmp_path, monkeypatch, body, returns=returns, target=target) == (
        0,
        _outputs(returns, value),
        ticks,
        chooses,
    )


@pytest.mark.parametrize(("shape", "target"), _cases(DEFUN_SHAPES))
def test_a_defun_argument_is_evaluated_in_the_caller_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, target: str
) -> None:
    returns, body, value, _ = DEFUN_SHAPES[shape]

    assert _outcome(tmp_path, monkeypatch, body, returns=returns, target=target) == (0, _outputs(returns, value), [], [])
