"""Closed executable-IR tests for provider peer groups."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import MappingProxyType

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.providers.types import (
    INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION,
)
from orchestrator.workflow import executable_ir as ir_module
from orchestrator.workflow.executable_ir import (
    WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION,
    ExecutableContract,
    ExecutableNodeKind,
    ExecutableWorkflow,
    LeafExecutableNode,
    ProviderPeerGroupMemberConfig,
    ProviderPeerGroupMemberSourceOwnership,
    ProviderPeerGroupSourceOwnership,
    ProviderPeerGroupStepConfig,
    ProviderStepConfig,
    StepCommonConfig,
    WorkflowRegion,
    validate_executable_workflow,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.lowering import _IRBuilder
from orchestrator.workflow.prompt_dependency_contract import (
    PromptDependencyOriginKind,
    PromptDependencyPosition,
    _build_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.resume_planner import ResumePlanner
from orchestrator.workflow.provider_peer_group.paths import (
    derive_provider_peer_group_paths,
)
from orchestrator.workflow.runtime_plan import (
    derive_workflow_runtime_plan,
    validate_workflow_runtime_plan,
)
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow.state_projection import (
    CompatibilityNodeProjection,
    WorkflowStateProjection,
)
from orchestrator.workflow.surface_ast import SurfaceWorkflow, WorkflowProvenance


_STRING_TYPE = MappingProxyType({"kind": "primitive", "name": "String"})


def _contract(name: str = "String") -> ExecutableContract:
    return ExecutableContract(
        name=name,
        kind="scalar",
        value_type="string",
        definition=MappingProxyType({"type": _STRING_TYPE}),
    )


def _provider_config(member_id: str, timeout_sec: int) -> ProviderStepConfig:
    prompt_contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=(),
        optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND,
        instruction=None,
        source_origin_key=f"source:{member_id}:prompt",
        source_workflow_bytes=b"; generated provider peer group\n",
        origin_kind=(
            PromptDependencyOriginKind
            .WORKFLOW_LISP_PROVIDER_SUPERVISION_MEMBER_IMPLICIT_EMPTY
        ),
    )
    return ProviderStepConfig(
        common=StepCommonConfig(
            timeout_sec=timeout_sec,
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
            ),
        ),
        provider=f"{member_id}-provider",
        depends_on=MappingProxyType(
            {
                "required": (),
                "optional": (),
                "inject": MappingProxyType(
                    {"mode": "content", "position": "prepend"}
                ),
            }
        ),
        inject_output_contract=True,
        compiler_prompt_dependency_contract=prompt_contract,
    )


def _config(
    *,
    node_id: str = "root.peers",
    member_ids: tuple[str, ...] = ("author", "reviewer", "builder"),
) -> ProviderPeerGroupStepConfig:
    timeouts = tuple(20 + index * 5 for index in range(len(member_ids)))
    members = tuple(
        ProviderPeerGroupMemberConfig(
            member_id=member_id,
            provider_config=_provider_config(member_id, timeout_sec),
            result_contract=_contract(),
            timeout_sec=timeout_sec,
        )
        for member_id, timeout_sec in zip(member_ids, timeouts)
    )
    return ProviderPeerGroupStepConfig(
        common=StepCommonConfig(timeout_sec=max(timeouts)),
        schema_version="provider_peer_group.v1",
        node_id=node_id,
        members=members,
        messaging_policy="all_other_members",
        settlement_payload=MappingProxyType(
            {
                "pure_expr_schema_version": 1,
                "result_type": _STRING_TYPE,
                "bindings": MappingProxyType(
                    {
                        member_id: MappingProxyType({"type": _STRING_TYPE})
                        for member_id in member_ids
                    }
                ),
                "expr": MappingProxyType(
                    {"kind": "binding", "name": member_ids[0]}
                ),
            }
        ),
        settlement_result_contract=_contract(),
        interactive_session_schema_version=(
            INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION
        ),
        max_steers=0,
        paths=derive_provider_peer_group_paths(
            node_id=node_id,
            member_ids=member_ids,
        ),
        source_ownership=ProviderPeerGroupSourceOwnership(
            form="source:form",
            members=tuple(
                ProviderPeerGroupMemberSourceOwnership(
                    member_id=member_id,
                    binding=f"source:{member_id}",
                )
                for member_id in member_ids
            ),
            settlement="source:settlement",
        ),
    )


def _workflow(
    config: ProviderPeerGroupStepConfig,
) -> tuple[ExecutableWorkflow, LeafExecutableNode]:
    node = LeafExecutableNode(
        node_id=config.node_id,
        step_id=config.node_id,
        presentation_name="Peers",
        kind=ExecutableNodeKind.PROVIDER_PEER_GROUP,
        region=WorkflowRegion.BODY,
        lexical_scope=("root", "peers"),
        execution_config=config,
    )
    workflow = ExecutableWorkflow(
        schema_version=WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION,
        version="2.17",
        name="generated-peers",
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


def _projection(node: LeafExecutableNode) -> WorkflowStateProjection:
    entry = CompatibilityNodeProjection(
        node_id=node.node_id,
        step_id=node.step_id,
        presentation_key=node.presentation_name,
        display_name=node.presentation_name,
        region=node.region,
        compatibility_index=0,
    )
    return WorkflowStateProjection(
        entries_by_node_id=MappingProxyType({node.node_id: entry}),
        node_id_by_compatibility_index=MappingProxyType({0: node.node_id}),
        compatibility_index_by_node_id=MappingProxyType({node.node_id: 0}),
        presentation_key_by_node_id=MappingProxyType(
            {node.node_id: node.presentation_name}
        ),
        node_id_by_step_id=MappingProxyType({node.step_id: node.node_id}),
    )


def _production_projection(node: LeafExecutableNode) -> WorkflowStateProjection:
    provenance = WorkflowProvenance(
        workflow_path=Path("/tmp/generated.orc"),
        source_root=Path("/tmp"),
        frontend_kind="workflow_lisp",
    )
    builder = _IRBuilder(
        SurfaceWorkflow(
            version="2.17",
            name="generated-peers",
            steps=(),
            provenance=provenance,
        )
    )
    builder._register_node(
        node=node,
        region=WorkflowRegion.BODY,
        top_level_region=builder.body_region,
    )
    _, projection = builder.build()
    return projection


def test_provider_peer_group_has_a_separate_executable_node_kind() -> None:
    assert (
        ir_module.ExecutableNodeKind.PROVIDER_PEER_GROUP.value
        == "provider_peer_group"
    )


def test_production_projection_quarantines_interrupted_peer_group_visit() -> None:
    _, node = _workflow(_config())
    projection = _production_projection(node)

    guard = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        {
            "status": "running",
            "steps": {},
            "current_step": {
                "name": "Peers",
                "index": 0,
                "type": "provider_peer_group",
                "status": "running",
                "step_id": "root.peers",
                "visit_count": 1,
            },
        },
        projection=projection,
    )

    assert (
        projection.entries_by_node_id[
            node.node_id
        ].step_definition.report_kind
        == "provider_peer_group"
    )
    assert guard == {
        "kind": "quarantine",
        "step_name": "Peers",
        "step_id": "root.peers",
        "node_id": "root.peers",
        "visit_count": 1,
    }


def test_provider_peer_group_exposes_a_separate_closed_config_contract() -> None:
    assert ir_module.PROVIDER_PEER_GROUP_SCHEMA_VERSION == (
        "provider_peer_group.v1"
    )
    assert ir_module.PROVIDER_PEER_GROUP_MESSAGING_POLICY == (
        "all_other_members"
    )
    assert ir_module.ProviderPeerGroupMemberConfig is not None
    assert ir_module.ProviderPeerGroupMemberSourceOwnership is not None
    assert ir_module.ProviderPeerGroupSourceOwnership is not None
    assert ir_module.ProviderPeerGroupStepConfig is not None


@pytest.mark.parametrize(
    "member_ids",
    [
        ("one", "two"),
        tuple(f"member-{index}" for index in range(8)),
    ],
)
def test_provider_peer_group_accepts_closed_two_through_eight_member_ir(
    member_ids: tuple[str, ...],
) -> None:
    config = _config(member_ids=member_ids)
    workflow, node = _workflow(config)

    validate_executable_workflow(workflow)
    payload = workflow_executable_ir_to_json(workflow)
    peer_group = payload["nodes"][node.node_id]["execution_config"]

    assert payload["schema_version"] == "workflow_executable_ir.v1"
    assert node.kind is ExecutableNodeKind.PROVIDER_PEER_GROUP
    assert set(peer_group) == {
        "common",
        "schema_version",
        "node_id",
        "members",
        "messaging_policy",
        "settlement_payload",
        "settlement_result_contract",
        "interactive_session_schema_version",
        "max_steers",
        "paths",
        "source_ownership",
    }
    assert peer_group["schema_version"] == "provider_peer_group.v1"
    assert [member["member_id"] for member in peer_group["members"]] == list(
        member_ids
    )
    assert peer_group["messaging_policy"] == "all_other_members"
    assert peer_group["interactive_session_schema_version"] == (
        "interactive_terminal_turn_queue.v1"
    )
    assert peer_group["max_steers"] == 0
    assert peer_group["common"]["timeout_sec"] == max(
        member.timeout_sec for member in config.members
    )
    assert [member["member_id"] for member in peer_group["paths"]["members"]] == (
        list(member_ids)
    )
    assert len(set(config.paths.leaf_relpaths())) == len(
        config.paths.leaf_relpaths()
    )
    assert [
        member["member_id"]
        for member in peer_group["source_ownership"]["members"]
    ] == list(member_ids)
    assert json.dumps(payload, sort_keys=True, separators=(",", ":")) == (
        json.dumps(
            workflow_executable_ir_to_json(workflow),
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def test_provider_peer_group_is_visible_in_runtime_step_and_runtime_plan() -> None:
    config = _config()
    workflow, node = _workflow(config)
    validate_executable_workflow(workflow)

    runtime_payload = dict(
        RuntimeStep(
            node=node,
            name=node.presentation_name,
            step_id=node.step_id,
        )
    )
    assert runtime_payload["timeout_sec"] == 30
    assert runtime_payload["provider_peer_group"]["schema_version"] == (
        "provider_peer_group.v1"
    )
    assert [
        member["member_id"]
        for member in runtime_payload["provider_peer_group"]["members"]
    ] == ["author", "reviewer", "builder"]

    projection = _projection(node)
    plan = derive_workflow_runtime_plan(workflow, projection)
    summary = plan.nodes[node.node_id].provider_peer_group
    assert summary is not None
    assert summary.member_ids == ("author", "reviewer", "builder")
    assert summary.messaging_policy == "all_other_members"
    assert summary.atomic_workflow_result_commit is True
    assert summary.max_steers == 0
    assert summary.interactive_session_schema_version == (
        "interactive_terminal_turn_queue.v1"
    )
    validate_workflow_runtime_plan(plan, workflow, projection)


@pytest.mark.parametrize("member_count", [1, 9])
def test_provider_peer_group_rejects_member_count_outside_closed_bounds(
    member_count: int,
) -> None:
    config = _config(member_ids=("one", "two"))
    members = list(config.members)
    if member_count == 1:
        invalid_members = (members[0],)
    else:
        invalid_members = tuple(
            [
                *members,
                *(
                    ProviderPeerGroupMemberConfig(
                        member_id=f"extra-{index}",
                        provider_config=_provider_config(
                            f"extra-{index}",
                            20,
                        ),
                        result_contract=_contract(),
                        timeout_sec=20,
                    )
                    for index in range(7)
                ),
            ]
        )
    workflow, _ = _workflow(replace(config, members=invalid_members))

    with pytest.raises(
        WorkflowValidationError,
        match="2 through 8",
    ):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda config: replace(config, schema_version="provider_peer_group.v2"),
        lambda config: replace(config, node_id="root.other"),
        lambda config: replace(config, common=None),  # type: ignore[arg-type]
        lambda config: replace(
            config,
            members=list(config.members),  # type: ignore[arg-type]
        ),
        lambda config: replace(
            config,
            members=(
                config.members[0],
                replace(
                    config.members[1],
                    member_id=config.members[0].member_id,
                ),
                *config.members[2:],
            ),
        ),
        lambda config: replace(
            config,
            members=tuple(reversed(config.members)),
        ),
        lambda config: replace(
            config,
            members=(
                replace(config.members[0], timeout_sec=0),
                *config.members[1:],
            ),
        ),
        lambda config: replace(
            config,
            members=(
                replace(
                    config.members[0],
                    provider_config=replace(
                        config.members[0].provider_config,
                        common=replace(
                            config.members[0].provider_config.common,
                            timeout_sec=99,
                        ),
                    ),
                ),
                *config.members[1:],
            ),
        ),
        lambda config: replace(
            config,
            members=(
                replace(
                    config.members[0],
                    provider_config=replace(
                        config.members[0].provider_config,
                        compiler_prompt_dependency_contract=None,
                    ),
                ),
                *config.members[1:],
            ),
        ),
        lambda config: replace(
            config,
            members=(
                replace(
                    config.members[0],
                    provider_config=replace(
                        config.members[0].provider_config,
                        inject_output_contract=False,
                    ),
                ),
                *config.members[1:],
            ),
        ),
        lambda config: replace(config, messaging_policy="directed_edges"),
        lambda config: replace(
            config,
            interactive_session_schema_version="provider-name-inference",
        ),
        lambda config: replace(config, max_steers=1),
        lambda config: replace(config, max_steers=False),
        lambda config: replace(
            config,
            common=replace(config.common, timeout_sec=29),
        ),
        lambda config: replace(
            config,
            common=replace(config.common, timeout_sec=31),
        ),
    ],
)
def test_provider_peer_group_rejects_schema_member_policy_and_timeout_tampering(
    mutate,
) -> None:
    workflow, _ = _workflow(mutate(_config()))

    with pytest.raises(WorkflowValidationError):
        validate_executable_workflow(workflow)


def test_provider_peer_group_rejects_bool_provider_timeout_equal_to_integer_one(
) -> None:
    config = _config(member_ids=("one", "two"))
    first_member = replace(
        config.members[0],
        timeout_sec=1,
        provider_config=replace(
            config.members[0].provider_config,
            common=replace(
                config.members[0].provider_config.common,
                timeout_sec=True,
            ),
        ),
    )
    workflow, _ = _workflow(
        replace(
            config,
            members=(first_member, *config.members[1:]),
        )
    )

    with pytest.raises(
        WorkflowValidationError,
        match="provider timeout must be a positive integer",
    ):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda config: replace(
            config,
            settlement_payload=MappingProxyType(
                {
                    **dict(config.settlement_payload),
                    "bindings": MappingProxyType(
                        {
                            key: value
                            for key, value in config.settlement_payload[
                                "bindings"
                            ].items()
                            if key != "builder"
                        }
                    ),
                }
            ),
        ),
        lambda config: replace(
            config,
            settlement_payload=MappingProxyType(
                {
                    **dict(config.settlement_payload),
                    "bindings": MappingProxyType(
                        {
                            key: config.settlement_payload["bindings"][key]
                            for key in reversed(
                                tuple(
                                    config.settlement_payload["bindings"]
                                )
                            )
                        }
                    ),
                }
            ),
        ),
        lambda config: replace(
            config,
            settlement_payload=MappingProxyType(
                {
                    **dict(config.settlement_payload),
                    "bindings": MappingProxyType(
                        {
                            **dict(config.settlement_payload["bindings"]),
                            "intruder": MappingProxyType(
                                {"type": _STRING_TYPE}
                            ),
                        }
                    ),
                }
            ),
        ),
        lambda config: replace(
            config,
            settlement_payload=MappingProxyType(
                {
                    **dict(config.settlement_payload),
                    "bindings": MappingProxyType(
                        {
                            **dict(config.settlement_payload["bindings"]),
                            "author": MappingProxyType(
                                {
                                    "type": MappingProxyType(
                                        {
                                            "kind": "primitive",
                                            "name": "Bool",
                                        }
                                    )
                                }
                            ),
                        }
                    ),
                }
            ),
        ),
        lambda config: replace(
            config,
            settlement_result_contract=replace(
                config.settlement_result_contract,
                name="Bool",
                value_type="bool",
                definition=MappingProxyType(
                    {
                        "type": MappingProxyType(
                            {"kind": "primitive", "name": "Bool"}
                        )
                    }
                ),
            ),
        ),
    ],
)
def test_provider_peer_group_rejects_settlement_tampering(mutate) -> None:
    workflow, _ = _workflow(mutate(_config()))

    with pytest.raises(WorkflowValidationError, match="settlement"):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    "member_ids",
    [
        ("builder", "reviewer", "author"),
        ("author", "reviewer"),
        ("author", "reviewer", "builder", "extra"),
    ],
)
def test_provider_peer_group_rejects_reordered_missing_or_extra_path_members(
    member_ids: tuple[str, ...],
) -> None:
    config = _config()
    workflow, _ = _workflow(
        replace(
            config,
            paths=derive_provider_peer_group_paths(
                node_id=config.node_id,
                member_ids=member_ids,
            ),
        )
    )

    with pytest.raises(WorkflowValidationError, match="path plan"):
        validate_executable_workflow(workflow)


@pytest.mark.parametrize(
    "mutate_ownership",
    [
        lambda ownership: replace(
            ownership,
            members=tuple(reversed(ownership.members)),
        ),
        lambda ownership: replace(
            ownership,
            members=ownership.members[:-1],
        ),
        lambda ownership: replace(
            ownership,
            members=(
                *ownership.members,
                ProviderPeerGroupMemberSourceOwnership(
                    member_id="extra",
                    binding="source:extra",
                ),
            ),
        ),
        lambda ownership: replace(ownership, form=""),
        lambda ownership: replace(
            ownership,
            members=(
                replace(ownership.members[0], binding=""),
                *ownership.members[1:],
            ),
        ),
    ],
)
def test_provider_peer_group_rejects_source_ownership_tampering(
    mutate_ownership,
) -> None:
    config = _config()
    workflow, _ = _workflow(
        replace(
            config,
            source_ownership=mutate_ownership(config.source_ownership),
        )
    )

    with pytest.raises(WorkflowValidationError, match="source ownership"):
        validate_executable_workflow(workflow)


def test_provider_peer_group_config_constructor_rejects_missing_or_extra_fields() -> None:
    kwargs = dict(_config().__dict__)
    kwargs.pop("messaging_policy")
    with pytest.raises(TypeError):
        ProviderPeerGroupStepConfig(**kwargs)

    with pytest.raises(TypeError):
        ProviderPeerGroupStepConfig(
            **dict(_config().__dict__),
            unexpected=True,  # type: ignore[call-arg]
        )
