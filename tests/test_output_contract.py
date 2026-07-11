"""Tests for deterministic artifact output contracts."""

import json
from pathlib import Path
from types import MappingProxyType

import pytest
import orchestrator.contracts.output_contract as output_contract_module

from orchestrator.contracts.output_contract import (
    ContractViolation,
    OutputContractError,
    validate_variant_output_bundle,
    validate_output_bundle,
    validate_expected_outputs,
)
from orchestrator.exceptions import ValidationSubjectRef


def _variant_field_subject(variant: str, field_name: str) -> dict[str, str]:
    return {
        "subject_kind": "variant_output_field",
        "subject_name": f"execute::Decision::{variant}::{field_name}",
        "workflow_name": "demo/module::entry",
    }


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


def test_validate_contract_value_accepts_native_json_scalars_and_relpaths(tmp_path: Path):
    """Workflow-boundary contracts should validate both scalar JSON values and direct relpaths."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    (tmp_path / "docs" / "tasks" / "task-a.md").write_text("# task\n")

    assert output_contract_module.validate_contract_value(
        7,
        {"type": "integer"},
        workspace=tmp_path,
    ) == 7
    assert output_contract_module.validate_contract_value(
        True,
        {"type": "bool"},
        workspace=tmp_path,
    ) is True
    assert output_contract_module.validate_contract_value(
        "docs/tasks/task-a.md",
        {
            "type": "relpath",
            "under": "docs/tasks",
            "must_exist_target": True,
        },
        workspace=tmp_path,
    ) == "docs/tasks/task-a.md"


def test_validate_contract_value_accepts_json_string_list_contracts(tmp_path: Path):
    """Structured joins may carry collection values through JSON string payloads."""
    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "state-layout.md").write_text("# state layout\n")

    assert output_contract_module.validate_contract_value(
        '["state-layout.md"]',
        {
            "kind": "collection",
            "type": "list",
            "items": MappingProxyType({
                "type": "relpath",
                "under": "docs/design",
                "must_exist_target": True,
            }),
        },
        workspace=tmp_path,
    ) == ["docs/design/state-layout.md"]


def test_validate_contract_value_accepts_exact_and_empty_strings(tmp_path: Path):
    """String contracts preserve exact scalar values, including empty strings."""
    assert output_contract_module.validate_contract_value(
        "  keep exact whitespace  ",
        {"type": "string"},
        workspace=tmp_path,
    ) == "  keep exact whitespace  "
    assert output_contract_module.validate_contract_value(
        "",
        {"type": "string"},
        workspace=tmp_path,
    ) == ""


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


def test_validate_expected_outputs_preserves_exact_string_contents(tmp_path: Path):
    """type string reads exact file contents without trimming."""
    (tmp_path / "state").mkdir()
    raw_text = "  leading and trailing  \nsecond line\n"
    (tmp_path / "state" / "assistant.txt").write_text(raw_text, encoding="utf-8")

    specs = [{
        "name": "assistant_text",
        "path": "state/assistant.txt",
        "type": "string",
    }]

    artifacts = validate_expected_outputs(specs, workspace=tmp_path)
    assert artifacts == {"assistant_text": raw_text}


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


def test_validate_expected_outputs_relpath_basename_normalizes_under_root(tmp_path: Path):
    """Bare filename relpaths normalize under declared under-root when present."""
    (tmp_path / "state").mkdir()
    (tmp_path / "artifacts" / "review").mkdir(parents=True)
    (tmp_path / "state" / "code_review_path.txt").write_text("latest-review.md\n")
    (tmp_path / "artifacts" / "review" / "latest-review.md").write_text("ok\n")

    specs = [{
        "name": "code_review_path",
        "path": "state/code_review_path.txt",
        "type": "relpath",
        "under": "artifacts/review",
        "must_exist_target": True,
    }]

    artifacts = validate_expected_outputs(specs, workspace=tmp_path)
    assert artifacts == {"code_review_path": "artifacts/review/latest-review.md"}


def test_validate_expected_outputs_relpath_nested_value_still_requires_under_root(tmp_path: Path):
    """Only bare filenames auto-normalize; nested values still enforce under-root checks."""
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "code_review_path.txt").write_text("foo/latest-review.md\n")

    specs = [{
        "name": "code_review_path",
        "path": "state/code_review_path.txt",
        "type": "relpath",
        "under": "artifacts/review",
    }]

    with pytest.raises(OutputContractError) as exc_info:
        validate_expected_outputs(specs, workspace=tmp_path)

    assert any(v["type"] == "outside_under_root" for v in exc_info.value.violations)


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


def test_validate_variant_output_bundle_accepts_completed_variant(tmp_path: Path):
    """variant_output exposes the discriminant and only the selected variant fields."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "execution_report.md").write_text("# report\n", encoding="utf-8")
    bundle_path = tmp_path / "state" / "variant_bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps(
            {
                "implementation_state": "COMPLETED",
                "execution_report_path": "artifacts/work/execution_report.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    contract = {
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        },
        "variants": {
            "COMPLETED": {
                "fields": [
                    {
                        "name": "execution_report_path",
                        "json_pointer": "/execution_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
            "BLOCKED": {
                "fields": [
                    {
                        "name": "progress_report_path",
                        "json_pointer": "/progress_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
        },
    }

    artifacts = validate_variant_output_bundle(contract, workspace=tmp_path)
    assert artifacts == {
        "implementation_state": "COMPLETED",
        "execution_report_path": "artifacts/work/execution_report.md",
    }


def test_validate_variant_output_bundle_rejects_missing_active_variant_field_with_subject(tmp_path: Path):
    """variant_output requires fields declared by the selected variant."""
    bundle_path = tmp_path / "state" / "variant_bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps({"implementation_state": "COMPLETED"}) + "\n",
        encoding="utf-8",
    )

    contract = {
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        },
        "variants": {
            "COMPLETED": {
                "fields": [
                    {
                        "name": "execution_report_path",
                        "json_pointer": "/execution_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                        "source_map_subject": _variant_field_subject(
                            "COMPLETED", "execution_report_path"
                        ),
                    }
                ]
            },
            "BLOCKED": {
                "fields": [
                    {
                        "name": "progress_report_path",
                        "json_pointer": "/progress_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
        },
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_variant_output_bundle(contract, workspace=tmp_path)

    assert [
        {
            "type": violation["type"],
            "context": violation["context"],
            "subject_refs": violation["subject_refs"],
        }
        for violation in exc_info.value.violations
    ] == [
        {
            "type": "variant_required_field_missing",
            "context": {
                "path": "state/variant_bundle.json",
                "variant": "COMPLETED",
                "name": "execution_report_path",
                "json_pointer": "/execution_report_path",
            },
            "subject_refs": [
                _variant_field_subject("COMPLETED", "execution_report_path")
            ],
        }
    ]


def test_validate_variant_output_bundle_rejects_forbidden_variant_fields_with_subject(tmp_path: Path):
    """variant_output rejects fields from unselected variants."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "execution_report.md").write_text("# report\n", encoding="utf-8")
    (tmp_path / "artifacts" / "work" / "progress_report.md").write_text("# blocked\n", encoding="utf-8")
    bundle_path = tmp_path / "state" / "variant_bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps(
            {
                "implementation_state": "COMPLETED",
                "execution_report_path": "artifacts/work/execution_report.md",
                "progress_report_path": "artifacts/work/progress_report.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    contract = {
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        },
        "variants": {
            "COMPLETED": {
                "fields": [
                    {
                        "name": "execution_report_path",
                        "json_pointer": "/execution_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
            "BLOCKED": {
                "fields": [
                    {
                        "name": "progress_report_path",
                        "json_pointer": "/progress_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                        "source_map_subject": _variant_field_subject(
                            "BLOCKED", "progress_report_path"
                        ),
                    }
                ]
            },
        },
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_variant_output_bundle(contract, workspace=tmp_path)

    violation = next(
        violation
        for violation in exc_info.value.violations
        if violation["type"] == "variant_forbidden_field_present"
    )
    assert violation["subject_refs"] == [
        _variant_field_subject("BLOCKED", "progress_report_path")
    ]


def test_validate_variant_output_bundle_missing_shared_field_uses_selected_subject(tmp_path: Path):
    bundle_path = tmp_path / "state" / "variant_bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps({"implementation_state": "COMPLETED"}) + "\n",
        encoding="utf-8",
    )
    contract = {
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        },
        "shared_fields": [
            {
                "name": "report",
                "json_pointer": "/report",
                "type": "string",
                "source_map_subjects_by_variant": {
                    "COMPLETED": _variant_field_subject("COMPLETED", "report"),
                    "BLOCKED": _variant_field_subject("BLOCKED", "report"),
                },
            }
        ],
        "variants": {
            "COMPLETED": {"fields": []},
            "BLOCKED": {"fields": []},
        },
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_variant_output_bundle(contract, workspace=tmp_path)

    assert exc_info.value.violations[0]["subject_refs"] == [
        _variant_field_subject("COMPLETED", "report")
    ]


def test_validate_variant_output_bundle_type_invalid_uses_selected_field_subject(tmp_path: Path):
    bundle_path = tmp_path / "state" / "variant_bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps({"implementation_state": "COMPLETED", "attempts": "many"}) + "\n",
        encoding="utf-8",
    )
    contract = {
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        },
        "variants": {
            "COMPLETED": {
                "fields": [
                    {
                        "name": "attempts",
                        "json_pointer": "/attempts",
                        "type": "integer",
                        "source_map_subject": _variant_field_subject("COMPLETED", "attempts"),
                    }
                ]
            },
            "BLOCKED": {"fields": []},
        },
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_variant_output_bundle(contract, workspace=tmp_path)

    violation = exc_info.value.violations[0]
    assert violation["type"] == "variant_field_type_invalid"
    assert violation["subject_refs"] == [
        _variant_field_subject("COMPLETED", "attempts")
    ]


@pytest.mark.parametrize(
    "source_metadata",
    [None, {"subject_kind": "variant_output_field"}],
)
def test_validate_variant_output_bundle_subject_free_or_malformed_metadata_omits_subject_refs(
    tmp_path: Path,
    source_metadata: dict[str, str] | None,
):
    bundle_path = tmp_path / "state" / "variant_bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps({"implementation_state": "COMPLETED"}) + "\n",
        encoding="utf-8",
    )
    field_spec = {
        "name": "report",
        "json_pointer": "/report",
        "type": "string",
    }
    if source_metadata is not None:
        field_spec["source_map_subject"] = source_metadata
    contract = {
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED"],
        },
        "variants": {
            "COMPLETED": {
                "fields": [field_spec]
            }
        },
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_variant_output_bundle(contract, workspace=tmp_path)

    violation = exc_info.value.violations[0]
    assert set(violation) == {"type", "message", "context"}
    assert violation["type"] == "variant_required_field_missing"
    assert violation["context"] == {
        "path": "state/variant_bundle.json",
        "variant": "COMPLETED",
        "name": "report",
        "json_pointer": "/report",
    }


def test_contract_violation_variant_subject_serialization_is_stable_and_deduplicated():
    subject = ValidationSubjectRef(
        subject_kind="variant_output_field",
        subject_name="execute::Decision::COMPLETED::report",
        workflow_name="demo/module::entry",
    )

    serialized = ContractViolation(
        type="variant_required_field_missing",
        message="missing",
        context={},
        subject_refs=(subject, subject),
    ).to_dict()

    assert serialized["subject_refs"] == [
        _variant_field_subject("COMPLETED", "report")
    ]


def test_validate_variant_output_bundle_accepts_shared_fields(tmp_path: Path):
    """shared_fields are always exposed alongside the selected variant fields."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "execution_report.md").write_text("# report\n", encoding="utf-8")
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "approved-plan.md").write_text("# plan\n", encoding="utf-8")
    bundle_path = tmp_path / "state" / "variant_bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps(
            {
                "implementation_state": "COMPLETED",
                "plan_path": "docs/plans/approved-plan.md",
                "execution_report_path": "artifacts/work/execution_report.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    contract = {
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        },
        "shared_fields": [
            {
                "name": "plan_path",
                "json_pointer": "/plan_path",
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            }
        ],
        "variants": {
            "COMPLETED": {
                "fields": [
                    {
                        "name": "execution_report_path",
                        "json_pointer": "/execution_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
            "BLOCKED": {
                "fields": [
                    {
                        "name": "progress_report_path",
                        "json_pointer": "/progress_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
        },
    }

    artifacts = validate_variant_output_bundle(contract, workspace=tmp_path)
    assert artifacts == {
        "implementation_state": "COMPLETED",
        "plan_path": "docs/plans/approved-plan.md",
        "execution_report_path": "artifacts/work/execution_report.md",
    }


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


def test_validate_output_bundle_preserves_exact_json_string_values(tmp_path: Path):
    """Output bundle string fields preserve decoded JSON string values exactly."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    raw_text = "  session note  \nnext line"
    (tmp_path / "artifacts" / "work" / "summary.json").write_text(
        json.dumps({"assistant_text": raw_text}) + "\n",
        encoding="utf-8",
    )

    bundle = {
        "path": "artifacts/work/summary.json",
        "fields": [
            {"name": "assistant_text", "json_pointer": "/assistant_text", "type": "string"},
        ],
    }

    artifacts = validate_output_bundle(bundle, workspace=tmp_path)
    assert artifacts == {"assistant_text": raw_text}


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


def _root_result_field_subject() -> dict[str, str]:
    return {
        "subject_kind": "output_bundle_field",
        "subject_name": "entry__result::root-result::__result__",
        "workflow_name": "demo/module::entry",
    }


def test_validate_output_bundle_root_result_type_invalid_attaches_subject(tmp_path: Path):
    """A root __result__ value violation carries its output_bundle_field subject."""
    bundle_path = tmp_path / "state" / "result.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(json.dumps("nope") + "\n", encoding="utf-8")

    bundle = {
        "path": "state/result.json",
        "fields": [
            {
                "name": "__result__",
                "json_pointer": "",
                "type": "bool",
                "source_map_subject": _root_result_field_subject(),
            }
        ],
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(bundle, workspace=tmp_path)

    violation = exc_info.value.violations[0]
    assert violation["type"] == "invalid_bool"
    assert violation["subject_refs"] == [_root_result_field_subject()]


def test_validate_output_bundle_json_pointer_not_found_attaches_output_bundle_field_subject(
    tmp_path: Path,
):
    """Ordinary bundle field violations carry optional field lineage when present."""
    bundle_path = tmp_path / "state" / "bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(json.dumps({"other": 1}) + "\n", encoding="utf-8")

    bundle = {
        "path": "state/bundle.json",
        "fields": [
            {
                "name": "decision",
                "json_pointer": "/decision",
                "type": "string",
                "source_map_subject": _root_result_field_subject(),
            }
        ],
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(bundle, workspace=tmp_path)

    violation = exc_info.value.violations[0]
    assert violation["type"] == "json_pointer_not_found"
    assert violation["subject_refs"] == [_root_result_field_subject()]


def test_validate_output_bundle_subject_free_field_violation_omits_subject_refs(
    tmp_path: Path,
):
    """Bundles without lineage metadata keep their existing violation payload."""
    bundle_path = tmp_path / "state" / "result.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(json.dumps("nope") + "\n", encoding="utf-8")

    bundle = {
        "path": "state/result.json",
        "fields": [{"name": "__result__", "json_pointer": "", "type": "bool"}],
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(bundle, workspace=tmp_path)

    violation = exc_info.value.violations[0]
    assert violation["type"] == "invalid_bool"
    assert "subject_refs" not in violation


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


def test_validate_output_bundle_relpath_basename_normalizes_under_root(tmp_path: Path):
    """Bundle relpath bare filenames normalize under declared under-root."""
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "review").mkdir(parents=True)
    (tmp_path / "artifacts" / "review" / "latest-review.md").write_text("ok\n")
    (tmp_path / "artifacts" / "work" / "summary.json").write_text('{"review_path":"latest-review.md"}\n')

    bundle = {
        "path": "artifacts/work/summary.json",
        "fields": [{
            "name": "code_review_path",
            "json_pointer": "/review_path",
            "type": "relpath",
            "under": "artifacts/review",
            "must_exist_target": True,
        }],
    }

    artifacts = validate_output_bundle(bundle, workspace=tmp_path)
    assert artifacts == {"code_review_path": "artifacts/review/latest-review.md"}


def test_validate_output_bundle_relpath_nested_path_normalizes_under_root_when_target_exists(
    tmp_path: Path,
):
    """Nested under-root-relative values normalize when the required target already exists."""
    (tmp_path / "artifacts" / "work" / "runs").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "runs" / "report.md").write_text("ok\n")
    (tmp_path / "artifacts" / "work" / "summary.json").write_text('{"report_path":"runs/report.md"}\n')

    bundle = {
        "path": "artifacts/work/summary.json",
        "fields": [{
            "name": "report_path",
            "json_pointer": "/report_path",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        }],
    }

    artifacts = validate_output_bundle(bundle, workspace=tmp_path)
    assert artifacts == {"report_path": "artifacts/work/runs/report.md"}
