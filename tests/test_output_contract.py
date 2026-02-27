"""Tests for deterministic artifact output contracts."""

from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
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
        {"name": "review_outcome", "path": "state/decision.txt", "type": "enum", "allowed": ["APPROVE", "REVISE"]},
        {"name": "failure_count", "path": "state/count.txt", "type": "integer"},
        {"name": "quality_score", "path": "state/score.txt", "type": "float"},
        {"name": "approved_flag", "path": "state/approved.txt", "type": "bool"},
        {
            "name": "plan_path",
            "path": "state/plan_pointer.txt",
            "type": "relpath",
            "under": "docs/plans",
            "must_exist_target": True,
        },
    ]

    artifacts = validate_expected_outputs(specs, workspace=tmp_path)
    assert artifacts == {
        "review_outcome": "APPROVE",
        "failure_count": 7,
        "quality_score": 0.82,
        "approved_flag": True,
        "plan_path": "docs/plans/plan-a.md",
    }


def test_validate_expected_outputs_ignores_guidance_fields(tmp_path: Path):
    """Guidance annotations do not change runtime parsing semantics."""
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "decision.txt").write_text("APPROVE\n")
    specs = [{
        "name": "review_outcome",
        "path": "state/decision.txt",
        "type": "enum",
        "allowed": ["APPROVE", "REVISE"],
        "description": "Final review gate decision.",
        "format_hint": "Uppercase token only.",
        "example": "APPROVE",
    }]

    artifacts = validate_expected_outputs(specs, workspace=tmp_path)
    assert artifacts == {"review_outcome": "APPROVE"}


def test_validate_expected_outputs_missing_file_raises_violation(tmp_path: Path):
    """Missing required output file returns a contract violation."""
    specs = [{"name": "decision", "path": "state/decision.txt", "type": "enum", "allowed": ["APPROVE"]}]

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(specs, workspace=tmp_path)

    assert any(v["type"] == "missing_output_file" for v in exc_info.value.violations)


def test_validate_expected_outputs_invalid_enum_raises_violation(tmp_path: Path):
    """Enum validation fails when file value is outside the allowed set."""
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "decision.txt").write_text("MAYBE\n")
    specs = [{"name": "decision", "path": "state/decision.txt", "type": "enum", "allowed": ["APPROVE", "REVISE"]}]

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(specs, workspace=tmp_path)

    assert any(v["type"] == "invalid_enum_value" for v in exc_info.value.violations)


def test_validate_expected_outputs_relpath_escape_or_under_violation(tmp_path: Path):
    """relpath outputs cannot escape workspace or declared under-root."""
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "plan_pointer.txt").write_text("../outside.md\n")

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(
            [{"name": "plan_pointer", "path": "state/plan_pointer.txt", "type": "relpath", "under": "docs/plans"}],
            workspace=tmp_path,
        )

    violation_types = {v["type"] for v in exc_info.value.violations}
    assert "path_escape" in violation_types or "outside_under_root" in violation_types


def test_validate_expected_outputs_relpath_symlink_escape_violation(tmp_path: Path):
    """Symlink targets escaping workspace are rejected by canonical path checks."""
    (tmp_path / "state").mkdir()
    (tmp_path / "artifacts").mkdir()
    outside_target = tmp_path.parent / "outside-target.md"
    outside_target.write_text("outside\n")
    link_path = tmp_path / "artifacts" / "link.md"
    link_path.symlink_to(outside_target)
    (tmp_path / "state" / "plan_pointer.txt").write_text("artifacts/link.md\n")

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(
            [{
                "name": "plan_path",
                "path": "state/plan_pointer.txt",
                "type": "relpath",
                "under": "artifacts",
                "must_exist_target": True,
            }],
            workspace=tmp_path,
        )

    assert any(v["type"] == "path_escape" for v in exc_info.value.violations)


def test_validate_expected_outputs_missing_non_required_file_is_allowed(tmp_path: Path):
    """Missing files are ignored when required is explicitly false."""
    specs = [{
        "name": "optional_plan",
        "path": "state/optional_plan_pointer.txt",
        "type": "relpath",
        "required": False,
    }]

    artifacts = validate_expected_outputs(specs, workspace=tmp_path)
    assert artifacts == {}


def test_validate_expected_outputs_rejects_non_strict_bool_tokens(tmp_path: Path):
    """Only true/false bool tokens are accepted."""
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "approved.txt").write_text("1\n")
    specs = [{"name": "approved_flag", "path": "state/approved.txt", "type": "bool"}]

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(specs, workspace=tmp_path)

    assert any(v["type"] == "invalid_bool" for v in exc_info.value.violations)


def test_validate_expected_outputs_rejects_duplicate_artifact_names(tmp_path: Path):
    """Explicit artifact names must be unique within a step contract."""
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "a.txt").write_text("1\n")
    (tmp_path / "state" / "b.txt").write_text("2\n")
    specs = [
        {"name": "value", "path": "state/a.txt", "type": "integer"},
        {"name": "value", "path": "state/b.txt", "type": "integer"},
    ]

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(specs, workspace=tmp_path)

    assert any(v["type"] == "duplicate_artifact_name" for v in exc_info.value.violations)


def test_validate_output_bundle_parses_supported_types(tmp_path: Path):
    """Bundle fields parse enum/int/float/bool/relpath into typed artifacts."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "plan-a.md").write_text("# plan\n")
    (tmp_path / "artifacts" / "work" / "summary.json").write_text(
        '{"decision":"APPROVE","failed_count":2,"score":0.91,"approved":true,"plan_path":"docs/plans/plan-a.md"}\n'
    )

    bundle = {
        "path": "artifacts/work/summary.json",
        "fields": [
            {"name": "review_outcome", "json_pointer": "/decision", "type": "enum", "allowed": ["APPROVE", "REVISE"]},
            {"name": "failure_count", "json_pointer": "/failed_count", "type": "integer"},
            {"name": "quality_score", "json_pointer": "/score", "type": "float"},
            {"name": "approved_flag", "json_pointer": "/approved", "type": "bool"},
            {
                "name": "plan_path",
                "json_pointer": "/plan_path",
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            },
        ],
    }

    artifacts = validate_output_bundle(bundle, workspace=tmp_path)
    assert artifacts == {
        "review_outcome": "APPROVE",
        "failure_count": 2,
        "quality_score": 0.91,
        "approved_flag": True,
        "plan_path": "docs/plans/plan-a.md",
    }


def test_validate_output_bundle_missing_file_raises_violation(tmp_path: Path):
    """Missing output_bundle file returns a contract violation."""
    bundle = {
        "path": "artifacts/work/summary.json",
        "fields": [{"name": "decision", "json_pointer": "/decision", "type": "enum", "allowed": ["APPROVE"]}],
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(bundle, workspace=tmp_path)

    assert any(v["type"] == "missing_bundle_file" for v in exc_info.value.violations)


def test_validate_output_bundle_invalid_json_raises_violation(tmp_path: Path):
    """Invalid bundle JSON fails deterministic contract parsing."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "summary.json").write_text("{invalid}\n")
    bundle = {
        "path": "artifacts/work/summary.json",
        "fields": [{"name": "decision", "json_pointer": "/decision", "type": "enum", "allowed": ["APPROVE"]}],
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(bundle, workspace=tmp_path)

    assert any(v["type"] == "invalid_json_document" for v in exc_info.value.violations)


def test_validate_output_bundle_missing_pointer_raises_violation(tmp_path: Path):
    """Missing JSON pointer path in bundle fails validation."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "summary.json").write_text('{"decision":"APPROVE"}\n')
    bundle = {
        "path": "artifacts/work/summary.json",
        "fields": [{"name": "decision", "json_pointer": "/missing", "type": "enum", "allowed": ["APPROVE"]}],
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(bundle, workspace=tmp_path)

    assert any(v["type"] == "json_pointer_not_found" for v in exc_info.value.violations)


def test_validate_output_bundle_invalid_enum_raises_violation(tmp_path: Path):
    """Enum constraints apply to extracted output_bundle field values."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "summary.json").write_text('{"decision":"MAYBE"}\n')
    bundle = {
        "path": "artifacts/work/summary.json",
        "fields": [{"name": "decision", "json_pointer": "/decision", "type": "enum", "allowed": ["APPROVE"]}],
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(bundle, workspace=tmp_path)

    assert any(v["type"] == "invalid_enum_value" for v in exc_info.value.violations)


def test_validate_output_bundle_relpath_constraints_are_enforced(tmp_path: Path):
    """relpath extraction from bundles cannot escape workspace or declared under root."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "summary.json").write_text('{"plan_path":"../outside.md"}\n')
    bundle = {
        "path": "artifacts/work/summary.json",
        "fields": [{"name": "plan_path", "json_pointer": "/plan_path", "type": "relpath", "under": "docs/plans"}],
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(bundle, workspace=tmp_path)

    violation_types = {v["type"] for v in exc_info.value.violations}
    assert "path_escape" in violation_types or "outside_under_root" in violation_types
