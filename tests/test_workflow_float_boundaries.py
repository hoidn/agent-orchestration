"""Numeric surface N6 and N7: a `Float` that enters a run at target 2.34 is finite.

Contract: docs/design/workflow_lisp_numeric_surface.md, rules N6 and N7 and
section 6; Task 4 of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md.

Programs run through the public entry (`run_workflow`). A command result comes
from a probe that copies `answer.json` verbatim into its result bundle, so each
test controls the exact JSON text; a provider result comes from a stand-in
provider executor that does the same. Target 2.33 is the control: it accepts
non-finite values as it does today (a known defect that stays), and the controls
pin what it writes to `state.json`.

The expected output file boundary is tested at its validator: Workflow Lisp
lowers an expected output file only as a `String` (a prompt output position), so
no `.orc` program declares a `Float` one.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import OutputContractError, validate_expected_outputs


# The input `x` reaches the command's argv; the second command runs only after the first result is accepted.

# The provider result is the workflow's result; the command after it runs only if the result is accepted.

# A Float field in a record inside a union variant inside a list. A list of records
# inside a union variant is refused by the compiler (`collection_element_type_unsupported`).

# A Float field of a union variant: a union result has a variant bundle contract.

# An opaque `Value` field: at 2.34 a non-finite number anywhere inside it is refused like a Float.


# Each row of N6, as the JSON text of the value, and the value as the refusal prints it.

# 17 significant digits, the smallest subnormal, and a negative zero.
FINITE = ["0.30000000000000004", "5e-324", "-0.0"]


def _bits(value: float) -> bytes:
    return struct.pack(">d", value)


def _same(value: float, printed: str) -> bool:
    expected = float(printed)
    return math.isnan(value) if math.isnan(expected) else _bits(value) == _bits(expected)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


# Target 2.34: each row of N6 is refused where it enters, naming the field.


# A JSON integer too large for a double: 2.33 fails with an uncaught `OverflowError`
# (a known defect that stays); 2.34 refuses it as the infinity it would read as.


# Target 2.34: a finite Float passes each boundary and arrives as the same double.


# Target 2.33, the control: non-finite values are accepted as today and reach state.json.


# The expected output file boundary, at its validator.

FILE_ROWS = {"NaN": "nan", "Infinity": "inf", "-Infinity": "-inf", "nan": "nan", "inf": "inf", "-inf": "-inf", "1e400": "inf"}


def _expected_output(root: Path, text: str, **kwargs) -> float:
    (root / "score.txt").write_text(text, encoding="utf-8")
    contract = [{"name": "score", "path": "score.txt", "type": "float"}]
    return validate_expected_outputs(contract, workspace=root, **kwargs)["score"]


@pytest.mark.parametrize("row", FILE_ROWS)
def test_finite_floats_refuse_a_non_finite_expected_output_file(tmp_path: Path, row: str) -> None:
    with pytest.raises(OutputContractError) as excinfo:
        _expected_output(tmp_path, row, finite_floats=True)

    (violation,) = excinfo.value.violations
    assert (violation["type"], violation["context"]) == (
        "float_not_finite", {"value": FILE_ROWS[row], "path": "score.txt"}
    )  # fmt: skip


@pytest.mark.parametrize("value", FINITE)
def test_finite_floats_pass_a_finite_expected_output_file_unchanged(tmp_path: Path, value: str) -> None:
    assert _same(_expected_output(tmp_path, value, finite_floats=True), value)


@pytest.mark.parametrize("row", FILE_ROWS)
def test_an_expected_output_file_keeps_todays_non_finite_values_by_default(tmp_path: Path, row: str) -> None:
    assert _same(_expected_output(tmp_path, row), FILE_ROWS[row])
