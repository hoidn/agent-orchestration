"""Closed executable-IR tests for provider peer groups."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import MappingProxyType

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.providers.types import (
    INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION,
)
from orchestrator.workflow import core_ast as core_ast_module
from orchestrator.workflow import executable_ir as ir_module
from orchestrator.workflow import semantic_ir as semantic_ir_module
from orchestrator.workflow.core_ast import (
    build_core_workflow_ast,
    lower_core_workflow_ast,
    workflow_core_ast_to_json,
)
from orchestrator.workflow.elaboration import elaborate_surface_workflow
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
from orchestrator.workflow.lowering import (
    LoweringError,
    _IRBuilder,
    build_loaded_workflow_bundle,
)
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
            .WORKFLOW_LISP_PROVIDER_PEER_GROUP_MEMBER_IMPLICIT_EMPTY
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


def _generated_surface(
    config: ProviderPeerGroupStepConfig,
) -> SurfaceWorkflow:
    provenance = WorkflowProvenance(
        workflow_path=Path("/tmp/generated.orc"),
        source_root=Path("/tmp"),
        frontend_kind="workflow_lisp",
    )
    return SurfaceWorkflow(
        version="2.17",
        name="generated-peers",
        steps=(
            SurfaceStep(
                name="Peers",
                step_id="root.peers",
                authored_id="peers",
                kind=SurfaceStepKind.PROVIDER_PEER_GROUP,
                common=SurfaceStepCommonConfig(
                    timeout_sec=config.common.timeout_sec,
                ),
                provider_peer_group=config,
            ),
        ),
        provenance=provenance,
    )


def _peer_bundle():
    surface = _generated_surface(_config(node_id="peers"))
    return build_loaded_workflow_bundle(surface, imports={})


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


def test_provider_peer_group_has_a_distinct_generated_surface_slot() -> None:
    assert SurfaceStepKind.PROVIDER_PEER_GROUP.value == "provider_peer_group"
    assert "provider_peer_group" in SurfaceStep.__dataclass_fields__


def test_generated_peer_group_traverses_one_core_and_executable_node() -> None:
    original_config = _config(node_id="peers")
    surface = _generated_surface(original_config)

    core = build_core_workflow_ast(surface, {}, surface.provenance)
    assert len(core.body) == 1
    assert isinstance(
        core.body[0],
        getattr(core_ast_module, "CoreProviderPeerGroupStep"),
    )
    assert core.body[0].provider_peer_group is original_config

    executable, _projection = lower_core_workflow_ast(core)
    assert executable.schema_version == WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION
    assert tuple(executable.nodes) == ("root.peers",)
    node = executable.nodes["root.peers"]
    assert node.kind is ExecutableNodeKind.PROVIDER_PEER_GROUP
    assert isinstance(node.execution_config, ProviderPeerGroupStepConfig)
    assert node.execution_config.node_id == node.node_id
    assert tuple(
        member.member_id for member in node.execution_config.members
    ) == ("author", "reviewer", "builder")
    assert node.execution_config.paths == derive_provider_peer_group_paths(
        node_id=node.node_id,
        member_ids=("author", "reviewer", "builder"),
    )
    assert original_config.node_id == "peers"


def test_peer_group_core_json_is_canonical_without_changing_envelope() -> None:
    config = _config(node_id="peers")
    surface = _generated_surface(config)
    core = build_core_workflow_ast(surface, {}, surface.provenance)

    payload = workflow_core_ast_to_json(core)

    assert payload["schema_version"] == "core_workflow_ast.v1"
    [statement] = payload["body"]
    assert statement["kind"] == "provider_peer_group"
    peer_group = statement["provider_peer_group"]
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
    assert [
        member["member_id"] for member in peer_group["members"]
    ] == ["author", "reviewer", "builder"]
    assert [
        member["member_id"] for member in peer_group["paths"]["members"]
    ] == ["author", "reviewer", "builder"]
    assert (
        peer_group["members"][0]["provider_config"][
            "compiler_prompt_dependency_contract"
        ]["origin_kind"]
        == "workflow_lisp_provider_peer_group_member_implicit_empty"
    )
    assert peer_group["max_steers"] == 0


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda config: MappingProxyType({}),
            "typed compiler-generated config",
        ),
        (
            lambda config: _config(node_id="other"),
            "generated node id",
        ),
        (
            lambda config: replace(
                config,
                common=replace(config.common, timeout_sec=99),
            ),
            "common config",
        ),
        (
            lambda config: replace(
                config,
                paths=derive_provider_peer_group_paths(
                    node_id=config.node_id,
                    member_ids=("builder", "reviewer", "author"),
                ),
            ),
            "path plan",
        ),
        (
            lambda config: replace(
                config,
                paths=derive_provider_peer_group_paths(
                    node_id=config.node_id,
                    member_ids=("author", "reviewer"),
                ),
            ),
            "path plan",
        ),
        (
            lambda config: replace(
                config,
                paths=derive_provider_peer_group_paths(
                    node_id=config.node_id,
                    member_ids=(
                        "author",
                        "reviewer",
                        "builder",
                        "intruder",
                    ),
                ),
            ),
            "path plan",
        ),
    ],
    ids=(
        "untyped",
        "node_id",
        "common",
        "paths_reordered",
        "paths_missing",
        "paths_extra",
    ),
)
def test_peer_group_lowering_rejects_prebind_contract_tampering(
    mutate,
    message: str,
) -> None:
    config = _config(node_id="peers")
    surface = _generated_surface(config)
    tampered_step = replace(
        surface.steps[0],
        provider_peer_group=mutate(config),
    )
    tampered_surface = replace(surface, steps=(tampered_step,))
    core = build_core_workflow_ast(
        tampered_surface,
        {},
        tampered_surface.provenance,
    )

    with pytest.raises(LoweringError, match=message):
        lower_core_workflow_ast(core)


def test_peer_group_semantic_ir_projects_the_exact_executable_contract() -> None:
    config = _config(node_id="peers")
    surface = _generated_surface(config)

    bundle = build_loaded_workflow_bundle(surface, imports={})

    assert bundle.semantic_ir.schema_version == "workflow_semantic_ir.v1"
    workflow = bundle.semantic_ir.workflows["generated-peers"]
    assert len(workflow.statements) == 1
    [statement] = workflow.statements.values()
    assert statement.step_kind == "provider_peer_group"
    assert statement.executable_node_ids == ("root.peers",)
    assert len(statement.effect_ids) == 1
    [effect_id] = statement.effect_ids
    effect = bundle.semantic_ir.effects[effect_id]
    assert effect.effect_kind == "provider_peer_group"

    semantic_payload = semantic_ir_module.workflow_semantic_ir_to_json(
        bundle.semantic_ir
    )
    details = semantic_payload["effects"][effect_id]["details"]
    executable_config = workflow_executable_ir_to_json(bundle.ir)["nodes"][
        "root.peers"
    ]["execution_config"]
    assert details == {
        "target_dsl_version": "2.17",
        **executable_config,
    }
    assert [
        member["member_id"] for member in details["members"]
    ] == ["author", "reviewer", "builder"]
    assert details["messaging_policy"] == "all_other_members"
    assert details["max_steers"] == 0
    assert details["interactive_session_schema_version"] == (
        "interactive_terminal_turn_queue.v1"
    )
    assert set(details["settlement_payload"]["bindings"]) == {
        "author",
        "reviewer",
        "builder",
    }
    assert [
        member["member_id"] for member in details["paths"]["members"]
    ] == ["author", "reviewer", "builder"]
    assert all(
        candidate.effect_kind
        not in {"provider_call", "provider_supervision"}
        for candidate in bundle.semantic_ir.effects.values()
    )


def _tamper_peer_semantic_details(
    details: dict[str, object],
    defect: str,
) -> dict[str, object]:
    if defect == "target":
        details["target_dsl_version"] = "2.18"
    elif defect == "common":
        details["common"]["timeout_sec"] = 999  # type: ignore[index]
    elif defect == "members_reordered":
        details["members"] = list(reversed(details["members"]))  # type: ignore[arg-type]
    elif defect == "members_missing":
        details["members"] = details["members"][:-1]  # type: ignore[index]
    elif defect == "members_extra":
        extra = deepcopy(details["members"][0])  # type: ignore[index]
        extra["member_id"] = "intruder"
        details["members"] = [*details["members"], extra]  # type: ignore[misc]
    elif defect == "provider":
        details["members"][0]["provider_config"]["provider"] = "wrong"  # type: ignore[index]
    elif defect == "result_contract":
        details["members"][0]["result_contract"]["name"] = "Wrong"  # type: ignore[index]
    elif defect == "policy":
        details["messaging_policy"] = "directed_edges"
    elif defect == "capability":
        details["interactive_session_schema_version"] = "wrong.v1"
    elif defect == "max_steers":
        details["max_steers"] = 1
    elif defect == "settlement_payload":
        details["settlement_payload"]["expr"]["name"] = "reviewer"  # type: ignore[index]
    elif defect == "settlement_contract":
        details["settlement_result_contract"]["name"] = "Wrong"  # type: ignore[index]
    elif defect == "paths_reordered":
        members = details["paths"]["members"]  # type: ignore[index]
        details["paths"]["members"] = list(reversed(members))  # type: ignore[index,arg-type]
    elif defect == "paths_missing":
        members = details["paths"]["members"]  # type: ignore[index]
        details["paths"]["members"] = members[:-1]  # type: ignore[index]
    elif defect == "paths_extra":
        members = details["paths"]["members"]  # type: ignore[index]
        extra = deepcopy(members[0])  # type: ignore[index]
        extra["member_id"] = "intruder"
        details["paths"]["members"] = [*members, extra]  # type: ignore[index,misc]
    elif defect == "prompt_ownership":
        contract = details["members"][0]["provider_config"][  # type: ignore[index]
            "compiler_prompt_dependency_contract"
        ]
        contract["source_origin_key"] = "source:wrong"
    elif defect == "source_ownership":
        members = details["source_ownership"]["members"]  # type: ignore[index]
        details["source_ownership"]["members"] = list(  # type: ignore[index]
            reversed(members)  # type: ignore[arg-type]
        )
    else:
        raise AssertionError(f"unknown semantic defect {defect}")
    return details


@pytest.mark.parametrize(
    "defect",
    (
        "target",
        "common",
        "members_reordered",
        "members_missing",
        "members_extra",
        "provider",
        "result_contract",
        "policy",
        "capability",
        "max_steers",
        "settlement_payload",
        "settlement_contract",
        "paths_reordered",
        "paths_missing",
        "paths_extra",
        "prompt_ownership",
        "source_ownership",
    ),
)
def test_peer_group_semantic_ir_rejects_exact_contract_tampering(
    defect: str,
) -> None:
    bundle = _peer_bundle()
    workflow = bundle.semantic_ir.workflows["generated-peers"]
    [statement] = workflow.statements.values()
    [effect_id] = statement.effect_ids
    effect = bundle.semantic_ir.effects[effect_id]
    serialized_details = (
        semantic_ir_module.workflow_semantic_ir_to_json(
            bundle.semantic_ir
        )["effects"][effect_id]["details"]
    )
    tampered_effect = replace(
        effect,
        details=MappingProxyType(
            _tamper_peer_semantic_details(
                deepcopy(serialized_details),
                defect,
            )
        ),
    )
    tampered = replace(
        bundle.semantic_ir,
        effects=MappingProxyType(
            {
                **dict(bundle.semantic_ir.effects),
                effect_id: tampered_effect,
            }
        ),
    )

    with pytest.raises(
        WorkflowValidationError,
        match="provider peer group effect",
    ):
        semantic_ir_module.validate_workflow_semantic_ir(
            tampered,
            ir=bundle.ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
            surface=bundle.surface,
            imports={},
        )


@pytest.mark.parametrize(
    "defect",
    (
        "workflow_name",
        "boundary_metadata",
        "call_target",
        "output_validation_surface",
        "source_map_behavior",
        "ref_ids",
    ),
)
def test_peer_group_semantic_ir_rejects_effect_metadata_tampering(
    defect: str,
) -> None:
    bundle = _peer_bundle()
    workflow = bundle.semantic_ir.workflows["generated-peers"]
    [statement] = workflow.statements.values()
    [effect_id] = statement.effect_ids
    effect = bundle.semantic_ir.effects[effect_id]
    kwargs: dict[str, object]
    if defect == "workflow_name":
        kwargs = {"workflow_name": "wrong"}
    elif defect == "boundary_metadata":
        kwargs = {
            "boundary_kind": "certified_adapter",
            "boundary_name": "fake",
        }
    elif defect == "call_target":
        kwargs = {"call_target": "wrong"}
    elif defect == "output_validation_surface":
        kwargs = {"output_validation_surface": "wrong"}
    elif defect == "source_map_behavior":
        kwargs = {"source_map_behavior": "wrong"}
    elif defect == "ref_ids":
        assert bundle.semantic_ir.refs
        kwargs = {"ref_ids": (next(iter(bundle.semantic_ir.refs)),)}
    else:
        raise AssertionError(f"unknown effect metadata defect {defect}")
    tampered_effect = replace(effect, **kwargs)
    tampered = replace(
        bundle.semantic_ir,
        effects=MappingProxyType(
            {
                **dict(bundle.semantic_ir.effects),
                effect_id: tampered_effect,
            }
        ),
    )

    with pytest.raises(
        WorkflowValidationError,
        match="provider peer group effect",
    ):
        semantic_ir_module.validate_workflow_semantic_ir(
            tampered,
            ir=bundle.ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
            surface=bundle.surface,
            imports={},
        )


@pytest.mark.parametrize(
    "defect",
    (
        "missing_effect",
        "extra_effect_listed",
        "extra_effect_catalog_only",
        "relabelled_effect",
        "relabelled_statement",
        "relabelled_statement_to_v1",
        "erased_node_and_effect",
        "missing_statement",
    ),
)
def test_peer_group_semantic_ir_rejects_noncanonical_projection(
    defect: str,
) -> None:
    bundle = _peer_bundle()
    workflow_name = "generated-peers"
    workflow = bundle.semantic_ir.workflows[workflow_name]
    [statement] = workflow.statements.values()
    [effect_id] = statement.effect_ids
    effect = bundle.semantic_ir.effects[effect_id]
    effects = dict(bundle.semantic_ir.effects)
    statements = dict(workflow.statements)

    if defect == "missing_effect":
        statements[statement.statement_id] = replace(
            statement,
            effect_ids=(),
        )
        effects.pop(effect_id)
    elif defect in {"extra_effect_listed", "extra_effect_catalog_only"}:
        extra_effect_id = f"{effect_id}:extra"
        effects[extra_effect_id] = replace(
            effect,
            effect_id=extra_effect_id,
            effect_kind="unknown_test_effect",
        )
        if defect == "extra_effect_listed":
            statements[statement.statement_id] = replace(
                statement,
                effect_ids=(*statement.effect_ids, extra_effect_id),
            )
    elif defect == "relabelled_effect":
        effects[effect_id] = replace(
            effect,
            effect_kind="provider_supervision",
        )
    elif defect == "relabelled_statement":
        statements[statement.statement_id] = replace(
            statement,
            step_kind="provider",
        )
    elif defect == "relabelled_statement_to_v1":
        statements[statement.statement_id] = replace(
            statement,
            step_kind="provider_supervision",
        )
    elif defect == "erased_node_and_effect":
        statements[statement.statement_id] = replace(
            statement,
            executable_node_ids=(),
            effect_ids=(),
        )
        effects.pop(effect_id)
    elif defect == "missing_statement":
        statements.pop(statement.statement_id)
        effects.pop(effect_id)
    else:
        raise AssertionError(f"unknown projection defect {defect}")

    tampered_workflow = replace(
        workflow,
        authored_statement_ids=tuple(statements),
        statements=MappingProxyType(statements),
    )
    tampered = replace(
        bundle.semantic_ir,
        workflows=MappingProxyType(
            {
                **dict(bundle.semantic_ir.workflows),
                workflow_name: tampered_workflow,
            }
        ),
        effects=MappingProxyType(effects),
    )

    with pytest.raises(
        WorkflowValidationError,
        match="provider peer group",
    ):
        semantic_ir_module.validate_workflow_semantic_ir(
            tampered,
            ir=bundle.ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
            surface=bundle.surface,
            imports={},
        )


def test_generated_mapping_elaborates_one_typed_peer_group_surface() -> None:
    config = _config(node_id="peers")
    surface = elaborate_surface_workflow(
        {
            "version": "2.17",
            "name": "generated-peers",
            "steps": [
                {
                    "name": "Peers",
                    "id": "peers",
                    "timeout_sec": config.common.timeout_sec,
                    "provider_peer_group": config,
                }
            ],
        },
        workflow_path=Path("/tmp/generated.orc"),
        imported_bundles={},
        allow_generated_step_kinds=True,
    )

    assert surface is not None
    assert len(surface.steps) == 1
    [step] = surface.steps
    assert step.kind is SurfaceStepKind.PROVIDER_PEER_GROUP
    assert step.provider_peer_group is config
    assert step.step_id == "root.peers"
    assert step.authored_id == "peers"


@pytest.mark.parametrize(
    "steps",
    [
        [
            {
                "name": "ForbiddenPeers",
                "provider_peer_group": {},
            }
        ],
        [
            {
                "name": "Nested",
                "for_each": {
                    "items": ["one"],
                    "as": "item",
                    "steps": [
                        {
                            "name": "ForbiddenPeers",
                            "provider_peer_group": {},
                        }
                    ],
                },
            }
        ],
    ],
    ids=("top_level", "nested"),
)
def test_classic_authored_mapping_cannot_construct_provider_peer_group(
    tmp_path: Path,
    steps: list[dict[str, object]],
) -> None:
    result = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping={
                "version": "2.17",
                "name": "classic-authored",
                "steps": steps,
            },
            workflow_path=tmp_path / "classic.orc",
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
        "provider_peer_group is compiler-generated only" in error.message
        for error in result.errors
    )


def test_production_projection_reruns_interrupted_peer_group_visit() -> None:
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
        "kind": "rerun_interrupted_visit",
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
