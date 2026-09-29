"""Shared defect repairs, Task 5 review fixes: hoisted bindings keep the source scope.

Plan: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md, Task 5.
Design: docs/design/workflow_lisp_core_calculus_middle_end.md section 9
(environments are scoped; a reference is valid only where its definition
dominates it) and section 13.3 (a failure after typecheck is a compiler defect).

The elaborator gives a binding that it hoists out of a `match` subject or out of a
`let*` binding value a fresh name when the code it is hoisted over refers to that
name, at every target (a correction of values; the `match` subject forms are
accepted from 2.33 only), and from 2.33 it names the bindings it generates for
effectful `loop-state` fields apart from every identifier in scope. Every direct form runs
as its hand-bound equivalent: same value, same ordered command log. The probes
and the program template are those of tests/test_workflow_lisp_elaborated_prefixes.py.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest

from tests.test_workflow_lisp_elaborated_prefixes import _logs, _run, _write_program
from tests.test_workflow_lisp_generic_unions_runtime import _public_run, _public_run_files
from tests.test_workflow_lisp_improve_stdlib import _resume, _run_until_the_first_committed_iteration


OUTER = '(record Candidate :title "outer" :score 7)'


def _match_on(subject: str, value: str) -> str:
    arms = " ".join(f'(({variant} x) (summarize "{variant}" {value}))' for variant in ("APPROVE", "REVISE", "BLOCKED"))
    return f"(match {subject} {arms})"


# The subject binds `note`; the arms read the `note` bound outside the `match`.
SCOPE_FORMS = {
    "match-subject-same-type": {
        "direct": f"(let* ((note {OUTER})) {_match_on('(let* ((note (revise SEED)) (d (review note))) d)', 'note.title')})",
        "let-bound": f"(let* ((note {OUTER}) (inner (revise SEED)) (d (review inner))) {_match_on('d', 'note.title')})",
    },
    "match-subject-other-type": {
        "direct": f"(let* ((note \"outer\")) {_match_on('(let* ((note (revise SEED)) (d (review note))) d)', 'note')})",
        "let-bound": f"(let* ((note \"outer\") (inner (revise SEED)) (d (review inner))) {_match_on('d', 'note')})",
    },
    # The strict boolean normalizer binds an `if` condition as one value, so its
    # bindings are hoisted like those of any `let*` binding value.
    "if-condition": {
        "direct": (
            f"(let* ((note {OUTER})) (if (let* ((note (revise SEED))) (= note.score 1))"
            ' (summarize "REVISE" note.title) (summarize "NO" note.title)))'
        ),
        "let-bound": (
            f"(let* ((note {OUTER}) (inner (revise SEED))) (if (= inner.score 1)"
            ' (summarize "REVISE" note.title) (summarize "NO" note.title)))'
        ),
    },
    "let-binding-value": {
        "direct": f"(let* ((note {OUTER}) (t (let* ((note (revise SEED))) note.score))) (summarize \"REVISE\" note.title))",
        "let-bound": f"(let* ((note {OUTER}) (inner (revise SEED)) (t inner.score)) (summarize \"REVISE\" note.title))",
    },
    # Each `match` subject has its own `let*`; every arm reads the outermost `d`.
    "nested-match-subjects": {
        "direct": (
            f"(let* ((d {OUTER})) (match (let* ((d (review SEED))) d)"
            ' ((APPROVE x) (summarize "APPROVE" d.title)) ((BLOCKED x) (summarize "BLOCKED" d.title))'
            f" ((REVISE x) {_match_on('(let* ((d (revise SEED)) (e (review d))) e)', 'd.title')})))"
        ),
        "let-bound": (
            f"(let* ((d {OUTER}) (d1 (review SEED))) (match d1"
            ' ((APPROVE x) (summarize "APPROVE" d.title)) ((BLOCKED x) (summarize "BLOCKED" d.title))'
            f" ((REVISE x) (let* ((d2 (revise SEED)) (e (review d2))) {_match_on('e', 'd.title')}))))"
        ),
    },
}

SCOPE_EXPECTED = {
    name: (0, {"return__outcome": "REVISE", "return__title": "outer", "return__score": 0}, (review, ["draft tidy fb"], ["REVISE outer 0"]))
    for name, review in (
        ("match-subject-same-type", ["draft+r tidy"]),
        ("match-subject-other-type", ["draft+r tidy"]),
        ("if-condition", []),
        ("let-binding-value", []),
        ("nested-match-subjects", ["draft tidy", "draft+r tidy"]),
    )
}


@pytest.mark.parametrize("form", ["direct", "let-bound"])
@pytest.mark.parametrize("shape", list(SCOPE_FORMS))
def test_a_hoisted_binding_does_not_capture_a_name_of_the_enclosing_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, form: str
) -> None:
    probes = _write_program(tmp_path, body=SCOPE_FORMS[shape][form], returns="Summary", seed="draft")

    assert _run(tmp_path, monkeypatch, probes) == SCOPE_EXPECTED[shape]


@pytest.mark.parametrize("target", ["2.26", "2.32"])
@pytest.mark.parametrize("shape", ["if-condition", "let-binding-value"])
def test_older_targets_give_a_hoisted_binding_its_source_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, target: str
) -> None:
    """The base commit returned the hoisted `note` (`draft+r`) here; the correction applies at every target."""

    probes = _write_program(tmp_path, body=SCOPE_FORMS[shape]["direct"], returns="Summary", seed="draft", target=target)

    assert _run(tmp_path, monkeypatch, probes) == SCOPE_EXPECTED[shape]


# A loop whose state keeps a record the workflow receives as input `ALT`.
COLLISION_LOOP = """(loop/recur :max 4
      :state (loop-state (current Candidate SEED) (other Candidate SEED))
      :on-exhausted state.other
      (fn (state)
        (if (= state.current.score 2) (done state.other) CONTINUE)))"""

COLLISION_CONTINUES = {
    "direct": "(continue (loop-state :like state :current (revise state.current) :other ALT))",
    "let-bound": "(let* ((next (revise state.current))) (continue (loop-state :like state :current next :other ALT)))",
}

_GENERATED_CURRENT = re.compile(r"__wcc_effect_current_[0-9a-f]{16}(?:_[0-9]+)?(?=__)")


def _generated_names(root: Path) -> set[str]:
    (lowered,) = (root / ".orchestrate" / "build").glob("*/lowered_workflows.json")
    return set(_GENERATED_CURRENT.findall(lowered.read_text(encoding="utf-8")))


def _run_with_inputs(
    root: Path, monkeypatch: pytest.MonkeyPatch, *, body: str, returns: str, params: str, inputs: dict, decls: str = ""
):
    """Run the template program with workflow parameters `params`, the given inputs and extra declarations."""

    probes = _write_program(root, body=body, returns=returns, seed="draft")
    source = root / "grt" / "entry.orc"
    text = source.read_text(encoding="utf-8").replace("(defworkflow run ()", f"{decls}(defworkflow run ({params})")
    source.write_text(text, encoding="utf-8")
    input_file = root / "inputs.json"
    input_file.write_text(json.dumps(inputs), encoding="utf-8")
    monkeypatch.chdir(root)
    result = _public_run(_public_run_files(root, probes), input_file=input_file)
    return result.exit_code, dict(result.workflow_outputs or {}), _logs(probes)


def _run_with_input(root: Path, monkeypatch: pytest.MonkeyPatch, form: str, name: str):
    return _run_with_inputs(
        root,
        monkeypatch,
        body=COLLISION_LOOP.replace("CONTINUE", COLLISION_CONTINUES[form]).replace("ALT", name),
        returns="Candidate",
        params=f"({name} Candidate)",
        inputs={f"{name}__title": "author", f"{name}__score": 5},
    )


def test_an_authored_identifier_spelled_like_a_generated_binding_is_not_captured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The input takes the exact spelling the generator gives the `current` binding of this program."""

    _run_with_input(tmp_path / "discover", monkeypatch, "direct", "alt")
    (generated,) = _generated_names(tmp_path / "discover")
    expected = (0, {"return__title": "author", "return__score": 5}, ([], ["draft tidy fb", "draft+r tidy fb"], []))

    assert [_run_with_input(tmp_path / form, monkeypatch, form, generated) for form in COLLISION_CONTINUES] == [
        expected,
        expected,
    ]


VIEW = (
    "(materialize-view note-view :value note :renderer canonical-json :renderer-version 1"
    " :target target :returns ViewPath)"
)
VIEW_FORMS = {
    "direct": f"(let* ((note {OUTER})) {_match_on(f'(let* ((note (revise SEED)) (p {VIEW}) (d (review note))) d)', 'note.title')})",
    "let-bound": (
        f"(let* ((note {OUTER}) (inner (revise SEED)) (p {VIEW.replace(':value note', ':value inner')}) (d (review inner)))"
        f" {_match_on('d', 'note.title')})"
    ),
}


@pytest.mark.parametrize("form", list(VIEW_FORMS))
def test_a_renamed_binding_is_renamed_inside_an_effect_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    """`materialize-view` keeps its arguments as a frontend expression inside the effect payload."""

    outcome = _run_with_inputs(
        tmp_path,
        monkeypatch,
        body=VIEW_FORMS[form],
        returns="Summary",
        params="(target ViewPath)",
        inputs={"target": "artifacts/work/view.json"},
        decls='(defpath ViewPath :kind relpath :under "artifacts/work" :must-exist false)\n  ',
    )
    view = json.loads((tmp_path / "artifacts" / "work" / "view.json").read_text(encoding="utf-8"))

    assert (outcome, view) == (SCOPE_EXPECTED["match-subject-same-type"], {"score": 1, "title": "draft+r"})


# Two arms of one `match` bind the same name and each `continue` with an effectful field.
TWO_ARMS = """(loop/recur :max 4
      :state (loop-state (current Candidate SEED) (other Candidate (record Candidate :title "other" :score 0)))
      :on-exhausted state.current
      (fn (state)
        (match (let* ((d (review state.current))) d)
          ((APPROVE a) (done state.current))
          ((BLOCKED a) BLOCKED_ARM)
          ((REVISE a) REVISE_ARM))))"""

TWO_ARMS_FORMS = {
    "direct": {
        "BLOCKED_ARM": "(continue (loop-state :like state :current (revise state.other)))",
        "REVISE_ARM": "(continue (loop-state :like state :current (revise state.current)))",
    },
    "let-bound": {
        "BLOCKED_ARM": "(let* ((n (revise state.other))) (continue (loop-state :like state :current n)))",
        "REVISE_ARM": "(let* ((n (revise state.current))) (continue (loop-state :like state :current n)))",
    },
}

TWO_ARMS_EXPECTED = (
    {"return__title": "other+r+r+r", "return__score": 3},
    (
        ["block tidy", "block+r tidy", "other+r tidy", "other+r+r tidy"],
        ["block tidy fb", "other tidy fb", "other+r tidy fb", "other+r+r tidy fb"],
        [],
    ),
)


def _two_arms(form: str) -> str:
    body = TWO_ARMS
    for placeholder, arm in TWO_ARMS_FORMS[form].items():
        body = body.replace(placeholder, arm)
    return body


@pytest.mark.parametrize("form", list(TWO_ARMS_FORMS))
def test_continue_in_two_arms_runs_as_the_let_bound_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    probes = _write_program(tmp_path, body=_two_arms(form), returns="Candidate", seed="block")

    assert _run(tmp_path, monkeypatch, probes) == (0, *TWO_ARMS_EXPECTED)


def test_continue_in_two_arms_binds_each_field_under_its_own_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = _write_program(tmp_path, body=_two_arms("direct"), returns="Candidate", seed="block")
    _run(tmp_path, monkeypatch, probes)

    assert len(_generated_names(tmp_path)) == 2


@pytest.mark.parametrize("form", list(TWO_ARMS_FORMS))
def test_resume_after_the_first_committed_iteration_runs_no_committed_command_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    probes = _write_program(tmp_path, body=_two_arms(form), returns="Candidate", seed="block")
    monkeypatch.chdir(tmp_path)

    run_id = _run_until_the_first_committed_iteration(monkeypatch, _public_run_files(tmp_path, probes))
    assert _logs(probes) == (["block tidy"], ["block tidy fb"], [])

    state = _resume(run_id)
    assert (state["status"], state["workflow_outputs"], _logs(probes)) == ("completed", *TWO_ARMS_EXPECTED)


# An effectful `if` or `match` whose value is bound in a loop body. The loop route
# cannot lower it (the hand-bound form fails as the direct one does).
BRANCH_LOOP = """(loop/recur :max 2
      :state (loop-state (current Candidate SEED) (other Candidate (record Candidate :title "other" :score 0)))
      :on-exhausted state.current
      (fn (state)
        (if (= state.current.score 2) (done state.current) CONTINUE)))"""

IF_VALUE = "(if (= state.current.score 0) (revise state.current) (revise state.other))"
MATCH_VALUE = (
    "(match (review state.current) ((APPROVE a) (revise state.current))"
    " ((REVISE a) (revise state.other)) ((BLOCKED a) state.current))"
)
BRANCH_FORMS = {
    "if-field": (f"(continue (loop-state :like state :current {IF_VALUE}))", IF_VALUE),
    "if-bound": (f"(let* ((next {IF_VALUE})) (continue (loop-state :like state :current next)))", IF_VALUE),
    "match-field": (f"(continue (loop-state :like state :current {MATCH_VALUE}))", MATCH_VALUE),
    "match-bound": (f"(let* ((next {MATCH_VALUE})) (continue (loop-state :like state :current next)))", MATCH_VALUE),
}
_DIAGNOSTIC = re.compile(r"entry\.orc:(\d+):(\d+): \[([a-z0-9_]+)\] ")


def _location(source: str, fragment: str) -> tuple[str, str]:
    before = source[: source.index(fragment)]
    return str(before.count("\n") + 1), str(len(before) - before.rfind("\n"))


@pytest.mark.parametrize("shape", list(BRANCH_FORMS))
def test_an_effectful_control_value_bound_in_a_loop_body_is_a_located_compiler_defect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, shape: str
) -> None:
    continue_form, value = BRANCH_FORMS[shape]
    probes = _write_program(tmp_path, body=BRANCH_LOOP.replace("CONTINUE", continue_form), returns="Candidate", seed="draft")
    source = (tmp_path / "grt" / "entry.orc").read_text(encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        exit_code, _, logs = _run(tmp_path, monkeypatch, probes)

    assert (exit_code, _DIAGNOSTIC.findall(caplog.text)[:1], logs) == (
        2,
        [(*_location(source, value), "compiler_defect_loop_control_value")],
        ([], [], []),
    )


@pytest.mark.parametrize("shape", list(BRANCH_FORMS))
def test_target_232_keeps_the_failure_of_an_effectful_control_value_in_a_loop_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, shape: str
) -> None:
    """Base behaviour at 2.32 is an internal exception, reported as `compiler_defect` since Task 13."""

    continue_form, _ = BRANCH_FORMS[shape]
    body = BRANCH_LOOP.replace("CONTINUE", continue_form)
    probes = _write_program(tmp_path, body=body, returns="Candidate", seed="draft", target="2.32")

    with caplog.at_level(logging.ERROR):
        outcome = _run(tmp_path, monkeypatch, probes)

    assert (outcome, [code for _, _, code in _DIAGNOSTIC.findall(caplog.text)]) == (
        (2, {}, ([], [], [])),
        ["compiler_defect"],
    )
