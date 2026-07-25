"""Closed executable-IR contract tests for generated provider supervision."""

from __future__ import annotations

from copy import deepcopy
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
from orchestrator.workflow.provider_supervision.contracts import (
    derive_result_bundle_contract,
    derive_result_contract_identity,
)
from orchestrator.workflow.provider_supervision.models import (
    ProviderSupervisionObservation,
    ProviderSupervisionSourceOwnership,
)
from orchestrator.workflow.provider_supervision.paths import (
    ProviderSupervisionPaths,
    derive_provider_supervision_paths,
)
from orchestrator.workflow.prompt_dependency_contract import (
    PromptDependencyOriginKind,
    PromptDependencyPosition,
    _build_compiler_prompt_dependency_contract,
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


def _member_provider_config(provider: str) -> ProviderStepConfig:
    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=(),
        optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND,
        instruction=None,
        source_origin_key=f"source:{provider}:implicit-prompt-dependencies",
        source_workflow_bytes=b"; generated provider supervision\n",
        origin_kind=(
            PromptDependencyOriginKind
            .WORKFLOW_LISP_PROVIDER_SUPERVISION_MEMBER_IMPLICIT_EMPTY
        ),
    )
    if provider == "supervisor-provider":
        common = StepCommonConfig(
            timeout_sec=20,
            variant_output=MappingProxyType(
                {
                    "discriminant": MappingProxyType(
                        {
                            "name": "variant",
                            "json_pointer": "/variant",
                            "type": "enum",
                            "allowed": ("CONTINUE", "STEER"),
                        }
                    ),
                    "shared_fields": (),
                    "variants": MappingProxyType(
                        {
                            "CONTINUE": MappingProxyType(
                                {"fields": ()}
                            ),
                            "STEER": MappingProxyType(
                                {
                                    "fields": (
                                        MappingProxyType(
                                            {
                                                "name": "guidance",
                                                "json_pointer": "/guidance",
                                                "type": "string",
                                            }
                                        ),
                                    )
                                }
                            ),
                        }
                    ),
                }
            )
        )
    else:
        common = StepCommonConfig(
            timeout_sec=30,
            output_bundle=MappingProxyType(
                {
                    "fields": (
                        MappingProxyType(
                            {
                                "name": "__result__",
                                "json_pointer": "",
                                "type": "string",
                            }
                        ),
                    )
                }
            )
        )
    return ProviderStepConfig(
        common=common,
        provider=provider,
        depends_on=MappingProxyType(
            {
                "required": (),
                "optional": (),
                "inject": MappingProxyType(
                    {
                        "mode": "content",
                        "position": "prepend",
                    }
                ),
            }
        ),
        inject_output_contract=True,
        compiler_prompt_dependency_contract=contract,
    )


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
        provider_config=_member_provider_config("worker-provider"),
        result_contract=_contract("String"),
        timeout_sec=30,
    )
    supervisor = ProviderSupervisionMemberConfig(
        member_id="supervisor",
        provider_config=_member_provider_config("supervisor-provider"),
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
        settlement_result_contract=_contract("String"),
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


def _provider_supervision_config_with_settlement_type(
    descriptor,
    *,
    contract_kind: str,
    value_type: str,
) -> ProviderSupervisionStepConfig:
    config = _provider_supervision_config(node_id="live")
    canonical_name, canonical_kind, canonical_value_type = (
        derive_result_contract_identity(descriptor)
    )
    assert (contract_kind, value_type) == (
        canonical_kind,
        canonical_value_type,
    )
    result_contract = _contract(
        canonical_name,
        descriptor,
        kind=contract_kind,
        value_type=value_type,
    )
    worker_result_contract = _contract(
        canonical_name,
        descriptor,
        kind=contract_kind,
        value_type=value_type,
    )
    prototype_kind, realized_prototype, _ = derive_result_bundle_contract(
        worker_result_contract,
        path="ignored-at-runtime.json",
    )
    pathless_prototype = MappingProxyType(
        {
            key: value
            for key, value in realized_prototype.items()
            if key != "path"
        }
    )
    worker_common = replace(
        config.worker.provider_config.common,
        output_bundle=(
            pathless_prototype
            if prototype_kind == "output_bundle"
            else None
        ),
        variant_output=(
            pathless_prototype
            if prototype_kind == "variant_output"
            else None
        ),
    )
    return replace(
        config,
        worker=replace(
            config.worker,
            provider_config=replace(
                config.worker.provider_config,
                common=worker_common,
            ),
            result_contract=worker_result_contract,
        ),
        settlement_payload=MappingProxyType(
            {
                "pure_expr_schema_version": 1,
                "result_type": descriptor,
                "bindings": MappingProxyType(
                    {
                        "worker": MappingProxyType({"type": descriptor}),
                        "supervisor": MappingProxyType(
                            {
                                "type": (
                                    provider_steering_directive_type_descriptor()
                                )
                            }
                        ),
                    }
                ),
                "expr": MappingProxyType(
                    {"kind": "binding", "name": "worker"}
                ),
            }
        ),
        settlement_result_contract=result_contract,
    )


def _validate_provider_supervision_settlement_mapping(
    tmp_path: Path,
    config: ProviderSupervisionStepConfig,
    *,
    outputs=None,
    extra_steps=(),
):
    mapping = {
        "version": "2.16",
        "name": "generated-live",
        "providers": {
            "worker-provider": {
                "command": ["worker-tool"],
                "input_mode": "stdin",
                "session_support": {
                    "metadata_mode": "codex_exec_jsonl_stdout",
                    "fresh_command": ["worker-tool", "--json"],
                    "resume_command": [
                        "worker-tool",
                        "resume",
                        "${SESSION_ID}",
                        "--json",
                    ],
                    "turn_boundary_resume": True,
                },
            }
        },
        "steps": [
            {
                "name": "Live",
                "id": "live",
                "timeout_sec": 60,
                "provider_supervision": config,
            },
            *extra_steps,
        ],
    }
    if outputs is not None:
        mapping["outputs"] = outputs
    return validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping=mapping,
            workflow_path=tmp_path / "generated-live.orc",
            frontend_kind="workflow_lisp",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
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


def test_provider_supervision_config_survives_generated_mapping_deepcopy() -> None:
    config = _provider_supervision_config()
    generated_mapping = {
        "steps": [
            {
                "name": "Live",
                "provider_supervision": config,
            }
        ]
    }

    copied_mapping = deepcopy(generated_mapping)

    assert copied_mapping is not generated_mapping
    assert copied_mapping["steps"][0]["provider_supervision"] is config


def test_provider_supervision_settlement_catalog_projects_scalar_result(
    tmp_path: Path,
) -> None:
    result = _validate_provider_supervision_settlement_mapping(
        tmp_path,
        _provider_supervision_config_with_settlement_type(
            _STRING_TYPE,
            contract_kind="scalar",
            value_type="string",
        ),
        outputs={
            "result": {
                "kind": "scalar",
                "type": "string",
                "from": {
                    "ref": "root.steps.Live.artifacts.__result__",
                },
            }
        },
    )

    assert result.errors == ()
    assert result.bundle is not None


def test_provider_supervision_settlement_catalog_projects_nested_record_fields(
    tmp_path: Path,
) -> None:
    descriptor = {
        "kind": "record",
        "name": "Review",
        "fields": [
            {
                "name": "label",
                "type": {"kind": "primitive", "name": "String"},
            },
            {
                "name": "metrics",
                "type": {
                    "kind": "record",
                    "name": "Metrics",
                    "fields": [
                        {
                            "name": "score",
                            "type": {
                                "kind": "primitive",
                                "name": "Float",
                            },
                        }
                    ],
                },
            },
        ],
    }

    result = _validate_provider_supervision_settlement_mapping(
        tmp_path,
        _provider_supervision_config_with_settlement_type(
            descriptor,
            contract_kind="record",
            value_type="Review",
        ),
        outputs={
            "label": {
                "kind": "scalar",
                "type": "string",
                "from": {"ref": "root.steps.Live.artifacts.label"},
            },
            "score": {
                "kind": "scalar",
                "type": "float",
                "from": {
                    "ref": "root.steps.Live.artifacts.metrics__score",
                },
            },
        },
    )

    assert result.errors == ()
    assert result.bundle is not None


def test_provider_supervision_settlement_catalog_projects_union_fields(
    tmp_path: Path,
) -> None:
    descriptor = {
        "kind": "union",
        "name": "Outcome",
        "variants": [
            {
                "name": "OK",
                "fields": [
                    {
                        "name": "note",
                        "type": {"kind": "primitive", "name": "String"},
                    },
                    {
                        "name": "score",
                        "type": {"kind": "primitive", "name": "Float"},
                    },
                ],
            },
            {
                "name": "BAD",
                "fields": [
                    {
                        "name": "note",
                        "type": {"kind": "primitive", "name": "String"},
                    },
                    {
                        "name": "reason",
                        "type": {"kind": "primitive", "name": "String"},
                    },
                ],
            },
        ],
    }
    materialize_steps = (
        {
            "name": "UseScore",
            "id": "use_score",
            "requires_variant": {"step": "Live", "value": "OK"},
            "materialize_artifacts": {
                "values": [
                    {
                        "name": "score",
                        "source": {
                            "ref": "root.steps.Live.artifacts.score",
                        },
                        "contract": {"type": "float"},
                        "pointer": {"path": "state/score.json"},
                    }
                ]
            },
        },
        {
            "name": "UseReason",
            "id": "use_reason",
            "requires_variant": {"step": "Live", "value": "BAD"},
            "materialize_artifacts": {
                "values": [
                    {
                        "name": "reason",
                        "source": {
                            "ref": "root.steps.Live.artifacts.reason",
                        },
                        "contract": {"type": "string"},
                        "pointer": {"path": "state/reason.json"},
                    }
                ]
            },
        },
    )

    result = _validate_provider_supervision_settlement_mapping(
        tmp_path,
        _provider_supervision_config_with_settlement_type(
            descriptor,
            contract_kind="union",
            value_type="Outcome",
        ),
        outputs={
            "variant": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["OK", "BAD"],
                "from": {"ref": "root.steps.Live.artifacts.variant"},
            },
            "note": {
                "kind": "scalar",
                "type": "string",
                "from": {"ref": "root.steps.Live.artifacts.note"},
            },
        },
        extra_steps=materialize_steps,
    )

    assert result.errors == ()
    assert result.bundle is not None


def test_provider_supervision_union_settlement_ref_requires_variant_proof(
    tmp_path: Path,
) -> None:
    descriptor = {
        "kind": "union",
        "name": "Outcome",
        "variants": [
            {
                "name": "OK",
                "fields": [
                    {
                        "name": "score",
                        "type": {"kind": "primitive", "name": "Float"},
                    }
                ],
            },
            {"name": "BAD", "fields": []},
        ],
    }

    result = _validate_provider_supervision_settlement_mapping(
        tmp_path,
        _provider_supervision_config_with_settlement_type(
            descriptor,
            contract_kind="union",
            value_type="Outcome",
        ),
        extra_steps=(
            {
                "name": "UseScore",
                "id": "use_score",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "score",
                            "source": {
                                "ref": (
                                    "root.steps.Live.artifacts.score"
                                ),
                            },
                            "contract": {"type": "float"},
                            "pointer": {"path": "state/score.json"},
                        }
                    ]
                },
            },
        ),
    )

    assert result.bundle is None
    assert [error.message for error in result.errors] == [
        (
            "Step 'UseScore': structured ref "
            "'root.steps.Live.artifacts.score' targets variant-specific "
            "artifact 'score' without required author-time variant proof"
        )
    ]


def test_provider_supervision_ir_accepts_exact_aggregate_timeout_budget() -> None:
    config = _provider_supervision_config()
    workflow, _ = _executable_workflow(config)

    validate_executable_workflow(workflow)


@pytest.mark.parametrize("timeout_sec", [59, 61])
def test_provider_supervision_ir_rejects_inexact_aggregate_timeout_budget(
    timeout_sec: int,
) -> None:
    config = _provider_supervision_config()
    config = replace(
        config,
        common=replace(config.common, timeout_sec=timeout_sec),
    )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(
        WorkflowValidationError,
        match="whole-step timeout budget",
    ):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda config: replace(config, schema_version="provider_supervision.v2"),
        lambda config: replace(config, node_id="root.other"),
        lambda config: replace(config, common=None),  # type: ignore[arg-type]
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
            worker=replace(
                config.worker,
                provider_config=replace(
                    config.worker.provider_config,
                    common={},  # type: ignore[arg-type]
                ),
            ),
        ),
        lambda config: replace(
            config,
            worker=replace(
                config.worker,
                provider_config=replace(
                    config.worker.provider_config,
                    inject_output_contract=False,
                ),
            ),
        ),
        lambda config: replace(
            config,
            worker=replace(
                config.worker,
                provider_config=replace(
                    config.worker.provider_config,
                    common=replace(
                        config.worker.provider_config.common,
                        timeout_sec=999,
                    ),
                ),
            ),
        ),
        lambda config: replace(
            config,
            worker=replace(
                config.worker,
                provider_config=replace(
                    config.worker.provider_config,
                    compiler_prompt_dependency_contract=None,
                ),
            ),
        ),
        lambda config: replace(
            config,
            worker=replace(
                config.worker,
                provider_config=replace(
                    config.worker.provider_config,
                    depends_on=MappingProxyType({}),
                ),
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
            worker=replace(
                config.worker,
                result_contract=replace(
                    config.worker.result_contract,
                    kind="union",
                    value_type="Bogus",
                ),
            ),
        ),
        lambda config: replace(
            config,
            settlement_result_contract=replace(
                config.settlement_result_contract,
                name="Bogus",
                kind="union",
                value_type="Bogus",
            ),
        ),
        lambda config: replace(
            config,
            worker=replace(
                config.worker,
                result_contract=replace(
                    config.worker.result_contract,
                    definition=MappingProxyType(
                        {
                            **dict(
                                config.worker.result_contract.definition
                            ),
                            "extra": True,
                        }
                    ),
                ),
            ),
        ),
        lambda config: replace(
            config,
            settlement_result_contract=replace(
                config.settlement_result_contract,
                definition=MappingProxyType(
                    {
                        **dict(
                            config.settlement_result_contract.definition
                        ),
                        "extra": True,
                    }
                ),
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


@pytest.mark.parametrize(
    "mutate_common",
    [
        lambda common: replace(common, output_bundle=None),
        lambda common: replace(
            common,
            variant_output=MappingProxyType(
                {
                    "discriminant": MappingProxyType(
                        {
                            "name": "variant",
                            "json_pointer": "/variant",
                            "type": "enum",
                            "allowed": ("OTHER",),
                        }
                    ),
                    "shared_fields": (),
                    "variants": MappingProxyType(
                        {"OTHER": MappingProxyType({"fields": ()})}
                    ),
                }
            ),
        ),
        lambda common: replace(
            common,
            output_bundle=None,
            variant_output=MappingProxyType(
                {
                    "discriminant": MappingProxyType(
                        {
                            "name": "variant",
                            "json_pointer": "/variant",
                            "type": "enum",
                            "allowed": ("OTHER",),
                        }
                    ),
                    "shared_fields": (),
                    "variants": MappingProxyType(
                        {"OTHER": MappingProxyType({"fields": ()})}
                    ),
                }
            ),
        ),
        lambda common: replace(
            common,
            output_bundle=MappingProxyType(
                {
                    **dict(common.output_bundle),
                    "path": "stale/result.json",
                }
            ),
        ),
        lambda common: replace(
            common,
            output_bundle=MappingProxyType(
                {
                    "fields": (
                        MappingProxyType(
                            {
                                "name": "__result__",
                                "json_pointer": "",
                                "type": "boolean",
                            }
                        ),
                    )
                }
            ),
        ),
        lambda common: replace(
            common,
            output_bundle=MappingProxyType(
                {
                    **dict(common.output_bundle),
                    "description": "misplaced guidance",
                }
            ),
        ),
        lambda common: replace(
            common,
            output_bundle=MappingProxyType(
                {
                    "fields": (
                        MappingProxyType(
                            {
                                **dict(common.output_bundle["fields"][0]),
                                "description": "",
                            }
                        ),
                    )
                }
            ),
        ),
        lambda common: replace(
            common,
            output_bundle=MappingProxyType(
                {
                    "fields": (
                        MappingProxyType(
                            {
                                **dict(common.output_bundle["fields"][0]),
                                "source_map_subject": MappingProxyType(
                                    {
                                        "subject_kind": (
                                            "output_bundle_field"
                                        ),
                                    }
                                ),
                            }
                        ),
                    )
                }
            ),
        ),
    ],
)
def test_provider_supervision_ir_rejects_invalid_member_result_prototype(
    mutate_common,
) -> None:
    config = _provider_supervision_config()
    config = replace(
        config,
        worker=replace(
            config.worker,
            provider_config=replace(
                config.worker.provider_config,
                common=mutate_common(config.worker.provider_config.common),
            ),
        ),
    )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(
        WorkflowValidationError,
        match="worker result contract prototype is invalid",
    ):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_provider_supervision_ir_preserves_metadata_named_union_variant(
    mutation: str,
) -> None:
    descriptor = {
        "kind": "union",
        "name": "Outcome",
        "variants": [
            {
                "name": "description",
                "fields": [
                    {
                        "name": "note",
                        "type": {"kind": "primitive", "name": "String"},
                    }
                ],
            },
            {
                "name": "OK",
                "fields": [
                    {
                        "name": "code",
                        "type": {"kind": "primitive", "name": "String"},
                    }
                ],
            },
        ],
    }
    config = _provider_supervision_config_with_settlement_type(
        descriptor,
        contract_kind="union",
        value_type="Outcome",
    )
    prototype = dict(
        config.worker.provider_config.common.variant_output
    )
    variants = {
        name: dict(payload)
        for name, payload in prototype["variants"].items()
    }
    if mutation == "missing":
        variants.pop("description")
    else:
        description_fields = [
            dict(field)
            for field in variants["description"]["fields"]
        ]
        description_fields[0]["type"] = "integer"
        variants["description"]["fields"] = description_fields
    prototype["variants"] = variants
    config = replace(
        config,
        worker=replace(
            config.worker,
            provider_config=replace(
                config.worker.provider_config,
                common=replace(
                    config.worker.provider_config.common,
                    variant_output=MappingProxyType(prototype),
                ),
            ),
        ),
    )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(
        WorkflowValidationError,
        match="worker result contract prototype is invalid",
    ):
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
                "Bool",
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


@pytest.mark.parametrize("owner", ["worker", "settlement"])
def test_provider_supervision_ir_translates_cyclic_member_contracts(
    owner: str,
) -> None:
    cyclic_descriptor: dict[str, object] = {"kind": "optional"}
    cyclic_descriptor["item"] = cyclic_descriptor
    config = _provider_supervision_config()
    cyclic_contract = replace(
        config.worker.result_contract,
        definition={"type": cyclic_descriptor},
    )
    if owner == "worker":
        config = replace(
            config,
            worker=replace(
                config.worker,
                result_contract=cyclic_contract,
            ),
        )
        expected_error = "member contract"
    else:
        config = replace(
            config,
            settlement_result_contract=cyclic_contract,
        )
        expected_error = "settlement result contract"
    workflow, _ = _executable_workflow(config)

    with pytest.raises(WorkflowValidationError, match=expected_error):
        validate_executable_workflow(workflow)


def test_provider_supervision_ir_translates_cyclic_guidance_example() -> None:
    cyclic_example: dict[str, object] = {}
    cyclic_example["self"] = cyclic_example
    config = _provider_supervision_config()
    prototype = dict(config.worker.provider_config.common.output_bundle)
    field = dict(prototype["fields"][0])
    field["example"] = cyclic_example
    prototype["fields"] = (MappingProxyType(field),)
    config = replace(
        config,
        worker=replace(
            config.worker,
            provider_config=replace(
                config.worker.provider_config,
                common=replace(
                    config.worker.provider_config.common,
                    output_bundle=MappingProxyType(prototype),
                ),
            ),
        ),
    )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(
        WorkflowValidationError,
        match="worker result contract prototype is invalid",
    ):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    "descriptor",
    [
        {
            "kind": "primitive",
            "name": "String",
            "extra": True,
        },
        {
            "kind": "map",
            "key": {"kind": "primitive", "name": "Int"},
            "value": {"kind": "primitive", "name": "String"},
        },
        {
            "kind": "union",
            "name": "Empty",
            "variants": [],
        },
    ],
)
def test_result_contract_identity_rejects_unvalidated_descriptors(
    descriptor: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        derive_result_contract_identity(descriptor)


def test_result_contract_identity_rejects_cyclic_descriptor() -> None:
    descriptor: dict[str, object] = {"kind": "optional"}
    descriptor["item"] = descriptor

    with pytest.raises(ValueError, match="reference cycle"):
        derive_result_contract_identity(descriptor)


@pytest.mark.parametrize(
    "descriptor",
    [
        {
            "kind": "record",
            "name": "Collision",
            "fields": [
                {
                    "name": "a__b",
                    "type": {"kind": "primitive", "name": "String"},
                },
                {
                    "name": "a",
                    "type": {
                        "kind": "record",
                        "name": "Inner",
                        "fields": [
                            {
                                "name": "b",
                                "type": {
                                    "kind": "primitive",
                                    "name": "String",
                                },
                            }
                        ],
                    },
                },
            ],
        },
        {
            "kind": "union",
            "name": "Collision",
            "variants": [
                {
                    "name": "BAD",
                    "fields": [
                        {
                            "name": "a__b",
                            "type": {
                                "kind": "primitive",
                                "name": "String",
                            },
                        },
                        {
                            "name": "a",
                            "type": {
                                "kind": "record",
                                "name": "Inner",
                                "fields": [
                                    {
                                        "name": "b",
                                        "type": {
                                            "kind": "primitive",
                                            "name": "String",
                                        },
                                    }
                                ],
                            },
                        },
                    ],
                }
            ],
        },
    ],
)
def test_result_contract_identity_rejects_flattened_name_collisions(
    descriptor: dict[str, object],
) -> None:
    with pytest.raises(
        ValueError,
        match="flattened result descriptor field names",
    ):
        derive_result_contract_identity(descriptor)


def test_provider_supervision_ir_translates_flattened_name_collision() -> None:
    descriptor = {
        "kind": "record",
        "name": "Collision",
        "fields": [
            {
                "name": "a__b",
                "type": {"kind": "primitive", "name": "String"},
            },
            {
                "name": "a",
                "type": {
                    "kind": "record",
                    "name": "Inner",
                    "fields": [
                        {
                            "name": "b",
                            "type": {
                                "kind": "primitive",
                                "name": "String",
                            },
                        }
                    ],
                },
            },
        ],
    }
    config = _provider_supervision_config()
    config = replace(
        config,
        worker=replace(
            config.worker,
            result_contract=replace(
                config.worker.result_contract,
                name="Collision",
                kind="record",
                value_type="Collision",
                definition={"type": descriptor},
            ),
        ),
    )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(
        WorkflowValidationError,
        match="member contract",
    ):
        validate_executable_workflow(workflow)


def test_result_contract_derivation_rejects_union_discriminant_collision() -> None:
    descriptor = {
        "kind": "union",
        "name": "Collision",
        "variants": [
            {
                "name": "OK",
                "fields": [
                    {
                        "name": "variant",
                        "type": {
                            "kind": "primitive",
                            "name": "String",
                        },
                    }
                ],
            },
            {"name": "BAD", "fields": []},
        ],
    }
    contract = _contract(
        "Collision",
        descriptor,
        kind="union",
        value_type="Collision",
    )

    with pytest.raises(ValueError, match="discriminant"):
        derive_result_contract_identity(descriptor)
    with pytest.raises(ValueError, match="discriminant"):
        derive_result_bundle_contract(
            contract,
            path="collision.json",
        )


def test_provider_supervision_ir_translates_union_discriminant_collision() -> None:
    descriptor = {
        "kind": "union",
        "name": "Collision",
        "variants": [
            {
                "name": "OK",
                "fields": [
                    {
                        "name": "variant",
                        "type": {
                            "kind": "primitive",
                            "name": "String",
                        },
                    }
                ],
            },
            {"name": "BAD", "fields": []},
        ],
    }
    config = _provider_supervision_config()
    config = replace(
        config,
        worker=replace(
            config.worker,
            result_contract=_contract(
                "Collision",
                descriptor,
                kind="union",
                value_type="Collision",
            ),
        ),
    )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(
        WorkflowValidationError,
        match="member contract",
    ):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    ("descriptor", "expected"),
    [
        (
            {
                "kind": "record",
                "name": "String",
                "fields": [
                    {
                        "name": "value",
                        "type": {"kind": "primitive", "name": "Bool"},
                    }
                ],
            },
            ("String", "record", "String"),
        ),
        (
            {
                "kind": "union",
                "name": "Bool",
                "variants": [{"name": "YES", "fields": []}],
            },
            ("Bool", "union", "Bool"),
        ),
        (
            {
                "kind": "enum",
                "name": "Float",
                "allowed": ["LOW", "HIGH"],
            },
            ("Float", "scalar", "Float"),
        ),
        (
            {
                "kind": "path",
                "name": "Int",
                "under": "",
                "must_exist_target": False,
            },
            ("Int", "scalar", "Int"),
        ),
    ],
)
def test_result_contract_identity_maps_primitive_names_only_for_primitives(
    descriptor: dict[str, object],
    expected: tuple[str, str, str],
) -> None:
    assert derive_result_contract_identity(descriptor) == expected


@pytest.mark.parametrize("owner", ["worker", "settlement"])
def test_provider_supervision_ir_rejects_mirrored_open_type_descriptor(
    owner: str,
) -> None:
    config = _provider_supervision_config()
    descriptor = {
        **dict(config.worker.result_contract.definition["type"]),
        "extra": True,
    }
    if owner == "worker":
        bindings = {
            **dict(config.settlement_payload["bindings"]),
            "worker": {"type": descriptor},
        }
        config = replace(
            config,
            worker=replace(
                config.worker,
                result_contract=replace(
                    config.worker.result_contract,
                    definition=MappingProxyType({"type": descriptor}),
                ),
            ),
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
            settlement_result_contract=replace(
                config.settlement_result_contract,
                definition=MappingProxyType({"type": descriptor}),
            ),
            settlement_payload=MappingProxyType(
                {
                    **dict(config.settlement_payload),
                    "result_type": descriptor,
                }
            ),
        )
    workflow, _ = _executable_workflow(config)

    with pytest.raises(WorkflowValidationError, match=owner):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    "under",
    ["/absolute", "../escape", "state/../escape"],
)
def test_provider_supervision_ir_rejects_unsafe_path_refinement(
    under: str,
) -> None:
    valid_descriptor = {
        "kind": "path",
        "name": "ReviewPath",
        "under": "state/reviews",
        "must_exist_target": False,
    }
    config = _provider_supervision_config_with_settlement_type(
        valid_descriptor,
        contract_kind="scalar",
        value_type="ReviewPath",
    )
    invalid_descriptor = {**valid_descriptor, "under": under}
    bindings = {
        **dict(config.settlement_payload["bindings"]),
        "worker": {"type": invalid_descriptor},
    }
    prototype = {
        **dict(config.worker.provider_config.common.output_bundle),
        "fields": (
            MappingProxyType(
                {
                    **dict(
                        config.worker.provider_config.common.output_bundle[
                            "fields"
                        ][0]
                    ),
                    "under": under,
                }
            ),
        ),
    }
    config = replace(
        config,
        worker=replace(
            config.worker,
            provider_config=replace(
                config.worker.provider_config,
                common=replace(
                    config.worker.provider_config.common,
                    output_bundle=MappingProxyType(prototype),
                ),
            ),
            result_contract=replace(
                config.worker.result_contract,
                definition=MappingProxyType(
                    {"type": invalid_descriptor}
                ),
            ),
        ),
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
        match="worker member contract identity is invalid",
    ):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize("under", ["", "."])
def test_provider_supervision_ir_accepts_workspace_root_path_refinement(
    under: str,
) -> None:
    descriptor = {
        "kind": "path",
        "name": "ReviewPath",
        "under": under,
        "must_exist_target": False,
    }
    config = _provider_supervision_config_with_settlement_type(
        descriptor,
        contract_kind="scalar",
        value_type="ReviewPath",
    )
    workflow, _ = _executable_workflow(config)

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


def test_generated_provider_supervision_rebinds_node_and_paths_atomically() -> None:
    original_config = _provider_supervision_config(node_id="draft.live")
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
                provider_supervision=original_config,
            ),
        ),
        provenance=provenance,
    )

    core = build_core_workflow_ast(surface, {}, provenance)
    executable, _projection = lower_core_workflow_ast(core)

    config = executable.nodes["root.live"].execution_config
    assert isinstance(config, ProviderSupervisionStepConfig)
    assert config.node_id == "root.live"
    assert config.paths == derive_provider_supervision_paths(
        node_id="root.live",
        worker_member_id="worker",
        supervisor_member_id="supervisor",
    )
    assert original_config.node_id == "draft.live"
    assert original_config.paths == derive_provider_supervision_paths(
        node_id="draft.live",
        worker_member_id="worker",
        supervisor_member_id="supervisor",
    )


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
