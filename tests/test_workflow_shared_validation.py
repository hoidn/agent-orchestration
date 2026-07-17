"""Characterization for the shared mapping-to-bundle validation boundary."""

from pathlib import Path

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from tests.workflow_bundle_helpers import thaw_surface_workflow


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid"


def test_shared_validation_contract_projects_yaml_bundle(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        'version: "2.14"\n'
        "name: shared-validation-yaml\n"
        "inputs:\n"
        "  state_root: {type: relpath, under: state}\n"
        "  steering_path: {type: relpath, under: docs, must_exist_target: true}\n"
        "  design_path: {type: relpath, under: docs/plans, must_exist_target: true}\n"
        "steps:\n"
        "  - name: MaterializeInputs\n"
        "    id: materialize_inputs\n"
        "    materialize_artifacts:\n"
        "      input_values:\n"
        "        - names: [steering_path, design_path]\n"
        "          contract: inherit\n"
        '          pointer_template: "${inputs.state_root}/{name}.txt"\n',
        encoding="utf-8",
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    surface = thaw_surface_workflow(bundle)
    stable_ids = ("root.materialize_inputs",)

    assert (bundle.surface.name, bundle.surface.version) == (
        "shared-validation-yaml",
        "2.14",
    )
    assert (
        bundle.core_workflow_ast.schema_version,
        bundle.core_workflow_ast.workflow_name,
    ) == ("core_workflow_ast.v1", "shared-validation-yaml")
    assert bundle.semantic_ir.schema_version == "workflow_semantic_ir.v1"
    assert tuple(sorted(bundle.semantic_ir.workflows)) == ("shared-validation-yaml",)
    assert (bundle.ir.schema_version, bundle.ir.name) == (
        "workflow_executable_ir.v1",
        "shared-validation-yaml",
    )
    assert tuple(sorted(bundle.ir.nodes)) == stable_ids
    assert (bundle.runtime_plan.schema_version, bundle.runtime_plan.workflow_name) == (
        "workflow_runtime_plan.v1",
        "shared-validation-yaml",
    )
    assert bundle.runtime_plan.ordered_node_ids == stable_ids
    assert tuple(sorted(bundle.projection.entries_by_node_id)) == stable_ids
    assert surface["steps"][0]["materialize_artifacts"] == {
        "values": [
            {
                "name": "steering_path",
                "source": {"input": "steering_path"},
                "contract": {"inherit": "source"},
                "pointer": {"path": "${inputs.state_root}/steering_path.txt"},
            },
            {
                "name": "design_path",
                "source": {"input": "design_path"},
                "contract": {"inherit": "source"},
                "pointer": {"path": "${inputs.state_root}/design_path.txt"},
            },
        ]
    }
    assert bundle.provenance.frontend_kind is None
    assert bundle.provenance.workflow_path == workflow_path.resolve()
    assert bundle.provenance.source_root == tmp_path.resolve()


def test_shared_validation_contract_projects_real_orc_compile(tmp_path: Path) -> None:
    source_path = FIXTURES / "defproc_inline.orc"

    result = compile_stage3_module(
        source_path,
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles["orchestrate"]

    assert result.lowering_schema_version == 2
    stable_ids = ("root.orchestrate__return",)
    assert (bundle.surface.name, bundle.surface.version) == ("orchestrate", "2.14")
    assert (
        bundle.core_workflow_ast.schema_version,
        bundle.core_workflow_ast.workflow_name,
    ) == ("core_workflow_ast.v1", "orchestrate")
    assert bundle.semantic_ir.schema_version == "workflow_semantic_ir.v1"
    assert tuple(sorted(bundle.semantic_ir.workflows)) == ("orchestrate",)
    assert (bundle.ir.schema_version, bundle.ir.name) == (
        "workflow_executable_ir.v1",
        "orchestrate",
    )
    assert tuple(sorted(bundle.ir.nodes)) == stable_ids
    assert (bundle.runtime_plan.schema_version, bundle.runtime_plan.workflow_name) == (
        "workflow_runtime_plan.v1",
        "orchestrate",
    )
    assert bundle.runtime_plan.ordered_node_ids == stable_ids
    assert tuple(sorted(bundle.projection.entries_by_node_id)) == stable_ids
    assert [(step.kind.value, step.step_id) for step in bundle.surface.steps] == [
        ("materialize_artifacts", stable_ids[0])
    ]
    assert bundle.provenance.frontend_kind == "workflow_lisp"
    assert bundle.provenance.workflow_path == source_path.resolve()


@pytest.mark.parametrize(
    ("version_line", "imports", "expected_message"),
    (
        (
            'version: "9.9"',
            "",
            "Unsupported version '9.9'",
        ),
        (
            "version: 214",
            "",
            "'version' field must be a string, got int",
        ),
        (
            'version: "2.14"',
            "imports:\n  child: ../child.yaml\n",
            "imports.child: asset path traversal outside the workflow source tree is not allowed",
        ),
    ),
)
def test_shared_validation_preserves_yaml_envelope_error_order(
    tmp_path: Path,
    version_line: str,
    imports: str,
    expected_message: str,
) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        f"{version_line}\n"
        "name: invalid-envelope\n"
        f"{imports}"
        "steps:\n"
        "  - name: Done\n"
        "    command: [echo, done]\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load_bundle(workflow_path)

    assert expected_message in exc_info.value.errors[0].message
