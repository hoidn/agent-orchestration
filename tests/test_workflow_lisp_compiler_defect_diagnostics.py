"""Shared defect repairs, Task 13: an internal failure after typecheck is a located compiler defect.

Plan: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md, Task 13.
Design: docs/design/workflow_lisp_core_calculus_middle_end.md section 9 (elaboration
totality) and section 13.3 (elaboration, normalization and defunctionalization failures
on typechecked programs are compiler defects by definition and must say so, with node
provenance); docs/design/workflow_language_design_principles.md principle 28.

A Python exception raised while a typechecked program is elaborated or lowered ends the
public run with exit 2 and one `compiler_defect` diagnostic at the authored form that the
failing stage was handling. The programs are defects that are not repaired: totality
matrix cells and the programs of the Task 4 and Task 5 reports. `--debug` prints the
internal traceback.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.wcc import defunctionalize as wcc_defunctionalize
from tests.test_workflow_lisp_elaborated_prefixes import _run as _run_candidate_program, _write_program
from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.test_workflow_lisp_prefix_scope import BRANCH_FORMS, BRANCH_LOOP, IF_VALUE, _location
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_argv
from tests.workflow_lisp_totality_matrix_sources import COMMANDS, PROBE, expected, program


REPO_ROOT = Path(__file__).resolve().parents[1]
_DIAGNOSTIC = re.compile(r"(\S+):(\d+):(\d+): \[([a-z0-9_]+)\] (.*)")

# Task 4 fix report, found 1: a pure procedure call bound in a loop body and then matched.
# Pure-projection type inference does not know the inlined procedure's parameter.
JUDGE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule grt/entry)
  (export run)
  (defrecord Cand (title String) (score Int))
  (defunion Verdict (GOOD (c Cand)) (BAD (c Cand)))
  (defproc judge ((c Cand)) -> Verdict :effects () :lowering inline
    (if (= c.score 2) (variant Verdict GOOD :c c) (variant Verdict BAD :c c)))
  (defworkflow run () -> Cand
    (loop/recur :max 5
      :state (loop-state (current Cand (record Cand :title "a" :score 0)))
      :on-exhausted state.current
      (fn (state)
        (let* ((verdict (judge state.current)))
          (match verdict
            ((GOOD g) (done g.c))
            ((BAD b) (continue (loop-state :like state :current (record Cand :title b.c.title :score (+ b.c.score 1)))))))))))
"""


def _diagnostics(caplog: pytest.LogCaptureFixture) -> list[tuple[str, ...]]:
    """(path, line, column, code, message) of each diagnostic the run logged."""

    matches = (_DIAGNOSTIC.match(record.getMessage()) for record in caplog.records)
    return [match.groups() for match in matches if match]


def _run_cell(root: Path, monkeypatch: pytest.MonkeyPatch, form: str, position: str):
    """Run one totality matrix cell. Return its run result, its entry source and its command log."""

    probe = _write_probe(root, "probe", PROBE)
    _write_sources(root, program(form, position, probe.as_posix()))
    monkeypatch.chdir(root)
    result = _public_run(_public_run_files(root, {name: probe for name in COMMANDS}))
    return result, (root / "grt" / "entry.orc").read_text(encoding="utf-8"), _log(probe)


def _cell(form: str, position: str):
    def run(root: Path, monkeypatch: pytest.MonkeyPatch):
        result, source, commands = _run_cell(root, monkeypatch, form, position)
        return result.exit_code, source, commands

    return run


def _run_judge(root: Path, monkeypatch: pytest.MonkeyPatch):
    _write_sources(root, {"grt/entry.orc": JUDGE})
    monkeypatch.chdir(root)
    return _public_run(_public_run_files(root, {})).exit_code, JUDGE, []


def _run_branch_value_at_232(root: Path, monkeypatch: pytest.MonkeyPatch):
    """Task 5 report, shape 7: an effectful `if` bound in a loop body, at target 2.32."""

    body = BRANCH_LOOP.replace("CONTINUE", BRANCH_FORMS["if-bound"][0])
    probes = _write_program(root, body=body, returns="Candidate", seed="draft", target="2.32")
    exit_code, _, logs = _run_candidate_program(root, monkeypatch, probes)
    return exit_code, (root / "grt" / "entry.orc").read_text(encoding="utf-8"), [line for log in logs for line in log]


CASES = {
    # Totality matrix, done-call: the elaborator has no rule for an effectful `done` value.
    "type-error-in-elaboration": (
        _cell("command-call", "done-value"),
        "(fetch 7)",
        "elaboration",
        "TypeError: unsupported WCC elaboration node: ProcedureCallExpr",
    ),
    # Totality matrix, loop-state-union: pure projection cannot represent a union-typed loop-state field,
    # so it fails while it reads `state.turn` from that state.
    "type-error-in-lowering": (
        _cell("plain-variant", "loop-state-field"),
        "state.turn",
        "lowering",
        "TypeError: unsupported pure projection expression: dict",
    ),
    "key-error-in-lowering": (_run_judge, "(judge state.current)", "lowering", "KeyError: '__pure_procedure_param_"),
    "value-error-in-lowering": (
        _run_branch_value_at_232,
        IF_VALUE,
        "lowering",
        "ValueError: pure boolean conditions require WCC pure-projection lowering",
    ),
}


@pytest.mark.parametrize("case", list(CASES))
def test_an_internal_exception_after_typecheck_is_a_compiler_defect_at_the_form_being_lowered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, case: str
) -> None:
    run, form, stage, internal = CASES[case]

    with caplog.at_level(logging.ERROR):
        exit_code, source, commands = run(tmp_path, monkeypatch)
    found = _diagnostics(caplog)
    message = found[0][4] if found else ""

    assert (
        exit_code,
        [row[:4] for row in found],
        commands,
        {part: part in message for part in ("passed typecheck", "defect of the compiler", stage, internal)},
    ) == (
        2,
        [(str(tmp_path / "grt" / "entry.orc"), *_location(source, form), "compiler_defect")],
        [],
        dict.fromkeys(("passed typecheck", "defect of the compiler", stage, internal), True),
    ), caplog.text


def test_a_located_diagnostic_raised_after_typecheck_keeps_its_code_and_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Totality matrix, loop-call-argument: call lowering rejects a literal argument inside a loop."""

    with caplog.at_level(logging.ERROR):
        result, source, commands = _run_cell(tmp_path, monkeypatch, "command-call", "loop-state-field")

    assert (result.exit_code, [row[1:4] for row in _diagnostics(caplog)], commands) == (
        2,
        [(*_location(source, "7) :turn 1"), "workflow_signature_mismatch")],
        [],
    )


def test_a_program_that_compiles_runs_as_before(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, _, commands = _run_cell(tmp_path, monkeypatch, "command-call", "let-binding")

    assert (result.exit_code, dict(result.workflow_outputs), commands) == (0, *expected("command-call", "let-binding"))


@pytest.mark.parametrize(
    ("raised", "outcome"),
    [(AssertionError, 1), (MemoryError, 1), (KeyboardInterrupt, KeyboardInterrupt)],
    ids=["assertion", "memory-error", "keyboard-interrupt"],
)
def test_assertions_memory_errors_and_interrupts_are_not_converted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    raised: type[BaseException],
    outcome: object,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise raised("injected")

    monkeypatch.setattr(wcc_defunctionalize, "_lower_wcc_workflow_definitions", fail)

    with caplog.at_level(logging.ERROR):
        try:
            observed: object = _run_cell(tmp_path, monkeypatch, "command-call", "let-binding")[0].exit_code
        except BaseException as error:  # noqa: BLE001 - the test observes which exception escapes
            observed = type(error)

    assert (observed, "[compiler_defect]" in caplog.text) == (outcome, False)


def test_debug_prints_the_internal_traceback_of_a_compiler_defect(tmp_path: Path) -> None:
    probe = _write_probe(tmp_path, "probe", PROBE)
    _write_sources(tmp_path, program("command-call", "done-value", probe.as_posix()))
    files = _public_run_files(tmp_path, {name: probe for name in COMMANDS})
    cli = [arg for arg in _run_argv(files) if arg != "--emit-debug-yaml"]  # an option of the test driver only
    argv = [sys.executable, "-m", *cli, "--command-boundaries-file", str(files["commands"])]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}

    runs = {
        flag: subprocess.run([*argv, *flags], cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
        for flag, flags in {"plain": [], "debug": ["--debug"]}.items()
    }

    assert {
        flag: (run.returncode, "[compiler_defect]" in run.stderr, "in _elaborate_expr_to_value" in run.stderr)
        for flag, run in runs.items()
    } == {"plain": (2, True, False), "debug": (2, True, True)}, runs["debug"].stderr
