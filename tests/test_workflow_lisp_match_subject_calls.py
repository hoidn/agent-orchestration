"""A procedure call written directly as a `match` subject.

A subject that calls a generic helper through a hook whose type uses a type
parameter is carried in its typechecked form, so the helper is specialized like
the same call bound with `let*`. Other subjects keep their authored identity.

The behavior tests use the public run entry. Hooks are command-backed probes
that append their argv to `<probe>.log`; the arms call `probe_summarize`, so each
run's command log ends with the selected arm.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.workflow_evaluated_totality_helpers import _log, _public_run_files, _write_probe, _write_sources
from tests.workflow_evaluated_totality_helpers import _public_run
from tests.test_workflow_lisp_generic_unions_runtime import _compile
from tests.workflow_lisp_generic_union_runtime_sources import CANDIDATE_CHECK, OUTCOME_LIB, OUTCOME_PROBE
from tests.workflow_lisp_improve_stdlib_sources import REVIEW_PROBE, REVISE_PROBE, SUMMARIZE_PROBE, entry_source
from tests.source_edits import replace_exact


HEADER = '(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "2.40")\n'

SUMMARIZE = """  (defrecord Summary (outcome String) (title String) (score Int))
  (defproc summarize ((outcome String) (candidate Candidate)) -> Summary
    (command-result probe_summarize
      :argv ("python" "PROBE_SUMMARIZE" outcome candidate.title candidate.score)
      :returns Summary))
"""
# The `improve` callers are the five-argument `std/improve` entry at 2.35 (Task 4a), where a
# procedure declares its exact effects.
SUMMARIZE_235 = replace_exact(
    SUMMARIZE,
    "-> Summary\n    (command-result",
    "-> Summary\n    :effects ((uses-command probe_summarize))\n    :lowering inline\n    (command-result",
)

IMPROVE_CALL = (
    '(improve (record Candidate :title "SEED" :score 0) (record Brief :goal "tidy")'
    " (proc-ref review-candidate) (proc-ref revise-candidate) 2)"
)
IMPROVE_ARMS = (
    '((APPROVED approved) (summarize "APPROVED" approved.value))'
    ' ((BLOCKED blocked) (summarize "BLOCKED" blocked.value))'
    ' ((EXHAUSTED exhausted) (summarize "EXHAUSTED" exhausted.value))'
)

CHECK_ARMS = '((OK ok) (summarize "OK" ok.value)) ((ERROR err) (summarize err.error (record Candidate :title "none" :score 0)))'

# `Checked` has the shape of `Outcome[Candidate String]`, so `OUTCOME_PROBE` answers for both.
CHECKED = "  (defunion Checked (OK (value Candidate)) (ERROR (error String)))\n"

# Helpers that take a `check` hook and return its union. `attempt` is generic over the
# imported `Outcome[T E]`; `judge` is generic over the plain union `Checked`; and
# `judge-concrete` is not generic.
CHECK_HELPERS = {
    "attempt": ("  (import grt/lib :only (Outcome attempt))\n", "", "attempt"),
    "judge": (
        "",
        CHECKED
        + "  (defproc judge :forall (S) ((subject S) (check ProcRef[(S) -> Checked])) :where ((S is-record))\n"
        + "    -> Checked (check subject))\n",
        "judge",
    ),
    "judge-concrete": (
        "",
        CHECKED
        + "  (defproc judge ((subject Candidate) (check ProcRef[(Candidate) -> Checked])) -> Checked\n"
        + "    (check subject))\n",
        "judge",
    ),
}


def _run_body(call: str, arms: str, *, bound: bool) -> str:
    match = f"(match result {arms})" if bound else f"(match {call} {arms})"
    body = f"(let* ((result {call})) {match})" if bound else match
    return f"  (defworkflow run () -> Summary\n    {body}))\n"


def _improve_sources(probes: dict[str, Path], *, seed: str, bound: bool) -> dict[str, str]:
    entry = entry_source(seed=seed, limit=2, probes=probes)
    prefix = entry[: entry.index("  (defworkflow run")]
    call = replace_exact(IMPROVE_CALL, "SEED", seed)
    summarize = replace_exact(SUMMARIZE_235, "PROBE_SUMMARIZE", probes["probe_summarize"].as_posix())
    return {"grt/entry.orc": prefix + summarize + _run_body(call, IMPROVE_ARMS, bound=bound)}


def _check_sources(
    probes: dict[str, Path], *, helper: str, seed: str, bound: bool
) -> dict[str, str]:
    imports, declarations, callee = CHECK_HELPERS[helper]
    check = replace_exact(CANDIDATE_CHECK, "PROBE_CHECK", probes["probe_check"].as_posix())
    if helper != "attempt":
        check = replace_exact(check, "Outcome[Candidate String]", "Checked", count=2)
    entry = (
        HEADER
        + "  (defmodule grt/entry)\n"
        + imports
        + "  (export run)\n"
        + check
        + declarations
        + replace_exact(SUMMARIZE, "PROBE_SUMMARIZE", probes["probe_summarize"].as_posix())
        + _run_body(f'({callee} (record Candidate :title "{seed}" :score 0) (proc-ref check-candidate))', CHECK_ARMS, bound=bound)
    )
    return {"grt/lib.orc": OUTCOME_LIB, "grt/entry.orc": entry} if helper == "attempt" else {"grt/entry.orc": entry}


IMPROVE_PROBES = (("probe_review", REVIEW_PROBE), ("probe_revise", REVISE_PROBE), ("probe_summarize", SUMMARIZE_PROBE))
CHECK_PROBES = (("probe_check", OUTCOME_PROBE), ("probe_summarize", SUMMARIZE_PROBE))


def _probes(root: Path, texts: tuple[tuple[str, str], ...]) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    return {name: _write_probe(root, name, text) for name, text in texts}


def _public_outcome(monkeypatch: pytest.MonkeyPatch, root: Path, probes: dict[str, Path], sources: dict[str, str]):
    """Run through the public entry; return the exit code, the outputs and each probe's ordered log."""

    _write_sources(root, sources)
    _compile(root, probes=probes)
    monkeypatch.chdir(root)
    result = _public_run(_public_run_files(root, probes))
    return result.exit_code, dict(result.workflow_outputs), {name: _log(path) for name, path in probes.items()}


def _direct_and_bound(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, texts, make_sources):
    outcomes = []
    for form in ("direct", "bound"):
        probes = _probes(tmp_path / form, texts)
        outcomes.append(_public_outcome(monkeypatch, tmp_path / form, probes, make_sources(probes, form == "bound")))
    return tuple(outcomes)


@pytest.mark.parametrize(
    ("seed", "variant"),
    [("approve", "APPROVED"), ("block", "BLOCKED"), ("draft", "EXHAUSTED")],
)
def test_improve_call_as_match_subject_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: str, variant: str
) -> None:
    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        IMPROVE_PROBES,
        lambda probes, is_bound: _improve_sources(probes, seed=seed, bound=is_bound),
    )

    assert (direct, direct[1].get("outcome")) == (bound, variant)


@pytest.mark.parametrize(("seed", "variant"), [("revise-x", "OK"), ("plain", "revise-plain")])
def test_second_generic_helper_over_another_generic_union_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: str, variant: str
) -> None:
    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        CHECK_PROBES,
        lambda probes, is_bound: _check_sources(probes, helper="attempt", seed=seed, bound=is_bound),
    )

    assert (direct, direct[1].get("outcome")) == (bound, variant)


def test_generic_helper_over_a_plain_union_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        CHECK_PROBES,
        lambda probes, is_bound: _check_sources(probes, helper="judge", seed="revise-x", bound=is_bound),
    )

    assert (direct, direct[1].get("outcome")) == (bound, "OK")


@pytest.mark.parametrize(("seed", "variant"), [("revise-x", "OK"), ("plain", "revise-plain")])
def test_non_generic_helper_with_a_hook_as_match_subject_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: str, variant: str
) -> None:
    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        CHECK_PROBES,
        lambda probes, is_bound: _check_sources(
            probes, helper="judge-concrete", seed=seed, bound=is_bound
        ),
    )

    assert (direct, direct[1].get("outcome")) == (bound, variant)


# Generic helpers, directly and bound with `let*`: one
# without a hook, which runs a command, and one whose hook type does not use its type
# parameter. The direct form names the authored helper; the bound form names its
# specialization.
COMPATIBLE_HELPERS = {
    "inspect": (
        "  (defproc inspect :forall (S) ((subject S)) :where ((S is-record)) -> Checked\n"
        '    (command-result probe_check :argv ("python" "PROBE_CHECK" "revise-x") :returns Checked))\n',
        '(inspect (record Candidate :title "revise-x" :score 0))',
    ),
    "judge-fixed": (
        "  (defproc judge-fixed :forall (S) ((subject S) (check ProcRef[(Candidate) -> Checked]))\n"
        "    :where ((S is-record)) -> Checked\n"
        '    (check (record Candidate :title "revise-x" :score 0)))\n',
        '(judge-fixed (record Candidate :title "revise-x" :score 0) (proc-ref check-candidate))',
    ),
}


def _compatible_sources(probes: dict[str, Path], *, helper: str, bound: bool) -> dict[str, str]:
    declaration, call = COMPATIBLE_HELPERS[helper]
    entry = (
        HEADER
        + "  (defmodule grt/entry)\n  (export run)\n"
        + replace_exact(CANDIDATE_CHECK, "Outcome[Candidate String]", "Checked", count=2)
        + CHECKED
        + declaration
        + SUMMARIZE
        + _run_body(call, CHECK_ARMS, bound=bound)
    )
    return {
        "grt/entry.orc": replace_exact(
            # once in `check-candidate`, and again in a helper that runs the probe itself
            replace_exact(entry, "PROBE_CHECK", probes["probe_check"].as_posix(), count=1 + declaration.count("PROBE_CHECK")),
            "PROBE_SUMMARIZE", probes["probe_summarize"].as_posix()
        )
    }


@pytest.mark.parametrize("helper", sorted(COMPATIBLE_HELPERS))
def test_generic_helper_as_match_subject_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, helper: str
) -> None:
    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        CHECK_PROBES,
        lambda probes, is_bound: _compatible_sources(probes, helper=helper, bound=is_bound),
    )

    assert (direct, direct[1].get("outcome")) == (bound, "OK")


# A field read on the subject of a `match` inside its arm (frontend specification §11: a match refines its
# exact selector).
from tests.workflow_lisp_cli_run_helpers import A_3, U, run_workflow  # noqa: E402


@pytest.mark.parametrize(("run", "inputs", "wanted"), [
    ("((u U)) -> Int (match u ((A a) u.n) ((B b) 0))", (f"u={A_3}",), (3, [])),
    ('((u U)) -> String (match u ((A a) "x") ((B b) u.why))', ('u={"variant":"B","why":"no"}',), ("no", [])),
    ("((u U)) -> Int (+ 1 (match u ((A a) u.n) ((B b) 0)))", (f"u={A_3}",), (4, [])),
    ("((u U)) -> Int (match u ((A a) (match u ((A a2) u.n) ((B b2) 1))) ((B b) 0))", (f"u={A_3}",), (3, [])),
    ('((u U)) -> Int (match u ((A a) (command-result c :argv ("python" "c.py" "argv" u.n) :returns Int)) ((B b) 0))',
     (f"u={A_3}",), (3, ["argv"])),
    ('() -> Int (let* ((u (command-result c :argv ("python" "c.py" "make" "{\\"variant\\":\\"A\\",\\"n\\":4}") '
     ":returns U))) (match u ((A a) u.n) ((B b) 0)))", (), (4, ["make"])),
], ids=["arm-value", "other-arm", "operand", "nested-match", "command-argv", "effect-result-subject"])
def test_field_read_on_the_subject_inside_its_arm(tmp_path, run, inputs, wanted):
    assert run_workflow(tmp_path, run, *inputs) == wanted


def test_a_subject_rebound_inside_its_arm_is_read_as_the_new_binding(tmp_path):
    run = ("((u U)) -> Int (match u ((A a) (let* ((u (variant U A :n 9))) (if (= u.variant A) u.n 0))) "
           "((B b) 0))")

    assert run_workflow(tmp_path, run, f"u={A_3}") == (9, [])


SHAPE = "(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))"
MKSHAPE = "(defproc mkshape ((r Int)) -> Shape (variant Shape CIRCLE :r r))"
E1_OR_E2 = ('(if (> n 0) (command-result c :argv ("python" "c.py" "e1" "1") :returns Int) '
            '(command-result c :argv ("python" "c.py" "e2" "2") :returns Int))')
SHAPE_ARMS = "((CIRCLE c) c.r) ((SQUARE s) 0)"


@pytest.mark.parametrize(("subject", "n", "wanted"), [
    (f"(mkshape {E1_OR_E2})", 1, (1, ["e1"])),
    (f"(mkshape {E1_OR_E2})", 0, (2, ["e2"])),
    (f"(let* ((r {E1_OR_E2})) (variant Shape CIRCLE :r r))", 0, (2, ["e2"])),
], ids=["call-then", "call-else", "let-subject"])
def test_subject_whose_binding_holds_a_conditional_effect_runs_it_once(tmp_path, subject, n, wanted):
    """A pure procedure call with an effectful `if` argument, or a `let*` binding such an `if`, as the subject:
    it runs as the subject bound with `let*` first does."""
    run = f"((n Int)) -> Int (match {subject} {SHAPE_ARMS})"

    assert run_workflow(tmp_path, run, f"n={n}", definitions=(SHAPE, MKSHAPE)) == wanted


def test_subject_bound_first_with_a_conditional_effect_argument_runs_it_once(tmp_path):
    run = f"((n Int)) -> Int (let* ((shape (mkshape {E1_OR_E2}))) (match shape {SHAPE_ARMS}))"

    assert run_workflow(tmp_path, run, "n=0", definitions=(SHAPE, MKSHAPE)) == (2, ["e2"])


E1 = '(command-result c :argv ("python" "c.py" "e1" "1") :returns Int)'
E2 = '(command-result c :argv ("python" "c.py" "e2" "2") :returns Int)'
SUBJECT_ARGUMENTS = {
    "cond": f"(cond ((> n 5) {E1}) ((> n 0) {E2}) (else 0))",
    "plus-match": f"(+ {E1} (match (variant U A :n n) ((A a) a.n) ((B b) 0)))",
    "match-arm": f"(match (variant U A :n n) ((A a) {E1}) ((B b) 0))",
    "loop": f"(loop/recur ((s 0)) :max 2 :on-exhausted s (if (> s 0) (done s) (continue {E1})))",
    "let-if": f"(let* ((q (if (> n 0) {E1} 2))) q)",
}


@pytest.mark.parametrize("spelling", ["call", "let", "nested-let", "cond-subject"])
@pytest.mark.parametrize("argument", SUBJECT_ARGUMENTS)
def test_subject_with_an_effectful_argument_runs_like_its_let_bound_spelling(tmp_path, argument, spelling):
    x = SUBJECT_ARGUMENTS[argument]
    subject = {
        "call": f"(mkshape {x})",
        "let": f"(let* ((r {x})) (variant Shape CIRCLE :r r))",
        "nested-let": f"(let* ((r (let* ((q {x})) q))) (variant Shape CIRCLE :r r))",
        "cond-subject": f"(cond ((> n 5) (variant Shape SQUARE :side 1)) (else (mkshape {x})))",
    }[spelling]
    definitions = (U, SHAPE, MKSHAPE)
    (tmp_path / "direct").mkdir()
    (tmp_path / "bound").mkdir()

    direct = run_workflow(tmp_path / "direct", f"((n Int)) -> Int (match {subject} {SHAPE_ARMS})", "n=1",
                          definitions=definitions)
    bound = run_workflow(tmp_path / "bound", f"((n Int)) -> Int (let* ((shape {subject})) (match shape {SHAPE_ARMS}))",
                         "n=1", definitions=definitions)

    assert direct == bound
