"""Characterization for the shared mapping-to-bundle validation boundary."""

import ast
import builtins
import importlib
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

from orchestrator.exceptions import ValidationError, WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from tests.workflow_bundle_helpers import thaw_surface_workflow


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid"


def _validation_module():
    return importlib.import_module("orchestrator.workflow.validation")


def _minimal_mapping(name: str = "shared-in-memory") -> dict:
    return {
        "version": "2.14",
        "name": name,
        "steps": [{"name": "Done", "command": ["echo", "done"]}],
    }


def _default_options(tmp_path: Path):
    validation = _validation_module()
    return validation.WorkflowMappingValidationOptions(
        workspace_root=tmp_path,
        boundary_validation_policy=validation.WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
    )


def test_shared_validation_builds_bundle_from_in_memory_mapping(tmp_path: Path) -> None:
    validation = _validation_module()
    result = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=_minimal_mapping(),
            workflow_path=tmp_path / "never-read.yaml",
        ),
        options=_default_options(tmp_path),
    )

    assert result.errors == ()
    assert result.bundle is not None
    assert (result.bundle.surface.name, result.bundle.surface.version) == (
        "shared-in-memory",
        "2.14",
    )


def test_shared_validation_returns_structured_errors(tmp_path: Path) -> None:
    validation = _validation_module()
    result = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping={"version": "9.9", "name": "invalid", "steps": []},
            workflow_path=tmp_path / "invalid.orc",
            frontend_kind="workflow_lisp",
        ),
        options=_default_options(tmp_path),
    )

    assert result.bundle is None
    assert result.errors
    assert all(hasattr(error, "message") for error in result.errors)
    assert "Unsupported version '9.9'" in result.errors[0].message


def test_shared_validation_returns_bundle_construction_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validation = _validation_module()
    expected = ValidationError("lowering rejected the validated surface")

    def reject_bundle(*args, **kwargs):
        raise WorkflowValidationError([expected])

    monkeypatch.setattr(validation, "build_loaded_workflow_bundle", reject_bundle)
    result = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=_minimal_mapping(),
            workflow_path=tmp_path / "workflow.orc",
        ),
        options=_default_options(tmp_path),
    )

    assert result.bundle is None
    assert result.errors == (expected,)


def test_shared_validation_request_isolation(tmp_path: Path) -> None:
    validation = _validation_module()
    first_mapping = _minimal_mapping("first")
    first = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=first_mapping,
            workflow_path=tmp_path / "first.orc",
        ),
        options=_default_options(tmp_path),
    )
    first_mapping["name"] = "mutated-after-validation"
    second = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=_minimal_mapping("second"),
            workflow_path=tmp_path / "second.orc",
        ),
        options=_default_options(tmp_path),
    )

    assert first.bundle is not None and first.bundle.surface.name == "first"
    assert second.bundle is not None and second.bundle.surface.name == "second"
    assert first.errors == second.errors == ()


def test_shared_validation_parser_isolation_has_no_yaml_or_authored_file_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validation = _validation_module()
    tree = ast.parse(Path(validation.__file__).read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("authored file read")),
    )
    result = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=_minimal_mapping(),
            workflow_path=tmp_path / "missing.orc",
        ),
        options=_default_options(tmp_path),
    )

    assert "yaml" not in imported_roots
    assert result.bundle is not None


def test_shared_private_validator_is_not_a_frontend_dependency() -> None:
    validation = _validation_module()
    loader_source = Path(importlib.import_module("orchestrator.loader").__file__).read_text(
        encoding="utf-8"
    )

    assert not hasattr(validation, "WorkflowMappingValidator")
    assert "_WorkflowMappingValidator" not in loader_source


def test_shared_validation_generated_step_policy_uses_same_actual_mapping(
    tmp_path: Path,
) -> None:
    validation = _validation_module()
    lowered = compile_stage3_module(
        FIXTURES / "pure_expr_selector_action_projection.orc",
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=False,
        workspace_root=tmp_path,
    )
    generated_mapping = lowered.lowered_workflows[0].authored_mapping

    orc_result = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=generated_mapping,
            workflow_path=FIXTURES / "pure_expr_selector_action_projection.orc",
            frontend_kind="workflow_lisp",
        ),
        options=_default_options(tmp_path),
    )
    assert orc_result.errors == ()
    assert orc_result.bundle is not None
    assert [step.kind.value for step in orc_result.bundle.surface.steps] == [
        "pure_projection"
    ]

    yaml_path = tmp_path / "generated.yaml"
    yaml_path.write_text(
        yaml.safe_dump(dict(generated_mapping), sort_keys=False),
        encoding="utf-8",
    )
    dedicated_bundle = WorkflowLoader(
        tmp_path,
        boundary_validation_policy=(
            validation.WorkflowBoundaryValidationPolicy.DEDICATED_RUNTIME_PROOF
        ),
    ).load_bundle(yaml_path)
    assert [step.kind.value for step in dedicated_bundle.surface.steps] == [
        "pure_projection"
    ]

    with pytest.raises(WorkflowValidationError, match="compiler-generated only"):
        WorkflowLoader(
            tmp_path,
            boundary_validation_policy=(
                validation.WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ).load_bundle(yaml_path)


def test_shared_validation_rejects_imported_bundles_and_resolver_together(tmp_path: Path) -> None:
    validation = _validation_module()
    sentinel = MappingProxyType({})
    request = validation.WorkflowMappingBuildRequest(
        authored_mapping=_minimal_mapping(),
        workflow_path=tmp_path / "workflow.yaml",
        imported_bundles={"child": sentinel},
        import_resolver=lambda *args, **kwargs: validation.WorkflowImportResolutionResult({}),
    )

    result = validation.validate_workflow_mapping(request, options=_default_options(tmp_path))

    assert result.bundle is None
    assert result.errors == (
        ValidationError(
            "shared validation request cannot supply both imported_bundles and import_resolver"
        ),
    )


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


def test_orc_shared_validation_does_not_enter_legacy_yaml_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "orchestrator.loader.WorkflowLoader.__init__",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy YAML loader used")
        ),
    )
    monkeypatch.setattr(
        "orchestrator.loader.yaml.load",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("YAML parser used")
        ),
    )

    result = compile_stage3_module(
        FIXTURES / "defproc_inline.orc",
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.validated_bundles


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
