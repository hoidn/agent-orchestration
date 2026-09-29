"""Totality matrix: value forms x positions at target 2.33, run through the public run entry.

Contract: docs/design/workflow_lisp_core_calculus_middle_end.md sections 9 and 13.3;
Task 1 of docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md.

Every generated cell has exactly one classification, kept in
`tests/workflow_lisp_totality_matrix_sources.py`:

- rule: typecheck rejects it with a code from `RESTRICTION_CODES`;
- working: it runs and returns its value with its ordered command log;
- known defect: it typechecks and then fails with exit 2 and a diagnostic code
  of its defect (`DEFECT_CODES`); any other failure fails the test. It is a
  strict xfail that names its defect, so a repair that makes it work fails the
  run until its line is deleted from `KNOWN_DEFECTS`.

Cells whose form's type cannot occupy the position are listed in `SKIPPED` and
not generated. The counts print when the module runs without xdist.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path

import pytest

from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.workflow_lisp_totality_matrix_sources import (
    COMMANDS,
    DEFECT_CODES,
    DEFECTS,
    KNOWN_DEFECTS,
    PROBE,
    RESTRICTION_CODES,
    RULES,
    SKIPPED,
    cells,
    expected,
    program,
)


_DIAGNOSTIC_CODE = re.compile(r":\d+:\d+: \[([a-z0-9_]+)\] ")


def _run(root: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, form: str, position: str):
    """Run one cell. Return the run result, the diagnostic codes it logged, its command log and its program."""

    probe = _write_probe(root, "probe", PROBE)
    sources = program(form, position, probe.as_posix())
    _write_sources(root, sources)
    monkeypatch.chdir(root)
    with caplog.at_level(logging.ERROR):
        result = _public_run(_public_run_files(root, {name: probe for name in COMMANDS}))
    listing = "\n".join(f"--- {path}\n{text}" for path, text in sources.items())
    return result, _DIAGNOSTIC_CODE.findall(caplog.text), _log(probe), listing


def _rule_cells() -> list:
    return [pytest.param(form, position, id=f"{form}/{position}") for form, position in cells() if (form, position) in RULES]


def _runnable() -> list:
    params = []
    for form, position in cells():
        if (form, position) in SKIPPED or (form, position) in RULES:
            continue
        defect = KNOWN_DEFECTS.get((form, position))
        marks = (
            [pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"known defect {defect}: {DEFECTS[defect]}")]
            if defect
            else []
        )
        params.append(pytest.param(form, position, id=f"{form}/{position}", marks=marks))
    return params


def test_every_cell_has_exactly_one_classification(capsys: pytest.CaptureFixture) -> None:
    tables = {"skipped": SKIPPED, "rule": RULES, "known defect": KNOWN_DEFECTS}
    found = {cell: [name for name, table in tables.items() if cell in table] or ["working"] for cell in cells()}
    counts = Counter(kind for kinds in found.values() for kind in kinds)
    with capsys.disabled():
        print(
            f"\ntotality matrix: {counts['rule']} rule, {counts['working']} working, "
            f"{counts['known defect']} known defect ({counts['skipped']} skipped of {len(found)})"
        )

    assert (
        {cell: kinds for cell, kinds in found.items() if len(kinds) != 1},
        {cell for table in tables.values() for cell in table} - set(found),
        set(KNOWN_DEFECTS.values()) - set(DEFECTS),
        set(RULES.values()) - RESTRICTION_CODES,
    ) == ({}, set(), set(), set())


@pytest.mark.parametrize(("form", "position"), _rule_cells())
def test_rule_cell_is_rejected_by_a_named_typecheck_restriction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, form: str, position: str
) -> None:
    result, codes, calls, listing = _run(tmp_path, monkeypatch, caplog, form, position)

    assert (result.exit_code, codes[:1], [code in RESTRICTION_CODES for code in codes[:1]], calls) == (
        2,
        [RULES[form, position]],
        [True],
        [],
    ), listing


@pytest.mark.parametrize(("form", "position"), _runnable())
def test_cell_returns_its_value_with_its_ordered_command_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, form: str, position: str
) -> None:
    result, codes, calls, listing = _run(tmp_path, monkeypatch, caplog, form, position)
    restricted = [code for code in codes if code in RESTRICTION_CODES]
    if restricted:
        pytest.fail(f"typecheck rejects this cell with {restricted[0]}: classify it as a rule\n{listing}")
    defect = KNOWN_DEFECTS.get((form, position))
    failure = (result.exit_code, codes[:1])
    if defect and result.exit_code != 0 and failure not in [(2, [code]) for code in DEFECT_CODES[defect]]:
        pytest.fail(f"known defect {defect}: expected exit 2 with {sorted(DEFECT_CODES[defect])}, got {failure}\n{listing}")

    assert (result.exit_code, dict(result.workflow_outputs), calls) == (0, *expected(form, position)), listing
