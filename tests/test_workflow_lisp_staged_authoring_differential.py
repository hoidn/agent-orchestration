"""Differential corpus for Task 0b of the staged-workflow authoring plan: every program of
`tests/workflow_lisp_staged_authoring_differential_cases.py` (the task's shapes, their neighbours and the probe
programs of its review) against its build on `main` at `524ed71a`, and the programs the fixes newly build against
their pinned digest and the value of their bound spelling on `main`.

The three expectation files are written by the cases module's `__main__`, never by hand; its docstring gives the
commands. A program that built on `main` builds with the same closed program digest; a refusal keeps its codes,
except those the task changes: D2's `list_empty_type_context_required` of an empty list in a subject's argument
and D3's `procedure_call_unknown` now build, a recursive generic call in a serial map body is
`parametric_specialization_cycle`, and D5's `procedure_lowering_unresolved` is
`proc_ref_binding_parameter_unsupported`; a crash is either fixed and pinned or has the signature of a row in the
defect backlog's `KNOWN`. Every newly built program runs with the value and command log its bound spelling gives on
`main`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workflow_lisp_defect_backlog import KNOWN
from tests.workflow_lisp_staged_authoring_differential_cases import BOUND, CASES, observe, run_value

FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MAIN = json.loads((FIXTURES / "staged_authoring_differential_main.json").read_text())
PINS = json.loads((FIXTURES / "staged_authoring_differential_pins.json").read_text())
BOUND_VALUES = json.loads((FIXTURES / "staged_authoring_differential_bound_values.json").read_text())
CRASHES = ("crash", "traceback")
# (family, outcome on `main`, outcome on the tip): the refusals the task changes.
CHANGED_REFUSALS = {("d2", ("refused", "list_empty_type_context_required"), "builds"),
                    ("d3", ("refused", "procedure_call_unknown"), "builds"),
                    ("d3", ("refused", "procedure_call_unknown"), ("refused", "parametric_specialization_cycle")),
                    ("d5", ("refused", "procedure_lowering_unresolved"),
                     ("refused", "proc_ref_binding_parameter_unsupported"))}


def test_the_expectations_cover_every_case() -> None:
    assert (sorted(MAIN), set(PINS) <= set(MAIN), set(BOUND_VALUES) <= set(PINS)) == (sorted(CASES), True, True)


def _moved_as_allowed(case_id: str) -> bool:
    before, after = tuple(MAIN[case_id]), tuple(PINS[case_id])
    if before[0] in CRASHES:
        return True
    return (case_id.split("-")[0], before, after[0] if after[0] == "builds" else after) in CHANGED_REFUSALS


def test_only_crashes_and_the_changed_refusals_moved() -> None:
    assert sorted(case_id for case_id in PINS if not _moved_as_allowed(case_id)) == []


def test_every_crash_left_has_a_known_signature() -> None:
    left = {case_id: tuple(PINS.get(case_id, MAIN[case_id])) for case_id in CASES}

    assert {case_id: outcome for case_id, outcome in left.items()
            if outcome[0] in CRASHES and outcome not in set(KNOWN.values())} == {}


def test_every_newly_built_case_has_its_bound_value() -> None:
    newly_built = {case_id for case_id, outcome in PINS.items() if outcome[0] == "builds"}

    assert sorted(case_id for case_id in newly_built if BOUND_VALUES.get(case_id) is None) == []


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_case_keeps_its_main_outcome_or_its_pin(tmp_path: Path, case_id: str) -> None:
    assert observe(case_id, tmp_path / "case") == PINS.get(case_id, MAIN[case_id])


@pytest.mark.parametrize("case_id", sorted(case_id for case_id, value in BOUND_VALUES.items() if value is not None))
def test_newly_built_case_runs_like_its_bound_spelling_on_main(tmp_path: Path, case_id: str) -> None:
    assert (BOUND[case_id], run_value(case_id, tmp_path / "case")) == (BOUND[case_id], BOUND_VALUES[case_id])
