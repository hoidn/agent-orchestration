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

import json
import logging
import re
import sys
import traceback
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from orchestrator.workflow.pure_expr import PureExprEvaluationError
from orchestrator.workflow_lisp.diagnostics import LispFrontendDiagnostic
from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.workflow_lisp_totality_matrix_sources import (
    COMMANDS,
    DEFECTS,
    KNOWN_DEFECTS,
    PROBE,
    RESTRICTION_CODES,
    RETURN_BOUNDARY_RULES,
    RULES,
    SKIPPED,
    STAGES,
    cells,
    expected,
    program,
)


_DIAGNOSTIC_CODE = re.compile(r":\d+:\d+: \[([a-z0-9_]+)\] ")


@dataclass(frozen=True)
class Outcome:
    exit_code: int
    kind: str | None  # the first diagnostic code logged, or else the type of the exception logged
    stage: str | None
    errors: str  # every error the run logged
    outputs: dict[str, object]
    calls: list[str]
    listing: str  # the program, for failure messages

    def report(self) -> str:
        return f"observed: exit {self.exit_code}, {self.kind}, stage {self.stage}\n{self.errors}\n{self.listing}"


def _where(frames) -> list[str]:
    return [f"{Path(frame.f_code.co_filename).as_posix()}:{frame.f_code.co_name}" for frame in frames]


def _origin(exc: BaseException) -> list[str]:
    """The frames of an exception's traceback, innermost first."""

    return _where(reversed([frame for frame, _ in traceback.walk_tb(exc.__traceback__)]))


def _stage(origin: list[str]) -> str | None:
    for where in origin:
        for fragment, stage in STAGES:
            if fragment in where:
                return stage
    return None


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


def _runtime_error(result) -> dict | None:
    if result.run_root is None:
        return None
    state_path = result.run_root / "state.json"
    if not state_path.exists():
        return None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return next((step["error"] for step in state.get("steps", {}).values()
                 if step.get("error", {}).get("type", "").startswith("pure_expr_")), None)


def _run(root: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, form: str, position: str):
    """Run one program through the public run entry and observe how it ends."""

    probe = _write_probe(root, "probe", PROBE)
    sources = program(form, position, probe.as_posix())
    _write_sources(root, sources)
    monkeypatch.chdir(root)
    origins = _record_diagnostic_origins(monkeypatch)
    with caplog.at_level(logging.ERROR):
        result = _public_run(_public_run_files(root, {name: probe for name in COMMANDS}))
    codes = _DIAGNOSTIC_CODE.findall(caplog.text)
    exceptions = [record.exc_info[1] for record in caplog.records if record.exc_info]
    kind, stage = None, None
    if codes:
        kind = codes[0]
        stage = _stage(next((origin for code, origin in origins if code == kind), []))
    elif exceptions:
        kind, stage = type(exceptions[0]).__name__, _stage(_origin(exceptions[0]))
    errors = caplog.text
    if result.exit_code and kind is None and (error := _runtime_error(result)):
        kind = error["type"]
        stage = _stage(next((origin for code, origin in reversed(origins) if code == kind), []))
        errors += "\n" + json.dumps(error, sort_keys=True)
    listing = "\n".join(f"--- {path}\n{text}" for path, text in sources.items())
    return Outcome(result.exit_code, kind, stage, errors, dict(result.workflow_outputs), _log(probe), listing)


def _rule_cells() -> list:
    return [pytest.param(form, position, id=f"{form}/{position}") for form, position in cells() if (form, position) in RULES]


def _runnable() -> list:
    return [
        pytest.param(form, position, id=f"{form}/{position}")
        for form, position in cells()
        if (form, position) not in SKIPPED and (form, position) not in RULES
    ]


def test_every_cell_has_exactly_one_classification(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert len(cells()) == len(set(cells())), "matrix cell identifiers must be unique"
    tables = {"skipped": SKIPPED, "rule": RULES, "known defect": KNOWN_DEFECTS}
    found = {cell: [name for name, table in tables.items() if cell in table] or ["working"] for cell in cells()}
    counts = Counter(kind for kinds in found.values() for kind in kinds)
    report = tmp_path / "totality-matrix-counts.json"
    report.write_text(
        json.dumps({kind: counts[kind] for kind in ("rule", "working", "known defect", "skipped")} | {"cells": len(found)}),
        encoding="utf-8",
    )
    summary = (
        f"totality matrix: {counts['rule']} rule, {counts['working']} working, "
        f"{counts['known defect']} known defect ({counts['skipped']} skipped of {len(found)}); written to {report}"
    )
    with capsys.disabled():
        print(f"\n{summary}")

    stages = {stage for _, stage in STAGES}
    assert (
        {cell: kinds for cell, kinds in found.items() if len(kinds) != 1},
        {cell for table in tables.values() for cell in table} - set(found),
        {defect.label for defect in KNOWN_DEFECTS.values()} - set(DEFECTS),
        {defect.stage for defect in KNOWN_DEFECTS.values()} - stages,
        set(RULES.values()) - RESTRICTION_CODES,
        {stage for _, stage in RETURN_BOUNDARY_RULES.values()} - stages,
    ) == ({}, set(), set(), set(), set(), set()), summary


@pytest.mark.parametrize(("form", "position"), _rule_cells())
def test_rule_cell_is_rejected_by_a_named_typecheck_restriction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, form: str, position: str
) -> None:
    outcome = _run(tmp_path, monkeypatch, caplog, form, position)

    assert (outcome.exit_code, outcome.kind, outcome.stage, outcome.calls) == (
        2, RULES[form, position], "typecheck", []
    ), outcome.report()


@pytest.mark.parametrize("form", sorted(RETURN_BOUNDARY_RULES))
def test_workflow_return_boundary_rejects_a_union_inside_a_returned_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, form: str
) -> None:
    outcome = _run(tmp_path, monkeypatch, caplog, form, "return-boundary")

    assert (outcome.exit_code, outcome.kind, outcome.stage, outcome.calls) == (
        2, *RETURN_BOUNDARY_RULES[form], []
    ), outcome.report()


@pytest.mark.parametrize(("form", "position"), _runnable())
def test_cell_returns_its_value_with_its_ordered_command_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, form: str, position: str
) -> None:
    outcome = _run(tmp_path, monkeypatch, caplog, form, position)
    defect = KNOWN_DEFECTS.get((form, position))
    if defect is None:
        assert (outcome.exit_code, outcome.outputs, outcome.calls) == (0, *expected(form, position)), (
            outcome.report()
        )
        return

    symptom, meaning = DEFECTS[defect.label]
    assert (outcome.exit_code, outcome.kind, outcome.stage, symptom in outcome.errors) == (
        defect.exit_code, defect.kind, defect.stage, True
    ), f"known defect {defect.label} does not fail as recorded in KNOWN_DEFECTS\n{outcome.report()}"
    pytest.xfail(f"known defect {defect.label}: {meaning}")
