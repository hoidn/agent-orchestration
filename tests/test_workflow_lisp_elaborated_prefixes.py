"""Shared defect repairs, Task 5: bound prefixes in `loop-state` fields and `match` subjects.

Plan: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md, Task 5
(decision brief case b and the `unsupported nested WCC M2 prefix` crash).
Design: docs/design/workflow_lisp_core_calculus_middle_end.md section 9
(elaboration totality) and section 11.1 (compound arguments are atomized,
`case` scrutinees are atoms).

At target 2.33 an effectful call written directly in a `loop-state :like` field
or inside a `match` subject runs exactly as the same program with the call bound
by `let*` first. Below 2.33 the same programs fail as they do at `7984b51e`.

Effects are command-backed probes that append their argv to `<probe>.log`
(see tests/workflow_lisp_improve_stdlib_sources.py for the probe policy).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_workflow_lisp_generic_unions_runtime import (
    _compile,
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.test_workflow_lisp_improve_stdlib import _resume, _run_until_the_first_committed_iteration
from tests.workflow_lisp_improve_stdlib_sources import REVIEW_PROBE, REVISE_PROBE, SUMMARIZE_PROBE


MODULE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Candidate (title String) (score Int))
  (defrecord Feedback (note String))
  (defrecord Blocker (why String))
  (defrecord Summary (outcome String) (title String) (score Int))
  (defunion Decision
    (APPROVE (evidence Feedback))
    (REVISE (feedback Feedback))
    (BLOCKED (reason Blocker)))
  (defproc review ((candidate Candidate)) -> Decision
    :effects ((uses-command probe_review))
    :lowering inline
    (command-result probe_review
      :argv ("python" "PROBE_REVIEW" candidate.title "tidy")
      :returns Decision))
  (defproc revise ((candidate Candidate)) -> Candidate
    :effects ((uses-command probe_revise))
    :lowering inline
    (command-result probe_revise
      :argv ("python" "PROBE_REVISE" candidate.title "tidy" "fb")
      :returns Candidate))
  (defproc summarize ((outcome String) (note String)) -> Summary
    :effects ((uses-command probe_summarize))
    :lowering inline
    (command-result probe_summarize
      :argv ("python" "PROBE_SUMMARIZE" outcome note 0)
      :returns Summary))
  (defworkflow run () -> RETURNS
    BODY))
"""

SEED = '(record Candidate :title "SEED" :score 0)'

LOOP = """(loop/recur :max 4
      :state (loop-state (current Candidate SEED)
                         (other Candidate (record Candidate :title "other" :score 0)))
      :on-exhausted state.current
      (fn (state)
        (if (= state.current.score 2) (done state.current) CONTINUE)))"""

# `current` is declared before `other`; the two-field form overrides `other` first.
CONTINUES = {
    "one-field": {
        "direct": "(continue (loop-state :like state :current (revise state.current)))",
        "let-bound": "(let* ((next (revise state.current))) (continue (loop-state :like state :current next)))",
    },
    "two-fields": {
        "direct": "(continue (loop-state :like state :other (revise state.current) :current (revise state.other)))",
        "let-bound": (
            "(let* ((a (revise state.current)) (b (revise state.other)))"
            " (continue (loop-state :like state :other a :current b)))"
        ),
    },
}

MATCH = """(match SUBJECT
      ((APPROVE a) (summarize "APPROVE" a.evidence.note))
      ((REVISE r) (summarize "REVISE" r.feedback.note))
      ((BLOCKED b) (summarize "BLOCKED" b.reason.why)))"""

MATCHES = {
    "let-name": {
        "direct": MATCH.replace("SUBJECT", "(let* ((d (review SEED))) d)"),
        "let-bound": "(let* ((d (review SEED))) " + MATCH.replace("SUBJECT", "d") + ")",
    },
    "let-call": {
        "direct": MATCH.replace("SUBJECT", "(let* ((next (revise SEED))) (review next))"),
        "let-bound": "(let* ((next (revise SEED)) (d (review next))) " + MATCH.replace("SUBJECT", "d") + ")",
    },
}

# Both repairs in one loop: an improve-shaped loop written without `let*`.
LOOP_MATCH = """(loop/recur :max 3
      :state (loop-state (current Candidate SEED))
      :on-exhausted state.current
      (fn (state)
        (match (let* ((d (review state.current))) d)
          ((APPROVE a) (done state.current))
          ((BLOCKED b) (done state.current))
          ((REVISE r) (continue (loop-state :like state :current (revise state.current)))))))"""

PROBES = (("probe_review", REVIEW_PROBE), ("probe_revise", REVISE_PROBE), ("probe_summarize", SUMMARIZE_PROBE))


def _loop_body(shape: str, form: str) -> str:
    return LOOP.replace("CONTINUE", CONTINUES[shape][form])


def _write_program(root: Path, *, body: str, returns: str, seed: str, target: str = "2.33") -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    probes = {name: _write_probe(root, name, text) for name, text in PROBES}
    source = (
        MODULE.replace("TARGET", target)
        .replace("RETURNS", returns)
        .replace("BODY", body)
        .replace("SEED", SEED)
        .replace('"SEED"', f'"{seed}"')
    )
    for name, path in probes.items():
        source = source.replace(name.upper(), path.as_posix())
    _write_sources(root, {"grt/entry.orc": source})
    return probes


def _logs(probes: dict[str, Path]) -> tuple[list[str], ...]:
    return tuple(_log(probes[name]) for name, _ in PROBES)


def _run(root: Path, monkeypatch: pytest.MonkeyPatch, probes: dict[str, Path]):
    monkeypatch.chdir(root)
    result = _public_run(_public_run_files(root, probes))
    return result.exit_code, dict(result.workflow_outputs or {}), _logs(probes)


@pytest.mark.parametrize("form", ["direct", "let-bound"])
@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        (
            "one-field",
            (0, {"return__title": "draft+r+r", "return__score": 2}, ([], ["draft tidy fb", "draft+r tidy fb"], [])),
        ),
        (
            "two-fields",
            (
                0,
                {"return__title": "draft+r+r", "return__score": 2},
                ([], ["draft tidy fb", "other tidy fb", "other+r tidy fb", "draft+r tidy fb"], []),
            ),
        ),
    ],
    ids=["one-field", "two-fields-run-once-each-in-authored-order"],
)
def test_effectful_call_in_a_loop_state_field_runs_as_the_let_bound_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, expected: tuple, form: str
) -> None:
    probes = _write_program(tmp_path, body=_loop_body(shape, form), returns="Candidate", seed="draft")

    assert _run(tmp_path, monkeypatch, probes) == expected


@pytest.mark.parametrize("form", ["direct", "let-bound"])
@pytest.mark.parametrize(
    ("shape", "seed", "expected"),
    [
        (
            "let-name",
            "approve",
            (
                0,
                {"return__outcome": "APPROVE", "return__title": "ok:approve:tidy", "return__score": 0},
                (["approve tidy"], [], ["APPROVE ok:approve:tidy 0"]),
            ),
        ),
        (
            "let-call",
            "approve",
            (
                0,
                {"return__outcome": "APPROVE", "return__title": "ok:approve+r:tidy", "return__score": 0},
                (["approve+r tidy"], ["approve tidy fb"], ["APPROVE ok:approve+r:tidy 0"]),
            ),
        ),
        (
            "let-call",
            "block",
            (
                0,
                {"return__outcome": "BLOCKED", "return__title": "refused:block+r", "return__score": 0},
                (["block+r tidy"], ["block tidy fb"], ["BLOCKED refused:block+r 0"]),
            ),
        ),
        (
            "let-call",
            "draft",
            (
                0,
                {"return__outcome": "REVISE", "return__title": "fb1", "return__score": 0},
                (["draft+r tidy"], ["draft tidy fb"], ["REVISE fb1 0"]),
            ),
        ),
    ],
    ids=["let-name-approve", "let-call-approve", "let-call-blocked", "let-call-revise"],
)
def test_effectful_call_inside_a_match_subject_runs_as_the_let_bound_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, seed: str, expected: tuple, form: str
) -> None:
    probes = _write_program(tmp_path, body=MATCHES[shape][form], returns="Summary", seed=seed)

    assert _run(tmp_path, monkeypatch, probes) == expected


def test_loop_with_both_forms_exhausts_like_improve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probes = _write_program(tmp_path, body=LOOP_MATCH, returns="Candidate", seed="draft")

    assert _run(tmp_path, monkeypatch, probes) == (
        0,
        {"return__title": "draft+r+r+r", "return__score": 3},
        (
            ["draft tidy", "draft+r tidy", "draft+r+r tidy"],
            ["draft tidy fb", "draft+r tidy fb", "draft+r+r tidy fb"],
            [],
        ),
    )


@pytest.mark.parametrize(
    ("body", "after_first_commit", "expected"),
    [
        (
            _loop_body("two-fields", "direct"),
            ([], ["draft tidy fb", "other tidy fb"], []),
            (
                "completed",
                {"return__title": "draft+r+r", "return__score": 2},
                ([], ["draft tidy fb", "other tidy fb", "other+r tidy fb", "draft+r tidy fb"], []),
            ),
        ),
        (
            LOOP_MATCH,
            (["draft tidy"], ["draft tidy fb"], []),
            (
                "completed",
                {"return__title": "draft+r+r+r", "return__score": 3},
                (
                    ["draft tidy", "draft+r tidy", "draft+r+r tidy"],
                    ["draft tidy fb", "draft+r tidy fb", "draft+r+r tidy fb"],
                    [],
                ),
            ),
        ),
    ],
    ids=["loop-state-fields", "match-subject-and-loop-state-field"],
)
def test_resume_after_the_first_committed_iteration_runs_no_committed_command_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str, after_first_commit: tuple, expected: tuple
) -> None:
    probes = _write_program(tmp_path, body=body, returns="Candidate", seed="draft")
    monkeypatch.chdir(tmp_path)

    run_id = _run_until_the_first_committed_iteration(monkeypatch, _public_run_files(tmp_path, probes))
    assert _logs(probes) == after_first_commit

    state = _resume(run_id)
    assert (state["status"], state["workflow_outputs"], _logs(probes)) == expected


@pytest.mark.parametrize(
    ("body", "returns", "message"),
    [
        (_loop_body("one-field", "direct"), "Candidate", "unsupported pure projection expression: ProcedureCallExpr"),
        (_loop_body("two-fields", "direct"), "Candidate", "unsupported pure projection expression: ProcedureCallExpr"),
        (MATCHES["let-name"]["direct"], "Summary", "unsupported nested WCC M2 prefix for `LetStarExpr`"),
        (MATCHES["let-call"]["direct"], "Summary", "unsupported nested WCC M2 prefix for `LetStarExpr`"),
        (LOOP_MATCH, "Candidate", "unsupported nested WCC M2 prefix for `LetStarExpr`"),
    ],
    ids=["loop-state-one-field", "loop-state-two-fields", "match-let-name", "match-let-call", "loop-match"],
)
def test_target_232_keeps_the_failure_it_has_at_the_base_commit(
    tmp_path: Path, body: str, returns: str, message: str
) -> None:
    probes = _write_program(tmp_path, body=body, returns=returns, seed="draft", target="2.32")

    with pytest.raises(TypeError, match=f"^{re.escape(message)}$"):
        _compile(tmp_path, probes=probes)
