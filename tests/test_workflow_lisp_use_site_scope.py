"""Pure bindings and specialization values keep their creation scope at 2.35.

Expected values and command order are fixed lexical outcomes. Excluded
live-provider forms must refuse before any effect executes.

Plan: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md, Task 15.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.workflow_evaluated_totality_helpers import _log, _write_probe, _write_sources
from tests.workflow_evaluated_totality_helpers import public_run
from tests.test_workflow_lisp_elaborated_prefixes import _scope_files
from tests.test_workflow_lisp_hoisted_scope import PROBES, _outputs
from orchestrator.providers.executor import ProviderExecutor


MODULE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
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


def _outcome(
    root: Path, monkeypatch: pytest.MonkeyPatch, body: str, *,
    returns: str, declarations: str = "",
    workflow_params: str = "", inputs: dict[str, object] | None = None,
):
    """Run `body` through `run_workflow`; return (exit code, outputs, tick log, choose log)."""

    root.mkdir(parents=True, exist_ok=True)
    probes = {name: _write_probe(root, name, text) for name, text in PROBES.items()}
    source = MODULE.replace("RETURNS", returns).replace("BODY", body)
    if declarations:
        source = source.replace("  (defworkflow run", declarations + "\n  (defworkflow run")
    if workflow_params:
        source = source.replace("  (defworkflow run () ->", f"  (defworkflow run {workflow_params} ->")
    for name, path in probes.items():
        source = source.replace(name.upper(), path.as_posix())
    _write_sources(root, {"grt/entry.orc": source})
    monkeypatch.chdir(root)
    input_file = None
    if inputs is not None:
        input_file = root / "inputs.json"
        input_file.write_text(json.dumps(inputs), encoding="utf-8")
    files = _scope_files(root, probes)
    result = public_run(files, input_file=input_file)
    return result.exit_code, dict(result.workflow_outputs or {}), _log(probes["tick"]), _log(probes["choose"])


LOOP = "(loop/recur :max 3 :state (loop-state (n Int 0)) :on-exhausted 0 (fn (state) BODY))"

# Each shape: (returns, body, lexical value, tick log, choose log). `v` reads the outer `b`; a later binder of `b` sits between `v` and its use.
USE_SITE_SHAPES = {
    "rebinding-let": ("Int", "(let* ((b 1) (v (+ b 1))) (let* ((b 5)) v))", 2, [], []),
    "record-field": (
        "Pair",
        "(let* ((b 1) (v (+ b 1))) (let* ((b 5)) (record Pair :left v :right b)))",
        (2, 5),
        [],
        [],
    ),
    # `b` is bound inside the first field; the second field's `b` is hoisted over it.
    "record-field-binding-inside-the-first-field": (
        "Pair",
        "(record Pair :left (let* ((b 1) (v (+ b 1))) v) :right (let* ((b 5)) b))",
        (2, 5),
        [],
        [],
    ),
    "condition": ("Int", "(let* ((b 1) (v (= b 1))) (let* ((b 5)) (if v 10 20)))", 10, [], []),
    "condition-on-the-value": ("Int", "(let* ((b 1) (v (+ b 1))) (let* ((b 5)) (if (= v 6) 1 0)))", 0, [], []),
    "if-branch": ("Int", "(let* ((b 1) (v (+ b 1))) (if (= b 1) (let* ((b 5)) v) 0))", 2, [], []),
    "match-arm": (
        "Int",
        "(let* ((b 1) (v (+ b 1))) (match (choose 3) ((YES c) (let* ((b 5)) v)) ((NO c) v)))",
        2,
        [],
        ["3"],
    ),
    "match-arm-binder": (
        "Int",
        "(let* ((b 1) (v (+ b 1))) (match (choose 3) ((YES b) v) ((NO c) v)))",
        2,
        [],
        ["3"],
    ),
    "loop-body": (
        "Int",
        "(let* ((b 1) (v (+ b 1))) " + LOOP.replace("BODY", "(let* ((b 5)) (done v))") + ")",
        2,
        [],
        [],
    ),
    "loop-parameter": (
        "Int",
        "(let* ((state 1) (v (+ state 1))) " + LOOP.replace("BODY", "(done v)") + ")",
        2,
        [],
        [],
    ),
    "loop-body-alias": (
        "Int",
        "(let* ((b 1)) " + LOOP.replace("BODY", "(let* ((v b)) (let* ((b 5)) (done v)))") + ")",
        1,
        [],
        [],
    ),
    "list-map-body": (
        "List[Int]",
        "(let* ((b 1) (v (+ b 1)) (xs (list 7 8))) (list/map ((x xs)) (let* ((b x)) (+ v b))))",
        (9, 10),
        [],
        [],
    ),
    # `add-tick` binds `b` to `(tick 5)` and returns `(+ n b)`.
    "effect-call-argument": ("Int", "(let* ((b 1) (v (+ b 1))) (add-tick v))", 7, ["5"], []),
    "effect-call-argument-named-like-the-parameter": (
        "Int",
        "(let* ((n 1) (v (+ n 1))) (add-tick v))",
        7,
        ["5"],
        [],
    ),
    "effect-between-definition-and-use": (
        "Int",
        "(let* ((b 1) (v (+ b 1)) (r (tick 7))) (let* ((b (tick 5))) v))",
        2,
        ["7", "5"],
        [],
    ),
    "effect-result-read-by-the-binding": (
        "Int",
        "(let* ((b (tick 1)) (v (+ b 1))) (let* ((b (tick 5))) v))",
        2,
        ["1", "5"],
        [],
    ),
}

# Each shape: (returns, body, lexical value). Caller bindings shadow the callee's parameter names, including through nested calls.
DEFUN_SHAPES = {
    "one-shadowed-parameter": ("Int", "(let* ((x 9)) (select-second 2 x))", 9),
    "two-shadowed-parameters": ("Pair", "(let* ((x 9) (y 7)) (last-two 2 x y))", (9, 7)),
    "two-crossed-parameters": ("Pair", "(let* ((x 9) (y 7)) (crossed y x))", (7, 9)),
    "nested-defun-call-argument": ("Int", "(let* ((x 9)) (select-second 2 (select-second 3 x)))", 9),
    "pure-binding-argument": ("Int", "(let* ((x 9) (w (+ x 1))) (select-second 2 w))", 10),
}


@pytest.mark.parametrize("shape", list(USE_SITE_SHAPES))
def test_a_pure_binding_reads_the_scope_of_its_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    returns, body, value, ticks, chooses = USE_SITE_SHAPES[shape]

    assert _outcome(tmp_path, monkeypatch, body, returns=returns) == (
        0,
        _outputs(returns, value),
        ticks,
        chooses,
    )


@pytest.mark.parametrize("shape", list(DEFUN_SHAPES))
def test_a_defun_argument_is_evaluated_in_the_caller_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    returns, body, value = DEFUN_SHAPES[shape]

    assert _outcome(tmp_path, monkeypatch, body, returns=returns) == (0, _outputs(returns, value), [], [])


BINDS_2 = "(bind-proc (proc-ref add-leading) :leading 2)"
# Each shape: (body, lexical value, tick log).
SPECIALIZATION_SHAPES = {
    "bound-value-and-a-caller-name": (
        f"(let* ((leading 9) (v (+ leading 1)) (hook {BINDS_2})) (hook v))",
        12,
        [],
    ),
    "bound-value-that-reads-its-own-name": (
        "(let* ((leading 9) (hook (bind-proc (proc-ref add-leading) :leading (+ leading 1)))) (hook 5))",
        15,
        [],
    ),
    "bound-value-and-a-body-rebinding": (
        "(let* ((leading 9) (v (+ leading 1)) (hook (bind-proc (proc-ref rebind-leading) :leading 2))) (hook v))",
        110,
        [],
    ),
    "bound-value-and-an-effect-in-the-body": (
        "(let* ((b 1) (v (+ b 1)) (hook (bind-proc (proc-ref add-leading-tick) :leading 2))) (hook v))",
        9,
        ["5"],
    ),
    "bound-procedure-reference-named-like-a-caller-name": (
        "(let* ((hook 1) (v (+ hook 1)) (twice (bind-proc (proc-ref apply-int) :hook (proc-ref add-one)))) (twice v))",
        3,
        [],
    ),
    "captured-value-and-a-parameter": (
        "(let* ((b 1) (v (+ b 1))) (let-proc (f ((b Int)) -> Int :captures (v) v) (apply-int (proc-ref f) 5)))",
        2,
        [],
    ),
    "captured-value-and-an-applying-procedure-parameter": (
        "(let* ((b 1) (v (+ b 1))) (let-proc (f ((x Int)) -> Int :captures (v) v) (apply-int-to-b (proc-ref f) 5)))",
        2,
        [],
    ),
    "captured-value-and-a-body-rebinding": (
        "(let* ((b 1) (v (+ b 1))) (let-proc (f ((x Int)) -> Int :captures (v) (let* ((b 7)) (+ v x))) (apply-int (proc-ref f) 5)))",
        7,
        [],
    ),
}


@pytest.mark.parametrize("shape", list(SPECIALIZATION_SHAPES))
def test_a_specialization_value_reads_the_scope_of_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    body, value, ticks = SPECIALIZATION_SHAPES[shape]

    assert _outcome(tmp_path, monkeypatch, body, returns="Int") == (0, {"__result__": value}, ticks, [])


def test_a_bound_value_keeps_its_scope_across_a_later_binder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "(let* ((b 1) (hook (bind-proc (proc-ref add-leading) :leading (+ b 1)))) (let* ((b 7)) (hook 5)))"

    assert _outcome(tmp_path, monkeypatch, body, returns="Int") == (0, {"__result__": 7}, [], [])


PURE_CAPTURE_PROCS = """  (defproc add ((fixed Int) (n Int)) -> Int
    :effects () :lowering inline (+ fixed n))"""


def test_unused_letproc_does_not_steal_a_body_created_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = """(let-proc (local ((n Int)) -> Int :captures (a) (+ a n))
      (let* ((b a) (hook (bind-proc (proc-ref add) :fixed b)))
        (let* ((b 100)) (hook 1))))"""

    assert _outcome(
        tmp_path, monkeypatch, body, returns="Int",
        declarations=PURE_CAPTURE_PROCS, workflow_params="((a Int))", inputs={"a": 7},
    ) == (0, {"__result__": 8}, [], [])


@pytest.mark.parametrize(
    "call",
    (
        "(invoke_first (bind-proc (proc-ref add) :fixed a) a)",
        "(invoke a (bind-proc (proc-ref add) :fixed a))",
    ),
    ids=("static-argument-first", "static-argument-last"),
)
def test_generic_letproc_static_argument_keeps_its_creation_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, call: str
) -> None:
    declarations = PURE_CAPTURE_PROCS + """
  (defproc invoke :forall (T)
    ((a T) (hook ProcRef[Int -> Int])) -> Int
    :effects () :lowering inline (let* ((a 100)) (hook 1)))
  (defproc invoke_first :forall (T)
    ((hook ProcRef[Int -> Int]) (a T)) -> Int
    :effects () :lowering inline (let* ((a 100)) (hook 1)) )"""
    body = f"""(let-proc (local ((n Int)) -> Int :captures (a) (+ a n))
      {call})"""

    assert _outcome(
        tmp_path, monkeypatch, body, returns="Int",
        declarations=declarations, workflow_params="((a Int))", inputs={"a": 7},
    ) == (0, {"__result__": 8}, [], [])


def test_match_arm_bound_capture_survives_shadow_and_runs_scrutinee_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    declarations = PURE_CAPTURE_PROCS + "\n  (defrecord Payload (value Int))"
    body = """(match (choose 100)
      ((YES a)
        (let* ((hook (bind-proc (proc-ref add) :fixed a.v)))
          (let* ((a (record Payload :value 200)))
            (hook 1))))
      ((NO other) 42))"""

    assert _outcome(
        tmp_path, monkeypatch, body, returns="Int",
        declarations=declarations, workflow_params="((a Int))", inputs={"a": 7},
    ) == (0, {"__result__": 101}, [], ["100"])


@pytest.mark.parametrize(
    ("body", "expected"),
    (
        (
            """(let* ((state (record Payload :value a))
                       (hook (bind-proc (proc-ref add) :fixed state.value)))
                 (loop/recur :max 1 :state (loop-state (value Int 100))
                   :on-exhausted 42 (fn (state) (done (hook 1)))))""",
            8,
        ),
        (
            """(loop/recur :max 2 :state (record Payload :value a) :on-exhausted 42
                 (fn (state)
                   (let* ((hook (bind-proc (proc-ref add) :fixed state.value)))
                     (if (< state.value 10)
                       (continue (record Payload :value 20))
                       (let* ((state (record Payload :value 100))) (done (hook 1)))))))""",
            21,
        ),
        (
            """(loop/recur :max 1 :state (record Payload :value a) :on-exhausted 42
                 (fn (state)
                   (let* ((hook (bind-proc (proc-ref add) :fixed state.value)))
                     (let* ((state (record Payload :value 200))) (done (hook 1))))))""",
            8,
        ),
    ),
    ids=(
        "outer-capture-crosses-loop",
        "capture-is-scoped-to-second-iteration",
        "inner-loop-capture-uses-current-target-creation-state",
    ),
)
def test_loop_capture_uses_the_intended_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str, expected: int
) -> None:
    declarations = PURE_CAPTURE_PROCS + "\n  (defrecord Payload (value Int))"
    assert _outcome(
        tmp_path, monkeypatch, body, returns="Int",
        declarations=declarations, workflow_params="((a Int))", inputs={"a": 7},
    ) == (0, {"__result__": expected}, [], [])


def test_a_captured_effect_result_runs_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = "(let* ((v (tick 1))) (let-proc (f ((x Int)) -> Int :captures (v) v) (apply-int (proc-ref f) 5)))"

    assert _outcome(tmp_path, monkeypatch, body, returns="Int") == (0, {"__result__": 1}, ["1"], [])


LIVE_PROVIDERS = """(let* ((worker 1) (v (+ worker 1)))
      (with-live-providers
        ((worker (provider-result providers.worker :prompt prompts.worker :inputs () :timeout-sec 30 :returns String))
         (supervisor (provider-result providers.supervisor :prompt prompts.supervisor :inputs ()
                       :timeout-sec 30 :returns ProviderSteeringDirective) :observes worker))
        v))"""


def test_live_provider_scope_is_refused_before_any_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    probes = {name: _write_probe(tmp_path, name, text) for name, text in PROBES.items()}
    source = MODULE.replace("RETURNS", "Int").replace("BODY", LIVE_PROVIDERS)
    for name, path in probes.items():
        source = source.replace(name.upper(), path.as_posix())
    _write_sources(tmp_path, {"grt/entry.orc": source})
    (tmp_path / "grt" / "prompt.md").write_text("review\n", encoding="utf-8")
    files = _scope_files(tmp_path, probes)
    providers = {"providers.worker": "codex", "providers.supervisor": "supervisor-provider"}
    files["providers"].write_text(json.dumps(providers), encoding="utf-8")
    files["prompts"].write_text(json.dumps({f"prompts.{name}": "prompt.md" for name in ("worker", "supervisor")}), encoding="utf-8")
    monkeypatch.setattr(ProviderExecutor, "execute", lambda *_args, **_kwargs: pytest.fail("provider effect ran before refusal"))
    monkeypatch.chdir(tmp_path)
    result = public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (2, {})
    assert "[closed_program_gap]" in caplog.text
    assert _log(probes["tick"]) == _log(probes["choose"]) == []
