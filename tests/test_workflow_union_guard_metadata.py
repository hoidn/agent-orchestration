"""Shared catalog owners retain the information needed for scoped union proofs."""

import pytest

from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    _WorkflowMappingValidator,
)


def _catalog(tmp_path, steps, *, version="2.29"):
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": version},
            workflow_path=tmp_path / "entry.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    return validator._build_scope_artifact_catalog(steps)


@pytest.mark.parametrize("version", ["2.28", "2.29"])
def test_materialized_explicit_projection_retains_group_and_activity(tmp_path, version):
    def contract(role, variants):
        return {
            "type": "enum" if role == "discriminant" else "string",
            **({"allowed": ["A", "B", "C"]} if role == "discriminant" else {}),
            "projection": {
                "projection_class": "union_workflow_boundary",
                "field_role": role,
                "union_output_group": "left",
                "discriminant_output": "left_tag",
                "active_variants": variants,
            },
        }

    outputs = _catalog(tmp_path, [{
        "name": "Final",
        "materialize_artifacts": {"values": [
            {"name": "left_tag", "source": {"literal": "A"},
             "contract": contract("discriminant", ["A", "B", "C"])},
            {"name": "left_text", "source": {"literal": "text"},
             "contract": contract("variant", ["A", "B"])},
        ]},
    }], version=version)["Final"]

    if version == "2.28":
        assert outputs["left_text"] == {"type": "string", "persisted": True, "allowed": None}
        assert outputs["left_tag"] == {"type": "enum", "persisted": True, "allowed": ["A", "B", "C"]}
        return

    assert outputs["left_tag"]["variant_role"] == "discriminant"
    assert outputs["left_tag"]["allowed"] == ["A", "B", "C"]
    assert outputs["left_text"]["variant_owner_step"] == "Final"
    assert outputs["left_text"]["union_output_group"] == "left"
    assert outputs["left_text"]["discriminant_output"] == "left_tag"
    assert outputs["left_text"]["active_variants"] == ["A", "B"]
    assert "variant_required" not in outputs["left_text"]


def test_selected_union_catalog_merges_partially_shared_field_activity(tmp_path):
    outputs = _catalog(tmp_path, [{
        "name": "Selected",
        "select_variant_output": {
            "discriminant": {"name": "tag", "type": "enum", "allowed": ["A", "B", "C"]},
            "variants": {
                "A": {"fields": [{"name": "text", "type": "string"}]},
                "B": {"fields": [{"name": "text", "type": "string"}]},
                "C": {"fields": [{"name": "other", "type": "string"}]},
            },
        },
    }])["Selected"]

    assert outputs["tag"]["active_variants"] == ["A", "B", "C"]
    assert outputs["text"]["variant_owner_step"] == "Selected"
    assert outputs["text"]["union_output_group"] == "tag"
    assert outputs["text"]["discriminant_output"] == "tag"
    assert outputs["text"]["active_variants"] == ["A", "B"]
    assert outputs["other"]["active_variants"] == ["C"]


@pytest.mark.parametrize("version", ["2.28", "2.29"])
def test_materializing_an_inherited_scalar_does_not_inherit_sparse_availability(tmp_path, version):
    outputs = _catalog(tmp_path, [
        {
            "name": "Source",
            "variant_output": {
                "discriminant": {"name": "tag", "type": "enum", "allowed": ["A", "B"]},
                "variants": {
                    "A": {"fields": [{"name": "text", "type": "string"}]},
                    "B": {"fields": []},
                },
            },
        },
        {
            "name": "Copy",
            "requires_variant": {"step": "Source", "value": "A"},
            "materialize_artifacts": {"values": [{
                "name": "copied_text",
                "source": {"ref": "root.steps.Source.artifacts.text"},
                "contract": {"inherit": "source"},
            }]},
        },
    ], version=version)["Copy"]

    assert outputs["copied_text"] == {"type": "string", "persisted": True, "allowed": None}
