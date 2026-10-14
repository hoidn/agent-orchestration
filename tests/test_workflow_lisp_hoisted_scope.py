"""Lexical scope across operands, control subjects and command payloads.

Historical header parameters cover typed frontend analysis; execution uses the
public evaluated 2.35 entry. Command probes and a fixed provider payload check
native values, capture and once-only execution independently of lowering names.

Plan: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md, Task 5.
"""

from __future__ import annotations

import json
import logging
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from tests.test_workflow_lisp_elaborated_prefixes import CAPTURE_PROBE, LOOP_MATCH, _run, _write_program
from tests.test_workflow_lisp_generic_union_provider_results import _Provider
from tests.workflow_evaluated_totality_helpers import _log, _public_run_files, _write_probe, _write_sources
from tests.workflow_evaluated_totality_helpers import public_run
from tests.test_workflow_lisp_elaborated_prefixes import _analyze_and_select_evaluated_entry, _scope_files
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
    "capture": CAPTURE_PROBE,
    "tick": _PROBE_PRELUDE + "payload = int(sys.argv[1])\n" + _PROBE_WRITE,
    "choose": _PROBE_PRELUDE + 'payload = {"variant": "YES", "v": int(sys.argv[1])}\n' + _PROBE_WRITE,
}


def _outcome(
    root: Path, monkeypatch: pytest.MonkeyPatch, body: str, *, returns: str = "Int", target: str = "2.35", view: bool = False
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
    files = _scope_files(root, probes)
    _analyze_and_select_evaluated_entry(root)
    result = public_run(files, input_file=input_file)
    return result.exit_code, dict(result.workflow_outputs or {}), _log(probes["tick"]), _log(probes["choose"])


# Each shape with the value lexical scope gives it and the oldest target that accepts
# the shape. The base commit returned the captured value at every target (see the
# task-5-fix2 report for both values).
OPERAND_SHAPES = {
    "let-binding-value": ("Int", "(let* ((b 1) (x (let* ((b (tick 10))) b))) b)", 1, "2.23"),
    "if-condition": ("Int", "(let* ((b 1)) (if (let* ((b (tick 10))) (= b 10)) b 0))", 1, "2.26"),
    "cond-condition": ("Int", "(let* ((b 1)) (cond ((let* ((b (tick 10))) (= b 10)) b) (else 0)))", 1, "2.26"),
    "pure-operator-right": ("Int", "(let* ((b 1)) (+ (let* ((b 10)) b) b))", 11, "2.23"),
    "pure-operator-left": ("Int", "(let* ((b 1)) (+ b (let* ((b 10)) b)))", 11, "2.23"),
    "pure-operator-effect": ("Int", "(let* ((b 1)) (+ (let* ((b (tick 10))) b) b))", 11, "2.23"),
    "record-later-field": ("Pair", "(let* ((b 1)) (record Pair :left (let* ((b 10)) b) :right b))", (10, 1), "2.23"),
    "record-earlier-field": ("Pair", "(let* ((b 1)) (record Pair :left b :right (let* ((b 10)) b)))", (1, 10), "2.23"),
    "record-sibling-fields": ("Pair", "(record Pair :left (let* ((b 10)) b) :right (let* ((b 20)) b))", (10, 20), "2.23"),
    # Lowering reads `v`'s free `x` where `v` is used, after the later field's binding.
    "record-field-rebinding-a-name-an-earlier-field-reads": (
        "Pair",
        "(let* ((x 9)) (record Pair :left (let* ((v (+ x 1))) (+ v v)) :right (let* ((x 2)) x)))",
        (20, 2),
        "2.23",
    ),
    "record-update-field": (
        "Pair",
        "(let* ((b 1) (p (record Pair :left 0 :right 0))) (record-update p :left (let* ((b 10)) b) :right b))",
        (10, 1),
        "2.23",
    ),
    "record-update-base": (
        "Pair",
        "(let* ((b 1)) (record-update (let* ((b 10)) (record Pair :left b :right b)) :right b))",
        (10, 1),
        "2.23",
    ),
    "union-field": ("Choice", "(let* ((b 1)) (variant Choice YES :v (+ (let* ((b 10)) b) b)))", 11, "2.32"),
    "effect-argument": ("Int", "(let* ((b 1) (r (tick (let* ((b 10)) b)))) b)", 1, "2.23"),
    "loop-budget": (
        "Int",
        "(let* ((b 1)) (loop/recur :max (let* ((b 2)) b) :state (loop-state (n Int 0)) :on-exhausted b"
        " (fn (state) (if (= state.n 5) (done state.n) (continue (loop-state :like state :n (+ state.n 1)))))))",
        1,
        "2.23",
    ),
}
_TICKS = {name: ["10"] for name in ("let-binding-value", "if-condition", "cond-condition", "pure-operator-effect", "effect-argument")}


def _outputs(returns: str, value) -> dict:
    if returns == "Pair":
        return {"left": value[0], "right": value[1]}
    if returns == "Choice":
        return {"variant": "YES", "v": value}
    return {"__result__": value}


@pytest.mark.parametrize(
    ("shape", "target"),
    [
        (shape, target)
        for shape, (_, _, _, oldest) in OPERAND_SHAPES.items()
        for target in dict.fromkeys((oldest, "2.32", "2.33"))
    ],
)
def test_a_hoisted_binding_keeps_its_source_scope_at_every_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, target: str
) -> None:
    returns, body, source_value, _ = OPERAND_SHAPES[shape]

    assert _outcome(tmp_path, monkeypatch, body, returns=returns, target=target) == (
        0,
        _outputs(returns, source_value),
        _TICKS.get(shape, []),
        [],
    )


VIEW = (
    '(command-result capture :argv ("python" "CAPTURE" target) :inputs ((value VALUE)) :returns String)'
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
        {"title": "draft+r+r+r", "score": 3},
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


def _prompt_outcome(root: Path, monkeypatch: pytest.MonkeyPatch, body: str, *, target: str = "2.35"):
    """Run with a stand-in `providers.pick`; return (exit code, outputs, provider calls, tick log)."""

    root.mkdir(parents=True, exist_ok=True)
    tick = _write_probe(root, "tick", PROBES["tick"])
    choose = _write_probe(root, "choose", PROBES["choose"])
    source = MODULE.replace("TARGET", target).replace("RETURNS", "Int").replace("BODY", body).replace("PARAMS", "")
    source = source.replace("TICK", tick.as_posix()).replace("CHOOSE", choose.as_posix())
    _write_sources(root, {"grt/entry.orc": source})
    files = _scope_files(root, {"tick": tick, "choose": choose})
    files["providers"].write_text(json.dumps({"providers.pick": "codex"}), encoding="utf-8")
    _analyze_and_select_evaluated_entry(root, provider_externs={"providers.pick": "codex"})
    provider = _Provider({"variant": "YES", "v": 7})
    with ExitStack() as stack:
        stack.enter_context(patch.object(ProviderExecutor, "prepare_invocation", provider.prepare_invocation))
        stack.enter_context(patch.object(ProviderExecutor, "execute", provider.execute))
        monkeypatch.chdir(root)
        result = public_run(files)
    return result.exit_code, dict(result.workflow_outputs or {}), provider.calls, _log(tick)


@pytest.mark.parametrize("form", list(PROMPT_FORMS))
def test_a_match_subject_that_applies_a_typed_prompt_runs_as_the_let_bound_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    assert _prompt_outcome(tmp_path, monkeypatch, PROMPT_FORMS[form]) == (0, {"__result__": 7}, 1, ["10"])


def test_target_232_prompt_analysis_remains_available_to_an_evaluated_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        outcome = _prompt_outcome(tmp_path, monkeypatch, PROMPT_FORMS["call-subject"], target="2.32")

    assert outcome == (0, {"__result__": 7}, 1, ["10"])


# A pure procedure that the resolved-inline normalizer copies into its caller is
# elaborated under the caller's target. The renaming runs at every target, so the
# copy gets the value lexical scope requires whichever target either module has.
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


@pytest.mark.parametrize(
    ("entry_target", "lib_target"),
    [("2.32", "2.33"), ("2.33", "2.32"), ("2.23", "2.33")],
    ids=["2.32-caller-of-a-2.33-procedure", "2.33-caller-of-a-2.32-procedure", "2.23-caller-of-a-2.33-procedure"],
)
def test_a_copied_pure_procedure_gets_the_source_value_whatever_the_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry_target: str, lib_target: str
) -> None:
    _write_sources(
        tmp_path,
        {
            "grt/lib.orc": LIB.replace("LIB_TARGET", lib_target),
            "grt/entry.orc": ENTRY.replace("ENTRY_TARGET", entry_target),
        },
    )
    monkeypatch.chdir(tmp_path)
    files = _scope_files(tmp_path, {})
    _analyze_and_select_evaluated_entry(tmp_path)
    result = public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (0, {"__result__": 11})
