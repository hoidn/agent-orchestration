"""Scope and authored command order in loop-state fields and match subjects.

Source profiles remain covered by typed frontend analysis. Runtime checks use
public evaluated target 2.35 and native result values; imported module headers
retain their authored profiles.

Plan: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md, Task 5.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.workflow_evaluated_totality_helpers import _log, _public_run_files, _write_probe, _write_sources
from tests.workflow_evaluated_totality_helpers import public_run
from tests.workflow_lisp_improve_stdlib_sources import REVIEW_PROBE, REVISE_PROBE, SUMMARIZE_PROBE


MODULE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
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


CAPTURE_PROBE = """import json, os, sys
from pathlib import Path
document = json.loads(Path(sys.argv[-1]).read_text())
target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(document["value"]))
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(sys.argv[1]))
"""

PROBES = (("probe_review", REVIEW_PROBE), ("probe_revise", REVISE_PROBE), ("probe_summarize", SUMMARIZE_PROBE))


def _loop_body(shape: str, form: str) -> str:
    return LOOP.replace("CONTINUE", CONTINUES[shape][form])


def _write_program(root: Path, *, body: str, returns: str, seed: str) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    probes = {name: _write_probe(root, name, text) for name, text in PROBES}
    source = (
        MODULE
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


def _scope_files(root: Path, probes: dict[str, Path]):
    files = _public_run_files(root, probes)
    files["workspace"] = root
    commands = json.loads(files["commands"].read_text())
    for name, path in probes.items():
        commands[name]["closure"] = [path.name]
    files["commands"].write_text(json.dumps(commands))
    return files


def _run(root: Path, monkeypatch: pytest.MonkeyPatch, probes: dict[str, Path]):
    monkeypatch.chdir(root)
    files = _scope_files(root, probes)
    result = public_run(files)
    return result.exit_code, dict(result.workflow_outputs or {}), _logs(probes)


@pytest.mark.parametrize("form", ["direct", "let-bound"])
@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        (
            "one-field",
            (0, {"title": "draft+r+r", "score": 2}, ([], ["draft tidy fb", "draft+r tidy fb"], [])),
        ),
        (
            "two-fields",
            (
                0,
                {"title": "draft+r+r", "score": 2},
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
                {"outcome": "APPROVE", "title": "ok:approve:tidy", "score": 0},
                (["approve tidy"], [], ["APPROVE ok:approve:tidy 0"]),
            ),
        ),
        (
            "let-call",
            "approve",
            (
                0,
                {"outcome": "APPROVE", "title": "ok:approve+r:tidy", "score": 0},
                (["approve+r tidy"], ["approve tidy fb"], ["APPROVE ok:approve+r:tidy 0"]),
            ),
        ),
        (
            "let-call",
            "block",
            (
                0,
                {"outcome": "BLOCKED", "title": "refused:block+r", "score": 0},
                (["block+r tidy"], ["block tidy fb"], ["BLOCKED refused:block+r 0"]),
            ),
        ),
        (
            "let-call",
            "draft",
            (
                0,
                {"outcome": "REVISE", "title": "fb1", "score": 0},
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
        {"title": "draft+r+r+r", "score": 3},
        (
            ["draft tidy", "draft+r tidy", "draft+r+r tidy"],
            ["draft tidy fb", "draft+r tidy fb", "draft+r+r tidy fb"],
            [],
        ),
    )


# Imported current-profile definitions retain scope under an evaluated entry.
# `refine` is LOOP_MATCH (both repaired forms) as a procedure of `grt/lib`.
REFINE_HEADER = """(defproc refine ((seed Candidate)) -> Candidate
    :effects ((uses-command probe_review) (uses-command probe_revise))
    :lowering inline"""
ENTRY = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule grt/entry)
  (import grt/lib :only (Candidate review revise refine))
  (export run)
  (defworkflow run () -> Candidate
    BODY))
"""
DRAFT = '(record Candidate :title "draft" :score 0)'
CALL_REFINE = f"(refine {DRAFT})"
REFINED = (
    0,
    {"title": "draft+r+r+r", "score": 3},
    (["draft tidy", "draft+r tidy", "draft+r+r tidy"], ["draft tidy fb", "draft+r tidy fb", "draft+r+r tidy fb"], []),
)


def _write_imported_program(root: Path, *, entry_body: str) -> dict[str, Path]:
    probes = _write_program(root, body=LOOP_MATCH.replace("SEED", "seed"), returns="Candidate", seed="draft")
    lib = (
        (root / "grt" / "entry.orc")
        .read_text(encoding="utf-8")
        .replace("(defmodule grt/entry)", "(defmodule grt/lib)")
        .replace("(export run)", "(export Candidate review revise refine)")
        .replace("(defworkflow run () -> Candidate", REFINE_HEADER)
    )
    entry = ENTRY.replace("BODY", entry_body)
    _write_sources(root, {"grt/lib.orc": lib, "grt/entry.orc": entry})
    return probes


@pytest.mark.parametrize(
    "entry_body",
    [CALL_REFINE, LOOP_MATCH.replace("SEED", DRAFT)],
    ids=["calls-imported-definition", "writes-the-forms"],
)
def test_the_forms_keep_source_scope_in_an_imported_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry_body: str
) -> None:
    probes = _write_imported_program(tmp_path, entry_body=entry_body)

    assert _run(tmp_path, monkeypatch, probes) == REFINED


def _assert_committed_prefix_resume(root, monkeypatch, probes, expected):
    from tests.workflow_evaluated_totality_helpers import (
        assert_commit_bytes, checked_run, pause_public, completed_resume,
    )
    from tests.test_workflow_evaluated_resume import _resume_cli

    files = _scope_files(root, probes)
    monkeypatch.chdir(root)
    committed = pause_public(files, monkeypatch)
    authority, before = checked_run(root)
    assert list(before.active_commits.values()) == [committed]
    assert before.terminal is None
    assert_commit_bytes(authority, committed)
    prefix = authority.memo_path.read_bytes()
    resumed = _resume_cli(root, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    authority, after = checked_run(root)
    assert authority.memo_path.read_bytes().startswith(prefix)
    assert (0, after.terminal.data["value"], _logs(probes)) == expected
    assert len(after.active_commits) == sum(len(log) for log in expected[2])
    completed_resume(root, next(iter(probes.values())), authority)
    assert _logs(probes) == expected[2]


@pytest.mark.parametrize("shape", ["loop-state-fields", "match-subject-and-loop-state-field"])
def test_resume_after_a_committed_command_preserves_scope_and_never_repeats_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    body = _loop_body("two-fields", "direct") if shape == "loop-state-fields" else LOOP_MATCH
    expected = (
        (0, {"title": "draft+r+r", "score": 2}, ([], ["draft tidy fb", "other tidy fb", "other+r tidy fb", "draft+r tidy fb"], []))
        if shape == "loop-state-fields" else REFINED
    )
    probes = _write_program(tmp_path, body=body, returns="Candidate", seed="draft")
    _assert_committed_prefix_resume(tmp_path, monkeypatch, probes, expected)
