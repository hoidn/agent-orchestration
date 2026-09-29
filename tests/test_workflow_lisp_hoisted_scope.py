"""Shared defect repairs, Task 5 second review fixes: every hoisted binding keeps its source scope.

Plan: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md, Task 5.
Design: docs/design/workflow_lisp_core_calculus_middle_end.md section 9 (a
reference is valid only where its definition dominates it).

From target 2.33 the elaborator renames a binding it hoists out of a sub-expression
when the code it is hoisted over refers to that name: the rest of a `let*`, the arms
of a `match`, the other operands of a pure operator, record, record update or union
constructor, the later arguments and the continuation of an effect call, and the body
of a loop whose `:max` binds names. The renaming follows binding structure: a binder
of the same spelling inside the renamed code starts a scope the renaming does not
enter. Below 2.33 the captured value of the base commit is kept.

A `match` subject that applies a typed prompt keeps its typechecked form from 2.33,
so the application reaches lowering with its compiled identity.

Effects are command probes (`tick`, `choose`) that append their argv to `<probe>.log`,
and, for prompts, a stand-in provider executor that writes a fixed payload.
"""

from __future__ import annotations

import json
import logging
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from tests.test_workflow_lisp_elaborated_prefixes import LOOP_MATCH, _run, _write_program
from tests.test_workflow_lisp_generic_union_provider_results import _Provider
from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.workflow_lisp_improve_stdlib_sources import _PROBE_PRELUDE, _PROBE_WRITE


MODULE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defpath OutPath :kind relpath :under "artifacts/work" :must-exist false)
  (defrecord Pair (left Int) (right Int))
  (defunion Choice (YES (v Int)) (NO (v Int)))
  (defprompt ask (:fills (v :value Int)) -> Choice "Pick for {v}.")
  (defproc tick ((v Int)) -> Int
    :effects ((uses-command tick))
    :lowering inline
    (command-result tick :argv ("python" "TICK" v) :returns Int))
  (defproc choose ((v Int)) -> Choice
    :effects ((uses-command choose))
    :lowering inline
    (command-result choose :argv ("python" "CHOOSE" v) :returns Choice))
  (defworkflow run (PARAMS) -> RETURNS
    BODY))
"""

PROBES = {
    "tick": _PROBE_PRELUDE + "payload = int(sys.argv[1])\n" + _PROBE_WRITE,
    "choose": _PROBE_PRELUDE + 'payload = {"variant": "YES", "v": int(sys.argv[1])}\n' + _PROBE_WRITE,
}


def _outcome(
    root: Path, monkeypatch: pytest.MonkeyPatch, body: str, *, returns: str = "Int", target: str = "2.33", view: bool = False
):
    """Run `body` through `run_workflow`; return (exit code, outputs, tick log, choose log)."""

    root.mkdir(parents=True, exist_ok=True)
    probes = {name: _write_probe(root, name, text) for name, text in PROBES.items()}
    source = MODULE.replace("TARGET", target).replace("RETURNS", returns).replace("BODY", body)
    source = source.replace("PARAMS", "(target OutPath)" if view else "")
    for name, path in probes.items():
        source = source.replace(name.upper(), path.as_posix())
    _write_sources(root, {"grt/entry.orc": source})
    input_file = None
    if view:
        input_file = root / "inputs.json"
        input_file.write_text(json.dumps({"target": "artifacts/work/view.json"}), encoding="utf-8")
    monkeypatch.chdir(root)
    result = _public_run(_public_run_files(root, probes), input_file=input_file)
    return result.exit_code, dict(result.workflow_outputs or {}), _log(probes["tick"]), _log(probes["choose"])


# The source value of each shape is the value lexical scope gives it; the base commit
# gave the captured value, which target 2.32 keeps.
OPERAND_SHAPES = {
    "let-binding-value": ("Int", "(let* ((b 1) (x (let* ((b (tick 10))) b))) b)", 1, 10),
    "pure-operator-right": ("Int", "(let* ((b 1)) (+ (let* ((b 10)) b) b))", 11, 20),
    "pure-operator-left": ("Int", "(let* ((b 1)) (+ b (let* ((b 10)) b)))", 11, 20),
    "pure-operator-effect": ("Int", "(let* ((b 1)) (+ (let* ((b (tick 10))) b) b))", 11, 20),
    "record-later-field": ("Pair", "(let* ((b 1)) (record Pair :left (let* ((b 10)) b) :right b))", (10, 1), (10, 10)),
    "record-earlier-field": ("Pair", "(let* ((b 1)) (record Pair :left b :right (let* ((b 10)) b)))", (1, 10), (10, 10)),
    "record-sibling-fields": ("Pair", "(record Pair :left (let* ((b 10)) b) :right (let* ((b 20)) b))", (10, 20), (20, 20)),
    "record-update-field": (
        "Pair",
        "(let* ((b 1) (p (record Pair :left 0 :right 0))) (record-update p :left (let* ((b 10)) b) :right b))",
        (10, 1),
        (10, 10),
    ),
    "record-update-base": (
        "Pair",
        "(let* ((b 1)) (record-update (let* ((b 10)) (record Pair :left b :right b)) :right b))",
        (10, 1),
        (10, 10),
    ),
    "union-field": ("Choice", "(let* ((b 1)) (variant Choice YES :v (+ (let* ((b 10)) b) b)))", 11, 20),
    "effect-argument": ("Int", "(let* ((b 1) (r (tick (let* ((b 10)) b)))) b)", 1, 10),
    "loop-budget": (
        "Int",
        "(let* ((b 1)) (loop/recur :max (let* ((b 2)) b) :state (loop-state (n Int 0)) :on-exhausted b"
        " (fn (state) (if (= state.n 5) (done state.n) (continue (loop-state :like state :n (+ state.n 1)))))))",
        1,
        2,
    ),
}
_TICKS = {"let-binding-value": ["10"], "pure-operator-effect": ["10"], "effect-argument": ["10"]}


def _outputs(returns: str, value) -> dict:
    if returns == "Pair":
        return {"return__left": value[0], "return__right": value[1]}
    if returns == "Choice":
        return {"return__variant": "YES", "return__v": value}
    return {"__result__": value}


@pytest.mark.parametrize("shape", list(OPERAND_SHAPES))
def test_a_hoisted_binding_keeps_its_source_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str) -> None:
    returns, body, source_value, _ = OPERAND_SHAPES[shape]

    assert _outcome(tmp_path, monkeypatch, body, returns=returns) == (0, _outputs(returns, source_value), _TICKS.get(shape, []), [])


@pytest.mark.parametrize("shape", ["let-binding-value", "pure-operator-right"])
def test_target_232_keeps_the_captured_value_of_the_base_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    returns, body, _, base_value = OPERAND_SHAPES[shape]

    assert _outcome(tmp_path, monkeypatch, body, returns=returns, target="2.32") == (
        0,
        _outputs(returns, base_value),
        _TICKS.get(shape, []),
        [],
    )


VIEW = (
    "(materialize-view audit-view :value VALUE :renderer canonical-json :renderer-version 1"
    " :target target :returns OutPath)"
)


def _subject(*bindings: str, arms: str = "((YES x) b) ((NO x) b)") -> str:
    """A `match` whose subject binds `b` (renamed: the arms read the outer `b`)."""

    return f"(let* ((b 1)) (match (let* ((b (tick 10)) {' '.join(bindings)}) d) {arms}))"


# Each form rebinds `b` inside the code the renaming walks, or binds it in an arm.
REBINDING_FORMS = {
    "let-inside-an-effect-payload": (
        _subject(f"(v {VIEW.replace('VALUE', '(let* ((b 20)) b)')})", "(d (choose b))"),
        (0, {"__result__": 1}, ["10"], ["10"]),
        20,
    ),
    "later-let-binding-inside-an-effect-payload": (
        _subject(f"(v {VIEW.replace('VALUE', '(let* ((c b) (b 20)) (record Pair :left b :right c))')})", "(d (choose b))"),
        (0, {"__result__": 1}, ["10"], ["10"]),
        {"left": 20, "right": 10},
    ),
    "later-let-binding-of-the-subject": (
        _subject("(c (let* ((b 20)) b))", "(d (choose c))"),
        (0, {"__result__": 1}, ["10"], ["20"]),
        None,
    ),
    "match-pattern-variable": (
        _subject("(d (choose b))", arms="((YES b) b.v) ((NO x) b)"),
        (0, {"__result__": 10}, ["10"], ["10"]),
        None,
    ),
}


@pytest.mark.parametrize("form", list(REBINDING_FORMS))
def test_the_renaming_stops_at_a_binder_of_the_same_spelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    body, expected, view = REBINDING_FORMS[form]
    outcome = _outcome(tmp_path, monkeypatch, body, view=view is not None)
    view_file = tmp_path / "artifacts" / "work" / "view.json"

    assert (outcome, json.loads(view_file.read_text(encoding="utf-8")) if view is not None else None) == (expected, view)


def test_a_subject_binding_named_like_the_loop_parameter_does_not_capture_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The subject binds `state`; the arms read the loop parameter `state`."""

    body = LOOP_MATCH.replace("(let* ((d (review state.current))) d)", "(let* ((state (review state.current))) state)")
    probes = _write_program(tmp_path, body=body, returns="Candidate", seed="draft")

    assert _run(tmp_path, monkeypatch, probes) == (
        0,
        {"return__title": "draft+r+r+r", "return__score": 3},
        (
            ["draft tidy", "draft+r tidy", "draft+r+r tidy"],
            ["draft tidy fb", "draft+r tidy fb", "draft+r+r tidy fb"],
            [],
        ),
    )


PROMPT_ARMS = "((YES x) x.v) ((NO x) x.v)"
PROMPT_FORMS = {
    "let-subject": f"(match (let* ((b (tick 10)) (d (provider-result providers.pick :prompt (ask :v b)))) d) {PROMPT_ARMS})",
    "call-subject": f"(let* ((b (tick 10))) (match (provider-result providers.pick :prompt (ask :v b)) {PROMPT_ARMS}))",
    "let-bound": f"(let* ((b (tick 10)) (d (provider-result providers.pick :prompt (ask :v b)))) (match d {PROMPT_ARMS}))",
}


def _prompt_outcome(root: Path, monkeypatch: pytest.MonkeyPatch, body: str, *, target: str = "2.33"):
    """Run with a stand-in `providers.pick`; return (exit code, outputs, provider calls, tick log)."""

    root.mkdir(parents=True, exist_ok=True)
    tick = _write_probe(root, "tick", PROBES["tick"])
    choose = _write_probe(root, "choose", PROBES["choose"])
    source = MODULE.replace("TARGET", target).replace("RETURNS", "Int").replace("BODY", body).replace("PARAMS", "")
    source = source.replace("TICK", tick.as_posix()).replace("CHOOSE", choose.as_posix())
    _write_sources(root, {"grt/entry.orc": source})
    files = _public_run_files(root, {"tick": tick, "choose": choose})
    files["providers"].write_text(json.dumps({"providers.pick": "codex"}), encoding="utf-8")
    provider = _Provider({"variant": "YES", "v": 7})
    with ExitStack() as stack:
        stack.enter_context(patch.object(ProviderExecutor, "prepare_invocation", provider.prepare_invocation))
        stack.enter_context(patch.object(ProviderExecutor, "execute", provider.execute))
        monkeypatch.chdir(root)
        result = _public_run(files)
    return result.exit_code, dict(result.workflow_outputs or {}), provider.calls, _log(tick)


@pytest.mark.parametrize("form", list(PROMPT_FORMS))
def test_a_match_subject_that_applies_a_typed_prompt_runs_as_the_let_bound_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    assert _prompt_outcome(tmp_path, monkeypatch, PROMPT_FORMS[form]) == (0, {"__result__": 7}, 1, ["10"])


def test_target_232_keeps_the_refusal_of_a_prompt_applied_in_a_match_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        outcome = _prompt_outcome(tmp_path, monkeypatch, PROMPT_FORMS["call-subject"], target="2.32")

    assert (outcome, "[compiled_prompt_fragment_identity_missing]" in caplog.text) == ((2, {}, 0, []), True)


# A pure procedure that the resolved-inline normalizer copies into its caller is
# elaborated under the caller's target, not under the target of its defining module.
LIB = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "LIB_TARGET")
  (defmodule grt/lib)
  (export shadow)
  (defproc shadow ((n Int)) -> Int :effects () :lowering inline
    (let* ((b n)) (+ (let* ((b 10)) b) b))))
"""
ENTRY = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "ENTRY_TARGET")
  (defmodule grt/entry)
  (import grt/lib :only (shadow))
  (export run)
  (defworkflow run () -> Int (shadow 1)))
"""


@pytest.mark.xfail(
    strict=True,
    reason=(
        "known defect: a pure procedure copied by the resolved-inline normalizer is elaborated "
        "under its caller's target, not its defining module's"
    ),
)
@pytest.mark.parametrize(
    ("entry_target", "lib_target", "value"),
    [("2.32", "2.33", 11), ("2.33", "2.32", 20)],
    ids=["2.32-caller-of-a-2.33-procedure", "2.33-caller-of-a-2.32-procedure"],
)
def test_a_copied_pure_procedure_follows_the_target_of_its_defining_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry_target: str, lib_target: str, value: int
) -> None:
    _write_sources(
        tmp_path,
        {
            "grt/lib.orc": LIB.replace("LIB_TARGET", lib_target),
            "grt/entry.orc": ENTRY.replace("ENTRY_TARGET", entry_target),
        },
    )
    monkeypatch.chdir(tmp_path)
    result = _public_run(_public_run_files(tmp_path, {}))

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (0, {"__result__": value})
