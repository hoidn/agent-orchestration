"""Differential corpus for defect D22: every program of `tests/workflow_lisp_d22_differential_cases.py` against
its outcome on `main` at `c24fb97d`, before the fix (`d22_differential_main.json`, written by the cases module's
`__main__`, never by hand; its docstring gives the command).

A program that built on `main` builds with the same closed program digest; a refusal keeps its codes; a crash with
D22's signature is refused `loop_recur_contract_invalid`. There was no other crash.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.workflow_lisp_d22_differential_cases import CASES, observe

MAIN = json.loads((Path(__file__).parent / "fixtures" / "workflow_lisp" / "d22_differential_main.json").read_text())
D22 = ["crash", "AttributeError", "workflow_lisp/typecheck_structural_values.py:typecheck_structural_value_expr"]


def test_the_expectations_cover_every_case() -> None:
    assert sorted(MAIN) == sorted(CASES)


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_case_keeps_its_main_outcome_or_is_refused_where_it_crashed(tmp_path: Path, case_id: str) -> None:
    before = MAIN[case_id]

    assert observe(case_id, tmp_path / "case") == (["refused", "loop_recur_contract_invalid"] if before == D22 else before)
