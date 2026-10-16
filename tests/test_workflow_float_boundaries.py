"""Finite expected-output files retain exact finite doubles and refuse non-finite values."""

from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import OutputContractError, validate_expected_outputs


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
