"""Tests for deterministic artifact output contracts."""

from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_expected_outputs,
)


def test_validate_expected_outputs_parses_supported_types(tmp_path: Path):
    """Parses enum/int/float/bool/relpath outputs and returns typed artifacts."""
    (tmp_path / "state").mkdir()
    (tmp_path / "docs" / "plans").mkdir(parents=True)

    (tmp_path / "state" / "decision.txt").write_text("APPROVE\n")
    (tmp_path / "state" / "count.txt").write_text("7\n")
    (tmp_path / "state" / "score.txt").write_text("0.82\n")
    (tmp_path / "state" / "approved.txt").write_text("true\n")
    (tmp_path / "state" / "plan_pointer.txt").write_text("docs/plans/plan-a.md\n")
    (tmp_path / "docs" / "plans" / "plan-a.md").write_text("# plan\n")

    specs = [
        {"path": "state/decision.txt", "type": "enum", "allowed": ["APPROVE", "REVISE"]},
        {"path": "state/count.txt", "type": "integer"},
        {"path": "state/score.txt", "type": "float"},
        {"path": "state/approved.txt", "type": "bool"},
        {
            "path": "state/plan_pointer.txt",
            "type": "relpath",
            "under": "docs/plans",
            "must_exist_target": True,
        },
    ]

    artifacts = validate_expected_outputs(specs, workspace=tmp_path)
    assert artifacts == {
        "decision": "APPROVE",
        "count": 7,
        "score": 0.82,
        "approved": True,
        "plan_pointer": "docs/plans/plan-a.md",
    }


def test_validate_expected_outputs_missing_file_raises_violation(tmp_path: Path):
    """Missing required output file returns a contract violation."""
    specs = [{"path": "state/decision.txt", "type": "enum", "allowed": ["APPROVE"]}]

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(specs, workspace=tmp_path)

    assert any(v["type"] == "missing_output_file" for v in exc_info.value.violations)


def test_validate_expected_outputs_invalid_enum_raises_violation(tmp_path: Path):
    """Enum validation fails when file value is outside the allowed set."""
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "decision.txt").write_text("MAYBE\n")
    specs = [{"path": "state/decision.txt", "type": "enum", "allowed": ["APPROVE", "REVISE"]}]

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(specs, workspace=tmp_path)

    assert any(v["type"] == "invalid_enum_value" for v in exc_info.value.violations)


def test_validate_expected_outputs_relpath_escape_or_under_violation(tmp_path: Path):
    """relpath outputs cannot escape workspace or declared under-root."""
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "plan_pointer.txt").write_text("../outside.md\n")

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(
            [{"path": "state/plan_pointer.txt", "type": "relpath", "under": "docs/plans"}],
            workspace=tmp_path,
        )

    violation_types = {v["type"] for v in exc_info.value.violations}
    assert "path_escape" in violation_types or "outside_under_root" in violation_types
