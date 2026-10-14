"""Integration tests for expected_outputs enforcement in workflow execution."""

from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import validate_output_bundle
from orchestrator.workflow.signatures import (
    WorkflowSignatureError,
    resolve_workflow_outputs,
)


def _structural_union_output_specs() -> dict[str, dict[str, object]]:
    common = {
        "projection_class": "union_workflow_boundary",
        "return_kind": "union",
        "union_output_group": "return__usage",
        "discriminant_output": "return__usage__variant",
    }
    return {
        "return__usage__variant": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["KNOWN", "UNKNOWN"],
            "from": {
                "ref": "root.steps.Produce.artifacts.return__usage__variant"
            },
            "projection": {
                **common,
                "field_role": "discriminant",
                "active_variants": ["KNOWN", "UNKNOWN"],
            },
        },
        "return__usage__amount": {
            "kind": "scalar",
            "type": "integer",
            "from": {
                "ref": "root.steps.Produce.artifacts.return__usage__amount"
            },
            "projection": {
                **common,
                "field_role": "variant",
                "active_variants": ["KNOWN"],
            },
        },
    }


def _top_level_union_output_specs() -> dict[str, dict[str, object]]:
    common = {
        "projection_class": "union_workflow_boundary",
        "return_kind": "union",
        "union_output_group": "return",
        "discriminant_output": "return__variant",
    }
    return {
        "return__variant": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["PRESENT", "ABSENT"],
            "from": {"ref": "root.steps.Produce.artifacts.return__variant"},
            "projection": {
                **common,
                "field_role": "discriminant",
                "active_variants": ["PRESENT", "ABSENT"],
            },
        },
        "return__value": {
            "kind": "scalar",
            "type": "integer",
            "from": {"ref": "root.steps.Produce.artifacts.return__value"},
            "projection": {
                **common,
                "field_role": "variant",
                "active_variants": ["PRESENT"],
            },
        },
    }


def test_workflow_output_export_preserves_root_workflow_boundary_carrier(
    tmp_path: Path,
) -> None:
    specs = {
        "return": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.Produce.artifacts.return"},
            "workflow_boundary": {"return_kind": "root"},
        }
    }
    state = {"steps": {"Produce": {"artifacts": {"return": "done"}}}}

    assert resolve_workflow_outputs(specs, state, tmp_path) == {
        "return": "done"
    }


def test_workflow_output_export_preserves_top_level_union_activity(
    tmp_path: Path,
) -> None:
    state = {
        "steps": {
            "Produce": {"artifacts": {"return__variant": "ABSENT"}}
        }
    }

    assert resolve_workflow_outputs(
        _top_level_union_output_specs(),
        state,
        tmp_path,
    ) == {"return__variant": "ABSENT"}


@pytest.mark.parametrize(
    ("artifacts", "expected"),
    (
        (
            {"return__usage__variant": "UNKNOWN"},
            {"return__usage__variant": "UNKNOWN"},
        ),
        (
            {
                "return__usage__variant": "KNOWN",
                "return__usage__amount": 7,
            },
            {
                "return__usage__variant": "KNOWN",
                "return__usage__amount": 7,
            },
        ),
    ),
    ids=("inactive-payload-omitted", "active-payload-exported"),
)
def test_workflow_output_export_obeys_structural_union_activity(
    tmp_path: Path,
    artifacts: dict[str, object],
    expected: dict[str, object],
) -> None:
    state = {"steps": {"Produce": {"artifacts": artifacts}}}

    assert resolve_workflow_outputs(
        _structural_union_output_specs(),
        state,
        tmp_path,
    ) == expected


def test_workflow_output_export_requires_active_structural_union_payload(
    tmp_path: Path,
) -> None:
    state = {
        "steps": {
            "Produce": {
                "artifacts": {"return__usage__variant": "KNOWN"},
            }
        }
    }

    with pytest.raises(WorkflowSignatureError) as exc_info:
        resolve_workflow_outputs(
            _structural_union_output_specs(),
            state,
            tmp_path,
        )

    assert exc_info.value.error["context"]["output"] == (
        "return__usage__amount"
    )
    assert exc_info.value.error["context"]["reason"] == "unresolved_source"


@pytest.mark.parametrize(
    "malformation",
    (
        "missing_discriminant",
        "ambiguous_discriminant",
        "wrong_discriminant_binding",
        "missing_group",
    ),
)
def test_workflow_output_export_rejects_malformed_structural_union_authority(
    tmp_path: Path,
    malformation: str,
) -> None:
    specs = _structural_union_output_specs()
    artifacts = {
        "return__usage__variant": "UNKNOWN",
        "return__usage__amount": 7,
    }
    if malformation == "missing_discriminant":
        specs.pop("return__usage__variant")
    elif malformation == "ambiguous_discriminant":
        specs["return__usage__other_variant"] = {
            **specs["return__usage__variant"],
            "from": {
                "ref": (
                    "root.steps.Produce.artifacts."
                    "return__usage__other_variant"
                )
            },
        }
        artifacts["return__usage__other_variant"] = "UNKNOWN"
    elif malformation == "wrong_discriminant_binding":
        specs["return__usage__amount"]["projection"] = {
            **specs["return__usage__amount"]["projection"],
            "discriminant_output": "return__usage__other_variant",
        }
    else:
        specs["return__usage__amount"]["projection"] = {
            key: value
            for key, value in specs["return__usage__amount"][
                "projection"
            ].items()
            if key != "union_output_group"
        }
    state = {"steps": {"Produce": {"artifacts": artifacts}}}

    with pytest.raises(WorkflowSignatureError) as exc_info:
        resolve_workflow_outputs(specs, state, tmp_path)

    assert exc_info.value.error["context"]["reason"] == (
        "invalid_union_projection"
    )


def test_workflow_output_export_rejects_unknown_structural_union_discriminant(
    tmp_path: Path,
) -> None:
    state = {
        "steps": {
            "Produce": {
                "artifacts": {
                    "return__usage__variant": "OTHER",
                    "return__usage__amount": 7,
                },
            }
        }
    }

    with pytest.raises(WorkflowSignatureError) as exc_info:
        resolve_workflow_outputs(
            _structural_union_output_specs(),
            state,
            tmp_path,
        )

    assert exc_info.value.error["context"]["reason"] == (
        "invalid_union_discriminant"
    )


def test_workflow_output_export_rejects_group_not_bound_to_discriminant_prefix(
    tmp_path: Path,
) -> None:
    specs = _structural_union_output_specs()
    for spec in specs.values():
        spec["projection"] = {
            **spec["projection"],
            "union_output_group": "wrong-group",
        }
    state = {
        "steps": {
            "Produce": {
                "artifacts": {"return__usage__variant": "UNKNOWN"}
            }
        }
    }

    with pytest.raises(WorkflowSignatureError) as exc_info:
        resolve_workflow_outputs(specs, state, tmp_path)

    assert exc_info.value.error["context"]["reason"] == (
        "invalid_union_projection"
    )


def test_workflow_output_export_rejects_non_object_projection_metadata(
    tmp_path: Path,
) -> None:
    specs = _structural_union_output_specs()
    for spec in specs.values():
        spec["projection"] = "union-workflow-boundary"
    state = {
        "steps": {
            "Produce": {
                "artifacts": {
                    "return__usage__variant": "UNKNOWN",
                    "return__usage__amount": 7,
                }
            }
        }
    }

    with pytest.raises(WorkflowSignatureError) as exc_info:
        resolve_workflow_outputs(specs, state, tmp_path)

    assert exc_info.value.error["context"] == {
        "scope": "workflow_outputs",
        "output": "return__usage__variant",
        "reason": "invalid_union_projection",
        "detail": "metadata_not_object",
    }


def test_bundle_guidance_is_runtime_neutral_for_value_validation(tmp_path: Path) -> None:
    bundle_path = tmp_path / "artifacts" / "work" / "decision.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text("true\n", encoding="utf-8")
    output_bundle = {
        "path": "artifacts/work/decision.json",
        "fields": [
            {
                "name": "decision",
                "json_pointer": "",
                "type": "bool",
                "description": "True only when approved.",
                "format_hint": "JSON boolean.",
                "example": True,
            }
        ],
    }

    assert validate_output_bundle(output_bundle, workspace=tmp_path) == {"decision": True}


# bundle-overrides-exit contract retired (contradicted by specs/io.md:44-48); current behavior owned by test_nonzero_exit_skips_output_bundle_validation below.
