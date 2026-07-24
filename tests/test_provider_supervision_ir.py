"""Closed executable-IR contract tests for generated provider supervision."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
from types import MappingProxyType

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.workflow.core_ast import (
    CoreProviderSupervisionStep,
    build_core_workflow_ast,
    lower_core_workflow_ast,
    workflow_core_ast_to_json,
)
from orchestrator.workflow.executable_ir import (
    WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION,
    ExecutableContract,
    ExecutableNodeKind,
    ExecutableWorkflow,
    LeafExecutableNode,
    ProviderStepConfig,
    ProviderSupervisionMemberConfig,
    ProviderSupervisionStepConfig,
    StepCommonConfig,
    WorkflowRegion,
    validate_executable_workflow,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.provider_supervision.directive import (
    PROVIDER_STEERING_DIRECTIVE_TYPE_DESCRIPTOR,
    ProviderSteeringDirective,
    provider_steering_directive_type_descriptor,
)
from orchestrator.workflow.provider_supervision.models import (
    ProviderSupervisionObservation,
    ProviderSupervisionSourceOwnership,
)
from orchestrator.workflow.provider_supervision.paths import (
    ProviderSupervisionPaths,
    derive_provider_supervision_paths,
)
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow.surface_ast import (
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
)
from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    validate_workflow_mapping,
)


_STRING_TYPE = MappingProxyType({"kind": "primitive", "name": "String"})
_BOOL_TYPE = MappingProxyType({"kind": "primitive", "name": "Bool"})
def _contract(
    name: str,
    descriptor=_STRING_TYPE,
    *,
    kind: str = "scalar",
    value_type: str = "string",
) -> ExecutableContract:
    return ExecutableContract(
        name=name,
        kind=kind,
        value_type=value_type,
        definition=MappingProxyType({"type": descriptor}),
    )


def _settlement_payload():
    return MappingProxyType(
        {
            "pure_expr_schema_version": 1,
            "result_type": _STRING_TYPE,
            "bindings": MappingProxyType(
                {
                    "worker": MappingProxyType({"type": _STRING_TYPE}),
                    "supervisor": MappingProxyType(
                        {
                            "type": provider_steering_directive_type_descriptor()
                        }
                    ),
                }
            ),
            "expr": MappingProxyType({"kind": "binding", "name": "worker"}),
        }
    )


def _provider_supervision_config(
    *,
    node_id: str = "root.live",
) -> ProviderSupervisionStepConfig:
    worker = ProviderSupervisionMemberConfig(
        member_id="worker",
        provider_config=ProviderStepConfig(provider="worker-provider"),
        result_contract=_contract("worker_result"),
        timeout_sec=30,
    )
    supervisor = ProviderSupervisionMemberConfig(
        member_id="supervisor",
        provider_config=ProviderStepConfig(provider="supervisor-provider"),
        result_contract=_contract(
            "ProviderSteeringDirective",
            provider_steering_directive_type_descriptor(),
            kind="union",
            value_type="ProviderSteeringDirective",
        ),
        timeout_sec=20,
    )
    return ProviderSupervisionStepConfig(
        common=StepCommonConfig(timeout_sec=60),
        schema_version="provider_supervision.v1",
        node_id=node_id,
        worker=worker,
        supervisor=supervisor,
        observation=ProviderSupervisionObservation(
            observer_member_id="supervisor",
            observed_member_id="worker",
        ),
        settlement_payload=_settlement_payload(),
        settlement_result_contract=_contract("settlement_result"),
        max_steers=1,
        paths=derive_provider_supervision_paths(
            node_id=node_id,
            worker_member_id="worker",
            supervisor_member_id="supervisor",
        ),
        source_ownership=ProviderSupervisionSourceOwnership(
            form="source:form",
            worker_binding="source:worker",
            supervisor_binding="source:supervisor",
            observation="source:observation",
            settlement="source:settlement",
        ),
    )


def _executable_workflow(
    config: ProviderSupervisionStepConfig,
) -> tuple[ExecutableWorkflow, LeafExecutableNode]:
    node = LeafExecutableNode(
        node_id=config.node_id,
        step_id=config.node_id,
        presentation_name="Live",
        kind=ExecutableNodeKind.PROVIDER_SUPERVISION,
        region=WorkflowRegion.BODY,
        lexical_scope=("root", "live"),
        execution_config=config,
    )
    workflow = ExecutableWorkflow(
        schema_version=WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION,
        version="2.15",
        name="generated-live",
        provenance=WorkflowProvenance(
            workflow_path=Path("/tmp/generated.orc"),
            source_root=Path("/tmp"),
            frontend_kind="workflow_lisp",
        ),
        body_region=(node.node_id,),
        finalization_region=(),
        finalization_entry_node_id=None,
        nodes=MappingProxyType({node.node_id: node}),
    )
    return workflow, node


def test_provider_supervision_primitives_are_closed_immutable_and_canonical() -> None:
    observation = ProviderSupervisionObservation.from_dict(
        {"observer_member_id": "supervisor", "observed_member_id": "worker"}
    )
    ownership = ProviderSupervisionSourceOwnership.from_dict(
        {
            "form": "source:form",
            "worker_binding": "source:worker",
            "supervisor_binding": "source:supervisor",
            "observation": "source:observation",
            "settlement": "source:settlement",
        }
    )
    paths = derive_provider_supervision_paths(
        node_id="root.live",
        worker_member_id="worker",
        supervisor_member_id="supervisor",
    )
    directive = ProviderSteeringDirective.from_dict(
        {"variant": "STEER", "guidance": "Correct the result."}
    )

    assert observation.to_dict() == {
        "observer_member_id": "supervisor",
        "observed_member_id": "worker",
    }
    assert ownership.to_dict()["settlement"] == "source:settlement"
    assert ProviderSupervisionPaths.from_dict(paths.to_dict()) == paths
    assert directive.to_dict() == {
        "variant": "STEER",
        "guidance": "Correct the result.",
    }
    assert json.loads(directive.canonical_json()) == directive.to_dict()
    assert (
        PROVIDER_STEERING_DIRECTIVE_TYPE_DESCRIPTOR.to_dict()
        == provider_steering_directive_type_descriptor()
    )
    projected_descriptor = provider_steering_directive_type_descriptor()
    projected_descriptor["variants"].append({"name": "BAD", "fields": []})
    assert [
        variant["name"]
        for variant in provider_steering_directive_type_descriptor()["variants"]
    ] == ["CONTINUE", "STEER"]
    with pytest.raises(FrozenInstanceError):
        PROVIDER_STEERING_DIRECTIVE_TYPE_DESCRIPTOR.kind = "record"  # type: ignore[misc]
    assert paths.worker_fresh.turn_role == "worker_fresh"
    assert paths.worker_resume.turn_role == "worker_resume"
    assert paths.supervisor_directive.turn_role == "supervisor_directive"
    assert len(
        {
            paths.worker_fresh.evidence_relpath,
            paths.worker_resume.evidence_relpath,
            paths.supervisor_directive.evidence_relpath,
            paths.worker_fresh.provisional_bundle_relpath,
            paths.worker_resume.provisional_bundle_relpath,
            paths.supervisor_directive.provisional_bundle_relpath,
        }
    ) == 6
    assert all(
        not Path(path).is_absolute()
        for turn in (
            paths.worker_fresh,
            paths.worker_resume,
            paths.supervisor_directive,
        )
        for path in (turn.evidence_relpath, turn.provisional_bundle_relpath)
    )
    with pytest.raises(FrozenInstanceError):
        observation.observer_member_id = "worker"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "payload"),
    [
        (
            ProviderSupervisionObservation.from_dict,
            {
                "observer_member_id": "supervisor",
                "observed_member_id": "worker",
                "extra": True,
            },
        ),
        (
            ProviderSupervisionSourceOwnership.from_dict,
            {
                "form": "source:form",
                "worker_binding": "source:worker",
                "supervisor_binding": "source:supervisor",
                "observation": "source:observation",
            },
        ),
        (
            ProviderSteeringDirective.from_dict,
            {"variant": "CONTINUE", "guidance": "forbidden"},
        ),
        (
            ProviderSteeringDirective.from_dict,
            {"variant": "STEER", "guidance": ""},
        ),
        (
            ProviderSteeringDirective.from_dict,
            {"variant": "WAIT"},
        ),
    ],
)
def test_provider_supervision_primitives_reject_missing_extra_or_invalid_fields(
    factory,
    payload,
) -> None:
    with pytest.raises(ValueError):
        factory(payload)


def test_hand_built_provider_supervision_ir_is_closed_and_runtime_visible() -> None:
    config = _provider_supervision_config()
    workflow, node = _executable_workflow(config)

    validate_executable_workflow(workflow)
    payload = workflow_executable_ir_to_json(workflow)
    provider_supervision = payload["nodes"][node.node_id]["execution_config"]

    assert payload["schema_version"] == "workflow_executable_ir.v1"
    assert node.kind is ExecutableNodeKind.PROVIDER_SUPERVISION
    assert set(provider_supervision) == {
        "common",
        "schema_version",
        "node_id",
        "worker",
        "supervisor",
        "observation",
        "settlement_payload",
        "settlement_result_contract",
        "max_steers",
        "paths",
        "source_ownership",
    }
    assert provider_supervision["schema_version"] == "provider_supervision.v1"
    assert provider_supervision["worker"]["provider_config"]["provider"] == (
        "worker-provider"
    )
    assert provider_supervision["supervisor"]["provider_config"]["provider"] == (
        "supervisor-provider"
    )
    assert provider_supervision["worker"]["timeout_sec"] == 30
    assert provider_supervision["supervisor"]["timeout_sec"] == 20
    assert provider_supervision["max_steers"] == 1

    runtime = RuntimeStep(node=node, name=node.presentation_name, step_id=node.step_id)
    runtime_payload = dict(runtime)
    assert runtime_payload["timeout_sec"] == 60
    assert runtime_payload["provider_supervision"]["schema_version"] == (
        "provider_supervision.v1"
    )
    assert runtime_payload["provider_supervision"]["node_id"] == node.node_id
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert serialized == json.dumps(
        workflow_executable_ir_to_json(workflow),
        sort_keys=True,
        separators=(",", ":"),
    )
    assert all(
        forbidden not in serialized
        for forbidden in ("run_root", "live_target", "session_id")
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda config: replace(config, schema_version="provider_supervision.v2"),
        lambda config: replace(config, node_id="root.other"),
        lambda config: replace(config, max_steers=2),
        lambda config: replace(config, max_steers=True),
        lambda config: replace(
            config,
            worker=replace(config.worker, timeout_sec=0),
        ),
        lambda config: replace(
            config,
            supervisor=replace(config.supervisor, timeout_sec=True),
        ),
        lambda config: replace(
            config,
            worker=replace(
                config.worker,
                provider_config={"provider": "not-typed"},  # type: ignore[arg-type]
            ),
        ),
        lambda config: replace(
            config,
            supervisor=replace(
                config.supervisor,
                result_contract={"name": "not-typed"},  # type: ignore[arg-type]
            ),
        ),
        lambda config: replace(
            config,
            supervisor=replace(config.supervisor, member_id="worker"),
        ),
        lambda config: replace(
            config,
            observation=ProviderSupervisionObservation(
                observer_member_id="worker",
                observed_member_id="supervisor",
            ),
        ),
        lambda config: replace(
            config,
            paths=replace(
                config.paths,
                worker_resume=replace(
                    config.paths.worker_resume,
                    provisional_bundle_relpath="tampered/resume-result.json",
                ),
            ),
        ),
    ],
)
def test_provider_supervision_ir_rejects_schema_member_edge_and_path_tampering(
    mutate,
) -> None:
    workflow, _ = _executable_workflow(mutate(_provider_supervision_config()))

    with pytest.raises(WorkflowValidationError):
        validate_executable_workflow(workflow)


def test_provider_supervision_ir_rejects_effectively_unvalidated_settlement() -> None:
    config = _provider_supervision_config()
    invalid_payload = MappingProxyType(
        {
            **dict(config.settlement_payload),
            "expr": MappingProxyType(
                {"kind": "binding", "name": "not_a_member"}
            ),
        }
    )
    workflow, _ = _executable_workflow(
        replace(config, settlement_payload=invalid_payload)
    )

    with pytest.raises(
        WorkflowValidationError,
        match="settlement",
    ):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize("mismatch", ["worker_binding", "result_contract"])
def test_provider_supervision_ir_rejects_settlement_type_mismatch(
    mismatch: str,
) -> None:
    config = _provider_supervision_config()
    if mismatch == "worker_binding":
        bindings = {
            **dict(config.settlement_payload["bindings"]),
            "worker": {"type": _BOOL_TYPE},
        }
        config = replace(
            config,
            settlement_payload=MappingProxyType(
                {
                    **dict(config.settlement_payload),
                    "bindings": MappingProxyType(bindings),
                }
            ),
        )
    else:
        config = replace(
            config,
            settlement_result_contract=_contract(
                "settlement_result",
                _BOOL_TYPE,
            ),
        )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(WorkflowValidationError, match="settlement"):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    ("owner", "definition"),
    [
        ("worker", object()),
        ("worker", {"type": object()}),
        (
            "worker",
            {
                "type": {
                    "kind": "primitive",
                    "name": float("nan"),
                }
            },
        ),
        ("settlement", object()),
        ("settlement", {"type": object()}),
        (
            "settlement",
            {
                "type": {
                    "kind": "primitive",
                    "name": float("nan"),
                }
            },
        ),
    ],
)
def test_provider_supervision_ir_translates_malformed_member_contracts(
    owner: str,
    definition,
) -> None:
    config = _provider_supervision_config()
    if owner == "worker":
        config = replace(
            config,
            worker=replace(
                config.worker,
                result_contract=replace(
                    config.worker.result_contract,
                    definition=definition,
                ),
            ),
        )
        expected_error = "member contract"
    else:
        config = replace(
            config,
            settlement_result_contract=replace(
                config.settlement_result_contract,
                definition=definition,
            ),
        )
        expected_error = "settlement result contract"
    workflow, _ = _executable_workflow(config)

    with pytest.raises(WorkflowValidationError, match=expected_error):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    ("kind", "value_type", "descriptor"),
    [
        (
            "scalar",
            "string",
            {"kind": "primitive", "name": "String"},
        ),
        (
            "union",
            "ProviderSteeringDirective",
            {
                "kind": "union",
                "name": "ProviderSteeringDirective",
                "variants": [
                    {
                        "name": "STEER",
                        "fields": [
                            {
                                "name": "guidance",
                                "type": {"kind": "primitive", "name": "String"},
                            }
                        ],
                    }
                ],
            },
        ),
        (
            "union",
            "ProviderSteeringDirective",
            {
                "kind": "union",
                "name": "ProviderSteeringDirective",
                "variants": [
                    {"name": "CONTINUE", "fields": []},
                    {
                        "name": "STEER",
                        "fields": [
                            {
                                "name": "guidance",
                                "type": {"kind": "primitive", "name": "String"},
                            }
                        ],
                    },
                    {"name": "WAIT", "fields": []},
                ],
            },
        ),
        (
            "union",
            "ProviderSteeringDirective",
            {
                "kind": "union",
                "name": "ProviderSteeringDirective",
                "variants": [
                    {
                        "name": "CONTINUE",
                        "fields": [
                            {
                                "name": "unexpected",
                                "type": {"kind": "primitive", "name": "String"},
                            }
                        ],
                    },
                    {
                        "name": "STEER",
                        "fields": [
                            {
                                "name": "guidance",
                                "type": {"kind": "primitive", "name": "String"},
                            }
                        ],
                    },
                ],
            },
        ),
        (
            "union",
            "ProviderSteeringDirective",
            {
                "kind": "union",
                "name": "ProviderSteeringDirective",
                "variants": [
                    {"name": "CONTINUE", "fields": []},
                    {
                        "name": "STEER",
                        "fields": [
                            {
                                "name": "guidance",
                                "type": {"kind": "primitive", "name": "Bool"},
                            }
                        ],
                    },
                ],
            },
        ),
        (
            "scalar",
            "ProviderSteeringDirective",
            provider_steering_directive_type_descriptor(),
        ),
        (
            "union",
            "String",
            provider_steering_directive_type_descriptor(),
        ),
    ],
)
def test_provider_supervision_ir_rejects_same_name_directive_contract_drift(
    kind: str,
    value_type: str,
    descriptor,
) -> None:
    config = _provider_supervision_config()
    supervisor = replace(
        config.supervisor,
        result_contract=_contract(
            "ProviderSteeringDirective",
            descriptor,
            kind=kind,
            value_type=value_type,
        ),
    )
    bindings = {
        **dict(config.settlement_payload["bindings"]),
        "supervisor": {"type": descriptor},
    }
    config = replace(
        config,
        supervisor=supervisor,
        settlement_payload=MappingProxyType(
            {
                **dict(config.settlement_payload),
                "bindings": MappingProxyType(bindings),
            }
        ),
    )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(
        WorkflowValidationError,
        match="directive contract",
    ):
        validate_executable_workflow(workflow)


def test_provider_supervision_ir_translates_unserializable_directive_shape_failure() -> None:
    config = _provider_supervision_config()
    invalid_descriptor = {
        **provider_steering_directive_type_descriptor(),
        "unserializable": object(),
    }
    config = replace(
        config,
        supervisor=replace(
            config.supervisor,
            result_contract=_contract(
                "ProviderSteeringDirective",
                invalid_descriptor,
                kind="union",
                value_type="ProviderSteeringDirective",
            ),
        ),
    )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(
        WorkflowValidationError,
        match="directive contract descriptor",
    ):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize("removed", ["schema_version", "worker", "settlement_payload"])
def test_provider_supervision_config_constructor_rejects_missing_fields(
    removed: str,
) -> None:
    kwargs = dict(_provider_supervision_config().__dict__)
    del kwargs[removed]

    with pytest.raises(TypeError):
        ProviderSupervisionStepConfig(**kwargs)


def test_provider_supervision_config_constructor_rejects_extra_fields() -> None:
    kwargs = {
        **dict(_provider_supervision_config().__dict__),
        "live_target": "%7",
    }

    with pytest.raises(TypeError):
        ProviderSupervisionStepConfig(**kwargs)


def test_generated_provider_supervision_traverses_surface_core_ir_and_runtime() -> None:
    config = _provider_supervision_config()
    provenance = WorkflowProvenance(
        workflow_path=Path("/tmp/generated.orc"),
        source_root=Path("/tmp"),
        frontend_kind="workflow_lisp",
    )
    surface = SurfaceWorkflow(
        version="2.15",
        name="generated-live",
        steps=(
            SurfaceStep(
                name="Live",
                step_id="root.live",
                kind=SurfaceStepKind.PROVIDER_SUPERVISION,
                common=SurfaceStepCommonConfig(timeout_sec=60),
                provider_supervision=config,
            ),
        ),
        provenance=provenance,
    )

    core = build_core_workflow_ast(surface, {}, provenance)
    assert len(core.body) == 1
    assert isinstance(core.body[0], CoreProviderSupervisionStep)
    assert core.body[0].provider_supervision is config
    core_payload = workflow_core_ast_to_json(core)
    assert core_payload["body"][0]["kind"] == "provider_supervision"
    assert core_payload == workflow_core_ast_to_json(core)

    executable, _projection = lower_core_workflow_ast(core)
    assert executable.schema_version == WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION
    node = executable.nodes["root.live"]
    assert isinstance(node, LeafExecutableNode)
    assert node.kind is ExecutableNodeKind.PROVIDER_SUPERVISION
    assert isinstance(node.execution_config, ProviderSupervisionStepConfig)
    assert node.execution_config.node_id == node.node_id
    runtime = RuntimeStep(
        node=node,
        name=node.presentation_name,
        step_id=node.step_id,
    )
    assert runtime["provider_supervision"]["max_steers"] == 1


def test_classic_authored_mapping_cannot_construct_provider_supervision(
    tmp_path: Path,
) -> None:
    result = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping={
                "version": "2.15",
                "name": "classic-authored",
                "steps": [
                    {
                        "name": "ForbiddenLiveGroup",
                        "provider_supervision": {},
                    }
                ],
            },
            workflow_path=tmp_path / "classic.yaml",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )

    assert result.bundle is None
    assert any(
        "provider_supervision is compiler-generated only" in error.message
        for error in result.errors
    )
