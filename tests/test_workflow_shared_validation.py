"""Characterization for the shared mapping-to-bundle validation boundary."""

import ast
import builtins
import importlib
import json
from pathlib import Path
from types import MappingProxyType, ModuleType

import pytest

from orchestrator.exceptions import (
    ValidationError,
    ValidationSubjectRef,
    WorkflowValidationError,
)
from orchestrator.workflow.prompt_fragment_contract import (
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
    CompilerPromptFragmentContractV2,
    CompilerPromptFragmentOutputPosition,
    CompilerPromptFragmentRenderedSlot,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from tests.workflow_fixture_loader import WorkflowLoader
from tests.workflow_bundle_helpers import thaw_surface_workflow


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid"


def _validation_module():
    return importlib.import_module("orchestrator.workflow.validation")


def _module_ast(module_name: str) -> ast.Module:
    module = importlib.import_module(module_name)
    module_path = Path(module.__file__)
    return ast.parse(
        module_path.read_text(encoding="utf-8"),
        filename=str(module_path),
    )


def _canonical_from_module(node: ast.ImportFrom, module_name: str) -> str:
    if node.level == 0:
        return node.module or ""
    package = module_name.split(".")[:-1]
    retained = len(package) - (node.level - 1)
    prefix = package[: max(retained, 0)]
    if node.module:
        prefix.extend(node.module.split("."))
    return ".".join(prefix)


def _canonical_import_bindings(tree: ast.AST, module_name: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bindings[alias.asname] = alias.name
                else:
                    root = alias.name.split(".", 1)[0]
                    bindings[root] = root
        elif isinstance(node, ast.ImportFrom):
            imported_from = _canonical_from_module(node, module_name)
            for alias in node.names:
                if alias.name == "*":
                    continue
                local_name = alias.asname or alias.name
                bindings[local_name] = ".".join(
                    part for part in (imported_from, alias.name) if part
                )
    return bindings


def _canonical_imported_symbols(tree: ast.AST, module_name: str) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_from = _canonical_from_module(node, module_name)
            imported.update(
                ".".join(part for part in (imported_from, alias.name) if part)
                for alias in node.names
            )
    return imported


def _canonical_expression_symbol(
    node: ast.AST,
    bindings: dict[str, str],
) -> str | None:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        owner = _canonical_expression_symbol(node.value, bindings)
        return f"{owner}.{node.attr}" if owner else node.attr
    return None


def _canonical_called_symbols(
    tree: ast.AST,
    module_name: str,
    *,
    import_tree: ast.AST | None = None,
) -> list[str]:
    bindings = _canonical_import_bindings(import_tree or tree, module_name)
    return [
        symbol
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        if (symbol := _canonical_expression_symbol(node.func, bindings)) is not None
    ]


def _canonical_referenced_symbols(
    tree: ast.AST,
    module_name: str,
    *,
    import_tree: ast.AST | None = None,
) -> set[str]:
    bindings = _canonical_import_bindings(import_tree or tree, module_name)
    return {
        symbol
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
        if (symbol := _canonical_expression_symbol(node, bindings)) is not None
    }


def _patch_callable_aliases_by_identity(
    monkeypatch: pytest.MonkeyPatch,
    *,
    modules: tuple[ModuleType, ...],
    forbidden_objects: tuple[object, ...],
    replacement: object,
) -> set[str]:
    forbidden_ids = {id(value) for value in forbidden_objects}
    patched: set[str] = set()
    for module in modules:
        for name, value in tuple(vars(module).items()):
            if id(value) not in forbidden_ids:
                continue
            monkeypatch.setattr(module, name, replacement)
            patched.add(f"{module.__name__}.{name}")
    return patched


def _minimal_mapping(name: str = "shared-in-memory") -> dict:
    return {
        "version": "2.14",
        "name": name,
        "steps": [{"name": "Done", "command": ["echo", "done"]}],
    }


def _prompt_output_position_contracts() -> dict[str, object]:
    return {
        "expected_outputs": [
            {
                "name": "report_path",
                "path": "state/report_path.txt",
                "type": "relpath",
                "must_exist_target": True,
            }
        ],
        "output_bundle": {
            "path": "state/result.json",
            "fields": [
                {
                    "name": "approved",
                    "json_pointer": "/approved",
                    "type": "bool",
                }
            ],
        },
        "variant_output": {
            "path": "state/result.json",
            "discriminant": {
                "name": "decision",
                "json_pointer": "/decision",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            },
            "shared_fields": [
                {
                    "name": "owner",
                    "json_pointer": "/owner",
                    "type": "string",
                }
            ],
            "variants": {
                "APPROVE": {
                    "fields": [
                        {
                            "name": "approval_path",
                            "json_pointer": "/approval_path",
                            "type": "relpath",
                        }
                    ]
                },
                "REVISE": {
                    "fields": [
                        {
                            "name": "reason",
                            "json_pointer": "/reason",
                            "type": "string",
                        }
                    ]
                },
            },
        },
        "select_variant_output": {},
    }


def _validate_prompt_output_position_contracts(
    tmp_path: Path,
    contract_names: tuple[str, ...],
    *,
    contracts: dict[str, object] | None = None,
    compiler_contract: CompilerPromptFragmentContractV2 | None = None,
):
    validation = _validation_module()
    contracts = contracts or _prompt_output_position_contracts()
    mapping = _minimal_mapping("prompt-output-position-admission")
    mapping["version"] = "2.21"
    mapping["steps"][0]["id"] = "produce"
    mapping["steps"][0].update(
        {name: contracts[name] for name in contract_names}
    )
    if compiler_contract is not None:
        mapping["inputs"] = {
            "report_path": {"kind": "scalar", "type": "string"},
            "other_path": {"kind": "scalar", "type": "string"},
        }
        mapping["steps"][0]["provider"] = "provider"
        mapping["steps"][0].pop("command")
        mapping["steps"][0]["compiler_prompt_fragment_contract"] = compiler_contract
        mapping["steps"][0]["compiled_prompt_fragment_identity"] = (
            compiler_contract.compiled_prompt_fragment_identity
        )
    return validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=mapping,
            workflow_path=tmp_path / "prompt-output-position.fixture.json",
            frontend_kind="workflow_lisp" if compiler_contract is not None else None,
        ),
        options=_default_options(tmp_path),
    )


def _prompt_output_position_v2_carrier() -> CompilerPromptFragmentContractV2:
    expected_output = {
        "name": "report_path",
        "path": "${inputs.report_path}",
        "type": "string",
        "required": True,
    }
    return CompilerPromptFragmentContractV2(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
        template_utf8="{report_path}",
        rendered_slots=(
            CompilerPromptFragmentRenderedSlot(
                name="report_path",
                kind="path",
                static_type={
                    "kind": "path",
                    "name": "ReportPath",
                    "under": "state",
                    "must_exist_target": False,
                },
                renderer_id="posix-path-line",
                value_source={
                    "kind": "typed_binding_ref",
                    "binding": {"ref": "inputs.report_path"},
                },
                placeholder_ordinals=(0,),
            ),
        ),
        output_positions=(
            CompilerPromptFragmentOutputPosition(
                slot_name="report_path",
                output_role="required_string_file",
                expected_output=expected_output,
            ),
        ),
        compiled_prompt_fragment_identity="sha256:" + "a" * 64,
    )


@pytest.mark.parametrize(
    "structured_contract,field_location",
    [
        ("output_bundle", "field"),
        ("variant_output", "discriminant"),
        ("variant_output", "shared"),
        ("variant_output", "approve"),
        ("variant_output", "revise"),
    ],
)
def test_prompt_output_position_contract_rejects_every_structured_name_collision(
    tmp_path: Path,
    structured_contract: str,
    field_location: str,
) -> None:
    contracts = _prompt_output_position_contracts()
    if field_location == "field":
        contracts["output_bundle"]["fields"][0]["name"] = "report_path"
    elif field_location == "discriminant":
        contracts["variant_output"]["discriminant"]["name"] = "report_path"
    elif field_location == "shared":
        contracts["variant_output"]["shared_fields"][0]["name"] = "report_path"
    else:
        variant = "APPROVE" if field_location == "approve" else "REVISE"
        contracts["variant_output"]["variants"][variant]["fields"][0]["name"] = (
            "report_path"
        )

    result = _validate_prompt_output_position_contracts(
        tmp_path,
        ("expected_outputs", structured_contract),
        contracts=contracts,
    )

    assert result.bundle is None
    collision = next(
        error
        for error in result.errors
        if error.message.startswith("prompt_output_position_contract_collision:")
    )
    assert collision.subject_refs == (
        ValidationSubjectRef(
            subject_kind="expected_output",
            subject_name="produce::expected-output::report_path",
            workflow_name="prompt-output-position-admission",
        ),
        ValidationSubjectRef(
            subject_kind="step_id",
            subject_name="produce",
            workflow_name="prompt-output-position-admission",
        ),
    )


def test_prompt_output_position_collision_relates_structured_field_origin(
    tmp_path: Path,
) -> None:
    contracts = _prompt_output_position_contracts()
    contracts["output_bundle"]["fields"][0].update(
        {
            "name": "report_path",
            "source_map_subject": {
                "subject_kind": "output_bundle_field",
                "subject_name": "done::result::report_path",
                "workflow_name": "prompt-output-position-admission",
            },
        }
    )

    result = _validate_prompt_output_position_contracts(
        tmp_path,
        ("expected_outputs", "output_bundle"),
        contracts=contracts,
    )

    collision = next(
        error
        for error in result.errors
        if error.message.startswith("prompt_output_position_contract_collision:")
    )
    assert collision.subject_refs == (
        ValidationSubjectRef(
            subject_kind="expected_output",
            subject_name="produce::expected-output::report_path",
            workflow_name="prompt-output-position-admission",
        ),
        ValidationSubjectRef(
            subject_kind="output_bundle_field",
            subject_name="done::result::report_path",
            workflow_name="prompt-output-position-admission",
        ),
    )


def test_prompt_output_position_collision_retains_all_variant_field_lineage(
    tmp_path: Path,
) -> None:
    contracts = _prompt_output_position_contracts()
    shared_field = contracts["variant_output"]["shared_fields"][0]
    shared_field.update(
        {
            "name": "report_path",
            "source_map_subjects_by_variant": {
                variant: {
                    "subject_kind": "variant_output_field",
                    "subject_name": f"produce::result::{variant}::report_path",
                    "workflow_name": "prompt-output-position-admission",
                }
                for variant in ("APPROVE", "REVISE")
            },
        }
    )

    result = _validate_prompt_output_position_contracts(
        tmp_path,
        ("expected_outputs", "variant_output"),
        contracts=contracts,
    )

    collision = next(
        error
        for error in result.errors
        if error.message.startswith("prompt_output_position_contract_collision:")
    )
    assert collision.subject_refs == (
        ValidationSubjectRef(
            subject_kind="expected_output",
            subject_name="produce::expected-output::report_path",
            workflow_name="prompt-output-position-admission",
        ),
        ValidationSubjectRef(
            subject_kind="variant_output_field",
            subject_name="produce::result::APPROVE::report_path",
            workflow_name="prompt-output-position-admission",
        ),
        ValidationSubjectRef(
            subject_kind="variant_output_field",
            subject_name="produce::result::REVISE::report_path",
            workflow_name="prompt-output-position-admission",
        ),
    )


def test_prompt_output_position_contract_precedence_exposes_each_next_defect(
    tmp_path: Path,
) -> None:
    carrier = _prompt_output_position_v2_carrier()

    incompatible = _prompt_output_position_contracts()
    incompatible["expected_outputs"] = [
        dict(carrier.output_positions[0].expected_output)
    ]
    incompatible["output_bundle"]["fields"][0]["name"] = "report_path"
    incompatible_result = _validate_prompt_output_position_contracts(
        tmp_path,
        ("expected_outputs", "output_bundle", "variant_output"),
        contracts=incompatible,
        compiler_contract=carrier,
    )
    assert any(
        "mutually exclusive output contract fields" in error.message
        for error in incompatible_result.errors
    )
    assert not any(
        error.message.startswith("prompt_output_position_contract_collision:")
        for error in incompatible_result.errors
    )
    assert not any(
        error.message.startswith("prompt_output_position_contract_mismatch")
        for error in incompatible_result.errors
    )

    colliding = _prompt_output_position_contracts()
    colliding["expected_outputs"] = [
        dict(carrier.output_positions[0].expected_output)
    ]
    colliding["output_bundle"]["fields"][0]["name"] = "report_path"
    collision_result = _validate_prompt_output_position_contracts(
        tmp_path,
        ("expected_outputs", "output_bundle"),
        contracts=colliding,
        compiler_contract=carrier,
    )
    assert any(
        error.message.startswith("prompt_output_position_contract_collision:")
        for error in collision_result.errors
    )
    assert not any(
        error.message.startswith("prompt_output_position_contract_mismatch")
        for error in collision_result.errors
    )

    malformed_carrier = _prompt_output_position_contracts()
    malformed_carrier["expected_outputs"] = [
        {
            **dict(carrier.output_positions[0].expected_output),
            "path": "${inputs.other_path}",
        }
    ]
    mismatch_result = _validate_prompt_output_position_contracts(
        tmp_path,
        ("expected_outputs", "output_bundle"),
        contracts=malformed_carrier,
        compiler_contract=carrier,
    )
    assert not any(
        error.message.startswith("prompt_output_position_contract_collision:")
        for error in mismatch_result.errors
    )
    assert any(
        error.message.startswith("prompt_output_position_contract_mismatch")
        for error in mismatch_result.errors
    )


def _default_options(tmp_path: Path):
    validation = _validation_module()
    return validation.WorkflowMappingValidationOptions(
        workspace_root=tmp_path,
        boundary_validation_policy=validation.WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
    )


@pytest.mark.parametrize(
    "contract_names",
    [
        ("expected_outputs",),
        ("output_bundle",),
        ("variant_output",),
        ("expected_outputs", "output_bundle"),
        ("expected_outputs", "variant_output"),
    ],
)
def test_prompt_output_position_contract_admission_accepts_supported_sets(
    tmp_path: Path,
    contract_names: tuple[str, ...],
) -> None:
    result = _validate_prompt_output_position_contracts(tmp_path, contract_names)

    assert result.errors == ()
    assert result.bundle is not None


@pytest.mark.parametrize(
    "contract_names",
    [
        ("output_bundle", "variant_output"),
        ("expected_outputs", "output_bundle", "variant_output"),
        ("expected_outputs", "select_variant_output"),
        ("output_bundle", "select_variant_output"),
        ("variant_output", "select_variant_output"),
        ("expected_outputs", "output_bundle", "select_variant_output"),
        ("expected_outputs", "variant_output", "select_variant_output"),
        ("output_bundle", "variant_output", "select_variant_output"),
        (
            "expected_outputs",
            "output_bundle",
            "variant_output",
            "select_variant_output",
        ),
    ],
)
def test_prompt_output_position_contract_admission_rejects_other_sets(
    tmp_path: Path,
    contract_names: tuple[str, ...],
) -> None:
    result = _validate_prompt_output_position_contracts(tmp_path, contract_names)

    assert result.bundle is None
    assert any(
        "mutually exclusive output contract fields" in error.message
        for error in result.errors
    )


def _provider_policy_mapping(policy) -> dict:
    return {
        "version": "2.15",
        "name": "provider-policy-validation",
        "providers": {
            "impl": {
                "command": ["provider"],
                "input_mode": "stdin",
            }
        },
        "steps": [
            {
                "name": "Execute",
                "id": "execute",
                "provider": "impl",
                "provider_call_policy": policy,
            }
        ],
    }


def _validate_provider_policy(tmp_path: Path, policy, *, frontend_kind: str | None):
    validation = _validation_module()
    return validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=_provider_policy_mapping(policy),
            workflow_path=tmp_path / "provider-policy.orc",
            frontend_kind=frontend_kind,
        ),
        options=_default_options(tmp_path),
    )


@pytest.mark.parametrize(
    "policy",
    [
        None,
        "model",
        [],
        {},
        {"unknown": "x"},
        {"timeout_sec": "30"},
        {"model": 1},
        {"model": True},
        {"model": {"nested": "x"}},
        {"effort": ["high"]},
    ],
)
def test_provider_call_policy_rejects_non_closed_or_non_string_mappings(
    tmp_path: Path,
    policy,
) -> None:
    result = _validate_provider_policy(tmp_path, policy, frontend_kind="workflow_lisp")

    assert result.bundle is None
    assert any("provider_call_policy" in error.message for error in result.errors)


@pytest.mark.parametrize(
    "policy",
    [
        {"model": "gpt-5"},
        {"effort": "${inputs.effort}"},
        {"model": "${inputs.model}", "effort": "high"},
    ],
)
def test_provider_call_policy_accepts_closed_string_mapping_for_workflow_lisp(
    tmp_path: Path,
    policy,
) -> None:
    result = _validate_provider_policy(tmp_path, policy, frontend_kind="workflow_lisp")

    assert result.errors == ()
    assert result.bundle is not None
    assert dict(result.bundle.surface.steps[0].provider_call_policy or {}) == policy


def test_public_mapping_reservation_rejects_internal_provider_call_policy(
    tmp_path: Path,
) -> None:
    result = _validate_provider_policy(
        tmp_path,
        {"model": "gpt-5"},
        frontend_kind=None,
    )

    assert result.bundle is None
    assert any(
        "provider_call_policy" in error.message and "workflow_lisp" in error.message
        for error in result.errors
    )


def test_public_mapping_reservation_rejects_provider_call_policy_bindings(
    tmp_path: Path,
) -> None:
    validation = _validation_module()
    mapping = _provider_policy_mapping({"model": "gpt-5"})
    del mapping["steps"][0]["provider_call_policy"]
    mapping["providers"]["impl"]["call_policy_bindings"] = {
        "model": {"target_param": "model"}
    }
    result = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=mapping,
            workflow_path=tmp_path / "provider-policy.fixture.json",
        ),
        options=_default_options(tmp_path),
    )

    assert result.bundle is None
    assert any("call_policy_bindings" in error.message for error in result.errors)


def test_shared_validation_builds_bundle_from_in_memory_mapping(tmp_path: Path) -> None:
    validation = _validation_module()
    result = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=_minimal_mapping(),
            workflow_path=tmp_path / "never-read.fixture.json",
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


def test_shared_validation_target_dsl_supports_2_21_as_latest_closed_version() -> None:
    validation = _validation_module()

    assert "2.20" in validation.DEFAULT_SUPPORTED_VERSIONS
    assert "2.21" in validation.DEFAULT_SUPPORTED_VERSIONS
    assert validation.DEFAULT_VERSION_ORDER[-2:] == ("2.20", "2.21")


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


def test_shared_validation_has_no_authored_file_reads(
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


def test_shared_private_validator_is_not_a_workflow_lisp_frontend_dependency() -> None:
    validation = _validation_module()
    lowering_source = Path(
        importlib.import_module("orchestrator.workflow_lisp.lowering.core").__file__
    ).read_text(
        encoding="utf-8"
    )

    assert not hasattr(validation, "WorkflowMappingValidator")
    assert "_WorkflowMappingValidator" not in lowering_source


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

    dedicated_result = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=generated_mapping,
            workflow_path=tmp_path / "generated.fixture.json",
        ),
        options=validation.WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                validation.WorkflowBoundaryValidationPolicy.DEDICATED_RUNTIME_PROOF
            ),
        ),
    )
    assert dedicated_result.errors == ()
    assert dedicated_result.bundle is not None
    assert [step.kind.value for step in dedicated_result.bundle.surface.steps] == [
        "pure_projection"
    ]

    public_result = validation.validate_workflow_mapping(
        validation.WorkflowMappingBuildRequest(
            authored_mapping=generated_mapping,
            workflow_path=tmp_path / "generated.fixture.json",
        ),
        options=_default_options(tmp_path),
    )
    assert public_result.bundle is None
    assert any(
        "compiler-generated only" in error.message for error in public_result.errors
    )


def test_shared_validation_rejects_imported_bundles_and_resolver_together(tmp_path: Path) -> None:
    validation = _validation_module()
    sentinel = MappingProxyType({})
    request = validation.WorkflowMappingBuildRequest(
        authored_mapping=_minimal_mapping(),
        workflow_path=tmp_path / "workflow.fixture.json",
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


def test_shared_validation_contract_projects_json_fixture_bundle(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.fixture.json"
    workflow_path.write_text(
        json.dumps(
            {
                "version": "2.14",
                "name": "shared-validation-json",
                "inputs": {
                    "state_root": {"type": "relpath", "under": "state"},
                    "steering_path": {
                        "type": "relpath",
                        "under": "docs",
                        "must_exist_target": True,
                    },
                    "design_path": {
                        "type": "relpath",
                        "under": "docs/plans",
                        "must_exist_target": True,
                    },
                },
                "steps": [
                    {
                        "name": "MaterializeInputs",
                        "id": "materialize_inputs",
                        "materialize_artifacts": {
                            "input_values": [
                                {
                                    "names": ["steering_path", "design_path"],
                                    "contract": "inherit",
                                    "pointer_template": (
                                        "${inputs.state_root}/{name}.txt"
                                    ),
                                }
                            ]
                        },
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    surface = thaw_surface_workflow(bundle)
    stable_ids = ("root.materialize_inputs",)

    assert (bundle.surface.name, bundle.surface.version) == (
        "shared-validation-json",
        "2.14",
    )
    assert (
        bundle.core_workflow_ast.schema_version,
        bundle.core_workflow_ast.workflow_name,
    ) == ("core_workflow_ast.v1", "shared-validation-json")
    assert bundle.semantic_ir.schema_version == "workflow_semantic_ir.v1"
    assert tuple(sorted(bundle.semantic_ir.workflows)) == ("shared-validation-json",)
    assert (bundle.ir.schema_version, bundle.ir.name) == (
        "workflow_executable_ir.v1",
        "shared-validation-json",
    )
    assert tuple(sorted(bundle.ir.nodes)) == stable_ids
    assert (bundle.runtime_plan.schema_version, bundle.runtime_plan.workflow_name) == (
        "workflow_runtime_plan.v1",
        "shared-validation-json",
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


def test_workflow_lisp_has_one_private_shared_mapping_validation_authority() -> None:
    validation_module = "orchestrator.workflow.validation"
    lowering_module = "orchestrator.workflow_lisp.lowering.core"
    validation_tree = _module_ast("orchestrator.workflow.validation")
    lowering_tree = _module_ast("orchestrator.workflow_lisp.lowering.core")

    validation_imports = _canonical_imported_symbols(
        validation_tree,
        validation_module,
    )
    lowering_imports = _canonical_imported_symbols(lowering_tree, lowering_module)
    assert not any(
        symbol == "yaml" or symbol.startswith("yaml.")
        for symbol in validation_imports
    )
    assert not any(
        symbol == "orchestrator.loader"
        or symbol.startswith("orchestrator.loader.")
        for symbol in validation_imports
    )
    assert not any(
        symbol == "yaml" or symbol.startswith("yaml.")
        for symbol in lowering_imports
    )
    assert not any(
        symbol == "orchestrator.loader"
        or symbol.startswith("orchestrator.loader.")
        for symbol in lowering_imports
    )

    lowering_symbols = _canonical_imported_symbols(
        lowering_tree,
        lowering_module,
    ) | _canonical_referenced_symbols(lowering_tree, lowering_module)
    assert not any(
        symbol == "_WorkflowMappingValidator"
        or symbol.endswith("._WorkflowMappingValidator")
        for symbol in lowering_symbols
    )

    lowering_entry = next(
        node
        for node in lowering_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_validate_one_lowered_workflow"
    )
    validator_entry = f"{validation_module}.validate_workflow_mapping"
    builder = "orchestrator.workflow.lowering.build_loaded_workflow_bundle"
    assert _canonical_called_symbols(
        lowering_entry,
        lowering_module,
        import_tree=lowering_tree,
    ).count(validator_entry) == 1
    assert builder not in _canonical_called_symbols(lowering_tree, lowering_module)

    shared_entry = next(
        node
        for node in validation_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "validate_workflow_mapping"
    )
    assert _canonical_called_symbols(
        shared_entry,
        validation_module,
        import_tree=validation_tree,
    ).count(builder) == 1
    assert _canonical_called_symbols(validation_tree, validation_module).count(builder) == 1


def test_ast_authority_helpers_resolve_aliases_and_qualified_attributes() -> None:
    tree = ast.parse(
        "import json as document_parser\n"
        "import orchestrator.workflow.validation as shared\n"
        "from orchestrator.workflow.lowering import "
        "build_loaded_workflow_bundle as assemble\n"
        "document_parser.loads(payload)\n"
        "shared._WorkflowMappingValidator(request, options)\n"
        "assemble(surface)\n"
    )

    assert _canonical_imported_symbols(tree, "example.frontend") == {
        "json",
        "orchestrator.workflow.validation",
        "orchestrator.workflow.lowering.build_loaded_workflow_bundle",
    }
    assert _canonical_called_symbols(tree, "example.frontend") == [
        "json.loads",
        "orchestrator.workflow.validation._WorkflowMappingValidator",
        "orchestrator.workflow.lowering.build_loaded_workflow_bundle",
    ]


def test_callable_identity_trap_replaces_consumer_held_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer = ModuleType("test_consumer")

    def prohibited():
        return "prohibited"

    def replacement():
        return "replacement"

    consumer.renamed_import = prohibited

    patched = _patch_callable_aliases_by_identity(
        monkeypatch,
        modules=(consumer,),
        forbidden_objects=(prohibited,),
        replacement=replacement,
    )

    assert patched == {"test_consumer.renamed_import"}
    assert consumer.renamed_import() == "replacement"


@pytest.mark.parametrize(
    ("validator_attribute", "option_attribute", "default_name"),
    (
        ("SUPPORTED_VERSIONS", "supported_versions", "DEFAULT_SUPPORTED_VERSIONS"),
        ("VERSION_ORDER", "version_order", "DEFAULT_VERSION_ORDER"),
        (
            "SUPPORTED_OUTPUT_TYPES",
            "supported_output_types",
            "DEFAULT_SUPPORTED_OUTPUT_TYPES",
        ),
        (
            "PRIVATE_COLLECTION_OUTPUT_TYPES",
            "private_collection_output_types",
            "DEFAULT_PRIVATE_COLLECTION_OUTPUT_TYPES",
        ),
        (
            "STRING_CONTRACT_VERSION",
            "string_contract_version",
            "DEFAULT_STRING_CONTRACT_VERSION",
        ),
        ("ENV_VAR_PATTERN", "env_var_pattern", "DEFAULT_ENV_VAR_PATTERN"),
        ("INPUT_REF_PATTERN", "input_ref_pattern", "DEFAULT_INPUT_REF_PATTERN"),
    ),
)
def test_shared_validator_policy_has_one_request_bound_authority(
    validator_attribute: str,
    option_attribute: str,
    default_name: str,
) -> None:
    validation_tree = _module_ast("orchestrator.workflow.validation")
    validator = next(
        node
        for node in validation_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "_WorkflowMappingValidator"
    )
    initializer = next(
        node
        for node in validator.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    bindings = {
        target.attr: (
            statement.value.value.id,
            statement.value.attr,
        )
        for statement in initializer.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
        and isinstance(statement.value, ast.Attribute)
        and isinstance(statement.value.value, ast.Name)
    }

    assert bindings[validator_attribute] == ("options", option_attribute)
    validator_references = _canonical_referenced_symbols(
        validator,
        "orchestrator.workflow.validation",
        import_tree=validation_tree,
    )
    assert not any(
        symbol == default_name
        or symbol.endswith(f".{default_name}")
        for symbol in validator_references
    )


def test_generated_step_admission_remains_derived_from_frontend_and_boundary_policy() -> None:
    validation_tree = _module_ast("orchestrator.workflow.validation")
    shared_entry = next(
        node
        for node in validation_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "validate_workflow_mapping"
    )
    admission = next(
        statement.value
        for statement in shared_entry.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "allow_generated_step_kinds"
            for target in statement.targets
        )
    )
    expected = ast.parse(
        'request.frontend_kind == "workflow_lisp" or '
        "options.boundary_validation_policy is "
        "WorkflowBoundaryValidationPolicy.DEDICATED_RUNTIME_PROOF",
        mode="eval",
    ).body

    assert ast.dump(admission, include_attributes=False) == ast.dump(
        expected,
        include_attributes=False,
    )


def test_persisted_dashboard_typed_surface_does_not_use_fresh_frontends_or_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.dashboard.projection import RunProjector
    from orchestrator.workflow.persisted_surface import PersistedWorkflowSurfaceGraph
    from tests.test_dashboard_compiled_workflow import (
        _scan_one,
        _write_real_imported_bundle_mix_run,
    )

    result, source_path, _state = _write_real_imported_bundle_mix_run(tmp_path)
    run = _scan_one(tmp_path)
    source_path = source_path.resolve(strict=False)
    manifest_path = result.manifest_path.resolve(strict=False)
    artifact_path = result.artifact_paths["persisted_workflow_surface"].resolve(
        strict=False
    )
    authoritative_paths = {manifest_path, artifact_path}
    required_reads: set[Path] = set()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("fresh workflow frontend or validation path was entered")

    definition_targets = (
        "orchestrator.workflow_lisp.build.build_frontend_bundle",
        "orchestrator.workflow_lisp.build.compile_stage3_entrypoint",
        "orchestrator.workflow_lisp.compiler.compile_stage3_entrypoint",
        "orchestrator.workflow_lisp.compiler.compile_stage3_module",
        "orchestrator.workflow_lisp.compiler.read_sexpr_file",
        "orchestrator.workflow_lisp.compiler.build_syntax_module",
        "orchestrator.workflow_lisp.compiler.expand_module_forms",
        "orchestrator.workflow_lisp.compiler.elaborate_definition_module",
        "orchestrator.workflow_lisp.compiler.elaborate_workflow_definitions",
        "orchestrator.workflow_lisp.compiler.validate_executable_workflow",
        "orchestrator.workflow_lisp.reader.read_sexpr_file",
        "orchestrator.workflow_lisp.syntax.build_syntax_module",
        "orchestrator.workflow_lisp.macros.expand_module_forms",
        "orchestrator.workflow_lisp.definitions.elaborate_definition_module",
        "orchestrator.workflow_lisp.workflows.elaborate_workflow_definitions",
        "orchestrator.workflow_lisp.lowering.core.read_sexpr_file",
        "orchestrator.workflow_lisp.lowering.core.build_syntax_module",
        "orchestrator.workflow_lisp.lowering.core.expand_module_forms",
        "orchestrator.workflow_lisp.lowering.core.elaborate_definition_module",
        "orchestrator.workflow_lisp.lowering.core.validate_workflow_mapping",
        "orchestrator.workflow.elaboration.elaborate_surface_workflow",
        "orchestrator.workflow.validation.elaborate_surface_workflow",
        "orchestrator.workflow.validation.validate_workflow_mapping",
        "orchestrator.workflow.lowering.build_loaded_workflow_bundle",
        "orchestrator.workflow.validation.build_loaded_workflow_bundle",
        "orchestrator.workflow.executable_ir.validate_executable_workflow",
        "orchestrator.workflow.lowering.validate_executable_workflow",
        "orchestrator.workflow.runtime_plan.derive_workflow_runtime_plan",
        "orchestrator.workflow.lowering.derive_workflow_runtime_plan",
    )

    def resolve_dotted_target(target: str) -> object:
        parts = target.split(".")
        for split_at in range(len(parts), 0, -1):
            try:
                value: object = importlib.import_module(".".join(parts[:split_at]))
            except ModuleNotFoundError:
                continue
            for attribute in parts[split_at:]:
                value = getattr(value, attribute)
            return value
        raise AssertionError(f"cannot resolve forbidden target {target}")

    forbidden_objects = tuple(resolve_dotted_target(target) for target in definition_targets)
    dashboard_consumers = tuple(
        importlib.import_module(module_name)
        for module_name in (
            "orchestrator.dashboard.compiled_workflow",
            "orchestrator.dashboard.models",
            "orchestrator.dashboard.projection",
            "orchestrator.dashboard.server",
            "orchestrator.cli.commands.dashboard",
        )
    )
    _patch_callable_aliases_by_identity(
        monkeypatch,
        modules=dashboard_consumers,
        forbidden_objects=forbidden_objects,
        replacement=forbidden,
    )
    for target in definition_targets:
        monkeypatch.setattr(target, forbidden)

    real_open = builtins.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes

    def resolved_path(value) -> Path | None:
        try:
            return Path(value).resolve(strict=False)
        except (TypeError, ValueError, OSError, RuntimeError):
            return None

    def record_authorized_read(value) -> None:
        resolved = resolved_path(value)
        if resolved == source_path:
            raise AssertionError("bound Workflow Lisp source was read")
        if resolved in authoritative_paths:
            required_reads.add(resolved)

    def guarded_open(file, *args, **kwargs):
        record_authorized_read(file)
        return real_open(file, *args, **kwargs)

    def guarded_read_text(path: Path, *args, **kwargs):
        record_authorized_read(path)
        return real_read_text(path, *args, **kwargs)

    def guarded_read_bytes(path: Path, *args, **kwargs):
        record_authorized_read(path)
        return real_read_bytes(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)

    detail = RunProjector().project_detail(run)

    structure = detail.workflow_structure
    assert isinstance(structure, PersistedWorkflowSurfaceGraph)
    assert structure.entry_workflow == "neurips/entry::orchestrate"
    assert set(structure.nodes) == {
        "neurips/entry::orchestrate",
        "neurips/helper::provider-attempt",
        "imported_selector::selector-run",
    }
    assert isinstance(structure.nodes, MappingProxyType)
    with pytest.raises(TypeError):
        structure.nodes["other"] = structure.entry_node  # type: ignore[index]
    assert required_reads == authoritative_paths
