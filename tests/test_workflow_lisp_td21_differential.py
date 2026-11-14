"""Differential corpus for defect backlog TD2, TD1 and D21: every program of
`tests/workflow_lisp_td21_differential_cases.py` against its outcome on `main` at `99726a3d`, before the fixes.

The expectations in `tests/fixtures/workflow_lisp/td21_differential_main.json` were written by the cases module's
`__main__` run on an export of that commit, never by hand. A program that built there builds with the same
closed program digest; a refusal keeps its codes; a program that crashes crashes only with the signature of a
row in the defect backlog's `KNOWN`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workflow_lisp_defect_backlog import KNOWN
from tests.workflow_lisp_td21_differential_cases import CASES, observe

MAIN = json.loads((Path(__file__).parent / "fixtures" / "workflow_lisp" / "td21_differential_main.json").read_text())


def test_the_expectations_cover_every_case() -> None:
    assert sorted(MAIN) == sorted(CASES)


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_case_keeps_its_main_outcome_or_leaves_a_crash(tmp_path: Path, case_id: str) -> None:
    before, after = MAIN[case_id], observe(case_id, tmp_path / "case")

    if before[0] in ("builds", "refused"):
        assert after == before
    elif after[0] in ("crash", "traceback"):
        assert tuple(after) in set(KNOWN.values())
