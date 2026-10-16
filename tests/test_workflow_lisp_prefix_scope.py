"""Bindings in expression prefixes keep their lexical scope at 2.35.

Effect payloads use a command probe that records the received JSON;
materialize-view execution and generated lowering names have been retired.

Plan: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md, Task 5.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workflow_lisp_elaborated_prefixes import CAPTURE_PROBE, _logs, _run, _write_program
from tests.workflow_evaluated_totality_helpers import _write_probe
from tests.workflow_evaluated_totality_helpers import public_run
from tests.test_workflow_lisp_elaborated_prefixes import _scope_files


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
    name: (0, {"outcome": "REVISE", "title": "outer", "score": 0}, (review, ["draft tidy fb"], ["REVISE outer 0"]))
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

def _run_with_inputs(
    root: Path, monkeypatch: pytest.MonkeyPatch, *, body: str, returns: str, params: str, inputs: dict, decls: str = ""
):
    """Run the template program with workflow parameters `params`, the given inputs and extra declarations."""

    probes = _write_program(root, body=body, returns=returns, seed="draft")
    if "CAPTURE" in body:
        probes["capture"] = _write_probe(root, "capture", CAPTURE_PROBE)
    source = root / "grt" / "entry.orc"
    text = source.read_text(encoding="utf-8").replace("(defworkflow run ()", f"{decls}(defworkflow run ({params})")
    if "capture" in probes:
        text = text.replace("CAPTURE", probes["capture"].as_posix())
    source.write_text(text, encoding="utf-8")
    input_file = root / "inputs.json"
    input_file.write_text(json.dumps(inputs), encoding="utf-8")
    monkeypatch.chdir(root)
    files = _scope_files(root, probes)
    result = public_run(files, input_file=input_file)
    return result.exit_code, dict(result.workflow_outputs or {}), _logs(probes)


def _run_with_input(root: Path, monkeypatch: pytest.MonkeyPatch, form: str, name: str):
    return _run_with_inputs(
        root,
        monkeypatch,
        body=COLLISION_LOOP.replace("CONTINUE", COLLISION_CONTINUES[form]).replace("ALT", name),
        returns="Candidate",
        params=f"({name} Candidate)",
        inputs={name: {"title": "author", "score": 5}},
    )


@pytest.mark.parametrize("form", list(COLLISION_CONTINUES))
def test_an_authored_prefix_like_identifier_keeps_its_input_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    expected = (0, {"title": "author", "score": 5}, ([], ["draft tidy fb", "draft+r tidy fb"], []))
    assert _run_with_input(tmp_path, monkeypatch, form, "__wcc_effect_current_0123456789abcdef") == expected


VIEW = (
    '(command-result capture :argv ("python" "CAPTURE" target) :inputs ((value note)) :returns String)'
)
VIEW_FORMS = {
    "direct": f"(let* ((note {OUTER})) {_match_on(f'(let* ((note (revise SEED)) (p {VIEW}) (d (review note))) d)', 'note.title')})",
    "let-bound": (
        f"(let* ((note {OUTER}) (inner (revise SEED)) (p {VIEW.replace('value note', 'value inner')}) (d (review inner)))"
        f" {_match_on('d', 'note.title')})"
    ),
}


@pytest.mark.parametrize("form", list(VIEW_FORMS))
def test_a_renamed_binding_is_renamed_inside_an_effect_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    """The command receives the renamed binding as a native input value."""

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
    {"title": "other+r+r+r", "score": 3},
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


# Bound effectful control values preserve branch order under evaluated execution.
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


def _location(source: str, fragment: str) -> tuple[str, str]:
    before = source[: source.index(fragment)]
    return str(before.count("\n") + 1), str(len(before) - before.rfind("\n"))


@pytest.mark.parametrize("shape", list(BRANCH_FORMS))
def test_an_effectful_control_value_bound_in_a_loop_body_keeps_order_and_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    continue_form, _ = BRANCH_FORMS[shape]
    probes = _write_program(tmp_path, body=BRANCH_LOOP.replace("CONTINUE", continue_form), returns="Candidate", seed="draft")
    expected_logs = (["draft tidy", "other+r tidy"], ["other tidy fb", "other tidy fb"], []) if shape.startswith("match") else ([], ["draft tidy fb", "other tidy fb"], [])
    assert _run(tmp_path, monkeypatch, probes) == (0, {"title": "other+r", "score": 1}, expected_logs)


@pytest.mark.parametrize("form", list(TWO_ARMS_FORMS))
def test_resume_after_a_committed_command_preserves_each_match_arm_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    from tests.test_workflow_lisp_elaborated_prefixes import _assert_committed_prefix_resume

    probes = _write_program(tmp_path, body=_two_arms(form), returns="Candidate", seed="block")
    _assert_committed_prefix_resume(tmp_path, monkeypatch, probes, (0, *TWO_ARMS_EXPECTED))
