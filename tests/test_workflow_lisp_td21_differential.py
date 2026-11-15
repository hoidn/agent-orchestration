"""Differential corpus for defect backlog TD2, TD1 and D21: every program of
`tests/workflow_lisp_td21_differential_cases.py` against its outcome on `main` before the fixes, and the programs
the fixes newly build against their pinned digest and the value of their `let*`-bound spelling.

The three expectation files are written by the cases module's `__main__`, never by hand; its docstring gives the
commits and the commands. A program that built on `main` builds with the same closed program digest; a refusal
keeps its codes; a program the fixes newly build has the digest pinned from the branch tip; any other crash has the
signature of a row in the defect backlog's `KNOWN`. A sampled newly built program runs with the value and command
log its bound spelling gives on `main`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workflow_lisp_defect_backlog import KNOWN
from tests.workflow_lisp_td21_differential_cases import CASES, observe, run_value

FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MAIN = json.loads((FIXTURES / "td21_differential_main.json").read_text())
PINS = json.loads((FIXTURES / "td21_differential_pins.json").read_text())
BOUND_VALUES = {case_id: value for case_id, value in
                json.loads((FIXTURES / "td21_differential_bound_values.json").read_text()).items() if value is not None}


def test_the_expectations_cover_every_case() -> None:
    assert (sorted(MAIN), set(PINS) <= set(MAIN), set(BOUND_VALUES) <= set(PINS)) == (sorted(CASES), True, True)


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_case_keeps_its_main_outcome_or_its_pin(tmp_path: Path, case_id: str) -> None:
    before, after = MAIN[case_id], observe(case_id, tmp_path / "case")

    if before[0] in ("builds", "refused"):
        assert after == before
    elif case_id in PINS:
        assert after == PINS[case_id]
    elif after[0] in ("crash", "traceback"):
        assert tuple(after) in set(KNOWN.values())


@pytest.mark.parametrize("case_id", sorted(BOUND_VALUES))
def test_newly_built_case_runs_like_its_bound_spelling_on_main(tmp_path: Path, case_id: str) -> None:
    run, definitions = CASES[case_id]

    assert run_value(run, definitions, tmp_path / "case") == BOUND_VALUES[case_id]
