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

An inlined procedure's specialization bindings (`bind-proc` values, `let-proc`
captures, bound procedure references) are binders of its body too, and their values
are pure values from the caller: a parameter, a specialization binding or a body
binder that spells a name one of them reads is renamed.

Effects are command probes (`tick`, `choose`) that append their argv to `<probe>.log`.
Live providers are the stand-in runtime of the provider supervision end-to-end tests.
"""

from __future__ import annotations

import json
import logging
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
from tests.test_workflow_lisp_provider_supervision_e2e import _install_fake_provider_runtime


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
  (defproc add-one ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defproc add-leading ((leading Int) (value Int)) -> Int :effects () :lowering inline (+ leading value))
  (defproc rebind-leading ((leading Int) (value Int)) -> Int :effects () :lowering inline
    (let* ((leading 100)) (+ leading value)))
  (defproc add-leading-tick ((leading Int) (value Int)) -> Int
    :effects ((uses-command tick))
    :lowering inline
    (let* ((b (tick 5))) (+ leading (+ value b))))
  (defproc apply-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int :effects () :lowering inline (hook value))
  (defproc apply-int-to-b ((hook ProcRef[Int -> Int]) (b Int)) -> Int :effects () :lowering inline (hook b))
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


BINDS_2 = "(bind-proc (proc-ref add-leading) :leading 2)"
ALL = ("2.15", "2.29", "2.30", "2.33")
BELOW_230 = ("2.15", "2.29")

# Each shape: (body, lexical value, tick log, targets). The targets are the oldest
# accepting target, 2.29, 2.30 and 2.33, less those that refuse the form. The previous
# head of this task returned the captured value below 2.30 (see the task-15 report,
# fix round 1); two forms failed there with a compiler defect.
SPECIALIZATION_SHAPES = {
    "bound-value-and-a-caller-name": (
        f"(let* ((leading 9) (v (+ leading 1)) (hook {BINDS_2})) (hook v))",
        12,
        [],
        ALL,
    ),
    # Below 2.30 this failed with a compiler defect (recursion).
    "bound-value-that-reads-its-own-name": (
        "(let* ((leading 9) (hook (bind-proc (proc-ref add-leading) :leading (+ leading 1)))) (hook 5))",
        15,
        [],
        ALL,
    ),
    "bound-value-and-a-body-rebinding": (
        "(let* ((leading 9) (v (+ leading 1)) (hook (bind-proc (proc-ref rebind-leading) :leading 2))) (hook v))",
        110,
        [],
        ALL,
    ),
    "bound-value-and-an-effect-in-the-body": (
        "(let* ((b 1) (v (+ b 1)) (hook (bind-proc (proc-ref add-leading-tick) :leading 2))) (hook v))",
        9,
        ["5"],
        ALL,
    ),
    # Below 2.30 this failed with a compiler defect: the bound procedure reference
    # `hook` replaced the caller's `hook`, which `v` reads.
    "bound-procedure-reference-named-like-a-caller-name": (
        "(let* ((hook 1) (v (+ hook 1)) (twice (bind-proc (proc-ref apply-int) :hook (proc-ref add-one)))) (twice v))",
        3,
        [],
        ALL,
    ),
    "captured-value-and-a-parameter": (
        "(let* ((b 1) (v (+ b 1))) (let-proc (f ((b Int)) -> Int :captures (v) v) (apply-int (proc-ref f) 5)))",
        2,
        [],
        BELOW_230,
    ),
    "captured-value-and-an-applying-procedure-parameter": (
        "(let* ((b 1) (v (+ b 1))) (let-proc (f ((x Int)) -> Int :captures (v) v) (apply-int-to-b (proc-ref f) 5)))",
        2,
        [],
        ALL,
    ),
    "captured-value-and-a-body-rebinding": (
        "(let* ((b 1) (v (+ b 1))) (let-proc (f ((x Int)) -> Int :captures (v) (let* ((b 7)) (+ v x))) (apply-int (proc-ref f) 5)))",
        7,
        [],
        BELOW_230,
    ),
}


@pytest.mark.parametrize(
    ("shape", "target"),
    [(shape, target) for shape, spec in SPECIALIZATION_SHAPES.items() for target in spec[-1]],
)
def test_a_specialization_value_reads_the_scope_of_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, target: str
) -> None:
    body, value, ticks, _ = SPECIALIZATION_SHAPES[shape]

    assert _outcome(tmp_path, monkeypatch, body, returns="Int", target=target) == (0, {"__result__": value}, ticks, [])


@pytest.mark.parametrize("target", ["2.30", "2.33"])
def test_targets_from_230_keep_refusing_a_capture_named_like_a_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, target: str
) -> None:
    body = SPECIALIZATION_SHAPES["captured-value-and-a-parameter"][0]

    with caplog.at_level(logging.ERROR):
        outcome = _outcome(tmp_path, monkeypatch, body, returns="Int", target=target)

    assert (outcome, "[name_unknown]" in caplog.text) == ((2, {}, [], []), True)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "not repaired: a bind-proc bound value is a compile-time binding expanded where the "
        "procedure is called, so a binder between the bind-proc and the call captures its "
        "names (task-15 report, fix round 1)"
    ),
)
@pytest.mark.parametrize("target", ALL)
def test_a_bound_value_keeps_its_scope_across_a_later_binder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    body = "(let* ((b 1) (hook (bind-proc (proc-ref add-leading) :leading (+ b 1)))) (let* ((b 7)) (hook 5)))"

    assert _outcome(tmp_path, monkeypatch, body, returns="Int", target=target) == (0, {"__result__": 7}, [], [])


@pytest.mark.xfail(
    strict=True,
    reason=(
        "not repaired: from 2.30 a let-proc capture of an effect result copies the effect "
        "into the call, so the command runs again (task-15 report, fix round 1)"
    ),
)
@pytest.mark.parametrize("target", ["2.30", "2.33"])
def test_a_captured_effect_result_runs_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    body = "(let* ((v (tick 1))) (let-proc (f ((x Int)) -> Int :captures (v) v) (apply-int (proc-ref f) 5)))"

    assert _outcome(tmp_path, monkeypatch, body, returns="Int", target=target) == (0, {"__result__": 1}, ["1"], [])


LIVE_PROVIDERS = """(let* ((worker 1) (v (+ worker 1)))
      (with-live-providers
        ((worker (provider-result providers.worker :prompt prompts.worker :inputs () :timeout-sec 30 :returns String))
         (supervisor (provider-result providers.supervisor :prompt prompts.supervisor :inputs ()
                       :timeout-sec 30 :returns ProviderSteeringDirective) :observes worker))
        v))"""


@pytest.mark.xfail(
    strict=True,
    reason=(
        "not repaired: a provider supervision member binds its name in the settlement body over "
        "a pure binding that reads the same name; refused in lowering with "
        "pure_expr_operand_type_mismatch (task-15 review, finding 2)"
    ),
)
@pytest.mark.parametrize("target", ["2.16", "2.33"])
def test_a_live_provider_member_does_not_capture_a_pure_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    probes = {name: _write_probe(tmp_path, name, text) for name, text in PROBES.items()}
    source = MODULE.replace("TARGET", target).replace("RETURNS", "Int").replace("BODY", LIVE_PROVIDERS)
    for name, path in probes.items():
        source = source.replace(name.upper(), path.as_posix())
    _write_sources(tmp_path, {"grt/entry.orc": source})
    (tmp_path / "grt" / "prompt.md").write_text("review\n", encoding="utf-8")
    files = _public_run_files(tmp_path, probes)
    providers = {"providers.worker": "codex", "providers.supervisor": "supervisor-provider"}
    files["providers"].write_text(json.dumps(providers), encoding="utf-8")
    files["prompts"].write_text(json.dumps({f"prompts.{name}": "prompt.md" for name in ("worker", "supervisor")}), encoding="utf-8")
    _install_fake_provider_runtime(monkeypatch)
    monkeypatch.chdir(tmp_path)
    result = _public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (0, {"__result__": 2})
