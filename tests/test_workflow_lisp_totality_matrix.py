"""Totality matrix: forms, positions, call locality, and targets 2.33/2.34 via public run.

Contract: docs/design/workflow_lisp_core_calculus_middle_end.md sections 9 and 13.3;
Task 1 of docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md.

Every generated cell has exactly one classification, kept in
`tests/workflow_lisp_totality_matrix_sources.py`:

- rule: typecheck rejects it with a code from `RESTRICTION_CODES`, in the typecheck stage;
- working: it runs and returns its value with its ordered command log;
- known defect: it fails after typecheck, or typecheck rejects it wrongly. The test first
  asserts the failure recorded for the cell in `KNOWN_DEFECTS` (exit code, diagnostic code
  or exception type, stage, and the defect's symptom) and only then marks it xfail with the
  defect's name. Any other outcome fails the test, success included (a strict xfail): a
  repaired cell is declared working by deleting its line from `KNOWN_DEFECTS`.

The stage of a failure is read from the frames where it started (see `STAGES`); the
test records frontend diagnostics and pure-expression exceptions. Runtime errors
that the executor handles internally are matched to their persisted step error.

Cells whose form's type cannot occupy the position are listed in `SKIPPED` and not
generated. The classification test writes the counts to `totality-matrix-counts.json` in
its temporary directory, names that file in its assertion message, and prints both when
the module runs without xdist.
"""

from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

import pytest

from orchestrator.workflow.pure_expr import PureExprEvaluationError
from orchestrator.workflow_lisp.diagnostics import LispFrontendDiagnostic
from tests.workflow_lisp_totality_matrix_sources import KNOWN_DEFECTS, RULES, SKIPPED, cells


_DIAGNOSTIC_CODE = re.compile(r":\d+:\d+: \[([a-z0-9_]+)\] ")




def _where(frames) -> list[str]:
    return [f"{Path(frame.f_code.co_filename).as_posix()}:{frame.f_code.co_name}" for frame in frames]


def _origin(exc: BaseException) -> list[str]:
    """The frames of an exception's traceback, innermost first."""

    return _where(reversed([frame for frame, _ in traceback.walk_tb(exc.__traceback__)]))




def _record_diagnostic_origins(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    """Record, for each diagnostic created from now on, its code and where its failure started."""

    origins: list[tuple[str, list[str]]] = []
    create = LispFrontendDiagnostic.__init__

    def recording_init(self, *args, **kwargs) -> None:
        create(self, *args, **kwargs)
        handled = sys.exc_info()[1]
        if handled is not None:
            origins.append((self.code, _origin(handled)))
        else:
            origins.append((self.code, _where(frame for frame, _ in traceback.walk_stack(None))))

    monkeypatch.setattr(LispFrontendDiagnostic, "__init__", recording_init)
    create_pure_error = PureExprEvaluationError.__init__

    def recording_pure_error(self, code, message, **kwargs) -> None:
        create_pure_error(self, code, message, **kwargs)
        origins.append((code, _where(frame for frame, _ in traceback.walk_stack(None))))

    monkeypatch.setattr(PureExprEvaluationError, "__init__", recording_pure_error)
    return origins










def test_every_cell_has_exactly_one_classification(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert len(cells()) == len(set(cells())), "matrix cell identifiers must be unique"
    tables = {"skipped": SKIPPED, "rule": RULES, "known defect": KNOWN_DEFECTS}
    report = tmp_path / "totality-matrix-counts.json"
