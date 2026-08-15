"""Post-WCC lowering acceptance for static provider peer groups."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import time
from typing import Any

import pytest

import orchestrator.providers.interactive_terminal as interactive_terminal_module
from orchestrator.cli.commands.run import run_workflow
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_bundle as loaded_workflow_bundle,
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.pure_result_replay import DERIVED_PURE_REPLAY_PROFILE
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from tests.workflow_bundle_helpers import bundle_context_dict
from orchestrator.providers.interactive_terminal import (
    CloseOfferReceipt,
    FailedCleanupProof,
    InteractiveMemberHandle,
    InteractiveMemberInvocation,
    InteractiveTerminalError,
    NaturalShutdownProof,
    OfferReceipt,
)
from orchestrator.workflow_lisp.wcc import defunctionalize as defunctionalize_module
from orchestrator.providers.types import (
    INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION,
)
from orchestrator.workflow.executable_ir import (
    PROVIDER_PEER_GROUP_MESSAGING_POLICY,
    PROVIDER_PEER_GROUP_SCHEMA_VERSION,
    ExecutableNodeKind,
    ProviderPeerGroupStepConfig,
)
from orchestrator.workflow.prompt_dependency_contract import (
    PromptDependencyOriginKind,
    PromptDependencyPosition,
    _build_compiler_prompt_dependency_contract,
    serialize_compiler_prompt_dependency_contract,
    validate_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.provider_peer_group.paths import (
    derive_provider_peer_group_paths,
)
from orchestrator.workflow.provider_peer_group.bindings import (
    PEER_DELIVERY_FRAME_HEADER,
    WorkflowProviderPeerGroupBindings,
)
from orchestrator.workflow.provider_peer_group.models import (
    PeerAcknowledgeReceipt,
    PeerFinishReceipt,
    PeerReadyReceipt,
    PeerSendReceipt,
)
from orchestrator.workflow.provider_peer_group.protocol import (
    _decode_active_peer_binding,
    peer_ack,
    peer_finish,
    peer_ready,
    peer_send,
)
from orchestrator.state import StateManager
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp import (
    lexical_checkpoints as lexical_checkpoints_module,
)
from orchestrator.workflow_lisp.lexical_checkpoint_effect_policies import (
    build_effect_resume_policy,
)
from orchestrator.workflow_lisp.lexical_checkpoints import (
    checkpoint_runtime_program_identity,
    validate_checkpoint_point_payload,
)


_PUBLIC_FIXTURE_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "provider_peer_group"
)
_PUBLIC_FIXTURE_FILES = (
    "provider_peer_group_three.orc",
    "providers.json",
    "prompts.json",
    "real_adapter_prompt.md",
)
_PUBLIC_MESSAGE = "Review this literal 🌍 payload.\nSecond line: Ω"


def _peer_group_source() -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.17")',
            "  (defpath RequiredContext :kind relpath :under \".\" "
            ":must-exist false)",
            "  (defrecord TeamResult",
            "    (plan String)",
            "    (approved Bool)",
            "    (notes String))",
            "  (defworkflow orchestrate ((required_path RequiredContext)) "
            "-> TeamResult",
            "    (with-live-provider-peers",
            "      ((planner",
            "         (provider-result providers.planner",
            "           :prompt prompts.planner",
            "           :inputs ()",
            "           :prompt-dependencies",
            "             (:required (required_path)",
            "              :position append",
            '              :instruction "Use the bound context.")',
            "           :timeout-sec 30",
            "           :returns String))",
            "       (reviewer",
            "         (provider-result providers.reviewer",
            "           :prompt prompts.reviewer",
            "           :inputs ()",
            "           :timeout-sec 20",
            "           :returns Bool))",
            "       (builder",
            "         (provider-result providers.builder",
            "           :prompt prompts.builder",
            "           :inputs ()",
            "           :timeout-sec 40",
            "           :returns String)))",
            "      (record TeamResult",
            "        :plan planner",
            "        :approved reviewer",
            "        :notes builder))))",
        )
    )


_PEER_MEMBER_IDS = (
    "planner",
    "reviewer",
    "builder",
    "tester",
    "analyst",
    "editor",
    "auditor",
    "publisher",
)


def _peer_group_source_with_member_count(member_count: int) -> str:
    member_ids = _PEER_MEMBER_IDS[:member_count]
    bindings = "\n".join(
        "\n".join(
            (
                f"       ({member_id}",
                f"         (provider-result providers.{member_id}",
                f"           :prompt prompts.{member_id}",
                "           :inputs ()",
                f"           :timeout-sec {20 + index}",
                "           :returns String))",
            )
        )
        for index, member_id in enumerate(member_ids)
    )
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.17")',
            "  (defworkflow orchestrate () -> String",
            "    (with-live-provider-peers",
            f"      ({bindings})",
            f"      {member_ids[-1]})))",
        )
    )


def _compile_peer_group(
    tmp_path: Path,
    *,
    source: str | None = None,
    planner_provider: str = "planner-provider",
    validate_shared: bool = False,
    member_ids: tuple[str, ...] = ("planner", "reviewer", "builder"),
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "provider_peer_group.orc"
    path.write_text(source or _peer_group_source(), encoding="utf-8")
    for member_id in member_ids:
        prompt_path = tmp_path / "prompts" / f"{member_id}.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(f"{member_id} prompt\n", encoding="utf-8")
    return compile_stage3_module(
        path,
        entry_workflow="orchestrate",
        provider_externs={
            f"providers.{member_id}": (
                planner_provider
                if member_id == "planner"
                else f"{member_id}-provider"
            )
            for member_id in member_ids
        },
        prompt_externs={
            f"prompts.{member_id}": f"prompts/{member_id}.md"
            for member_id in member_ids
        },
        validate_shared=validate_shared,
        workspace_root=tmp_path,
    )


def _lowered_peer_config_and_checkpoint(compiled):
    lowered = next(
        workflow
        for workflow in compiled.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )
    [step] = lowered.authored_mapping["steps"]
    [checkpoint] = lowered.lexical_checkpoint_points
    return step["provider_peer_group"], checkpoint


def test_wcc_peer_group_defunctionalizes_to_one_distinct_typed_config(
    tmp_path: Path,
) -> None:
    compiled = _compile_peer_group(tmp_path)
    lowered = next(
        workflow
        for workflow in compiled.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )

    [step] = lowered.authored_mapping["steps"]
    assert set(step) == {
        "name",
        "id",
        "timeout_sec",
        "provider_peer_group",
    }
    assert "provider_supervision" not in step
    assert "provider" not in step
    config = step["provider_peer_group"]
    assert isinstance(config, ProviderPeerGroupStepConfig)
    assert config.schema_version == PROVIDER_PEER_GROUP_SCHEMA_VERSION
    assert config.messaging_policy == PROVIDER_PEER_GROUP_MESSAGING_POLICY
    assert config.interactive_session_schema_version == (
        INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION
    )
    assert config.max_steers == 0

    member_ids = tuple(member.member_id for member in config.members)
    assert member_ids == ("planner", "reviewer", "builder")
    assert tuple(member.provider_config.provider for member in config.members) == (
        "planner-provider",
        "reviewer-provider",
        "builder-provider",
    )
    assert len({id(member.provider_config) for member in config.members}) == 3
    assert len({id(member.result_contract) for member in config.members}) == 3
    assert tuple(member.result_contract.name for member in config.members) == (
        "String",
        "Bool",
        "String",
    )
    assert tuple(member.result_contract.value_type for member in config.members) == (
        "string",
        "bool",
        "string",
    )
    assert tuple(member.timeout_sec for member in config.members) == (30, 20, 40)
    assert config.common.timeout_sec == 40
    assert tuple(config.settlement_payload["bindings"]) == member_ids
    assert config.settlement_result_contract.name == "TeamResult"
    assert config.settlement_result_contract.kind == "record"
    assert config.settlement_result_contract.value_type == "TeamResult"
    assert config.paths == derive_provider_peer_group_paths(
        node_id=config.node_id,
        member_ids=member_ids,
    )

    ownership = config.source_ownership
    source_owners = (
        ownership.form,
        *(member.binding for member in ownership.members),
        ownership.settlement,
    )
    assert tuple(member.member_id for member in ownership.members) == member_ids
    assert len(source_owners) == len(member_ids) + 2
    assert len(set(source_owners)) == len(source_owners)

    optional_prompt_contracts = tuple(
        member.provider_config.compiler_prompt_dependency_contract
        for member in config.members
    )
    assert all(
        contract is not None
        for contract in optional_prompt_contracts
    )
    prompt_contracts = tuple(
        contract
        for contract in optional_prompt_contracts
        if contract is not None
    )
    assert all(
        validate_compiler_prompt_dependency_contract(contract) is contract
        for contract in prompt_contracts
    )
    assert prompt_contracts[0].origin_kind is (
        PromptDependencyOriginKind
        .WORKFLOW_LISP_PROVIDER_RESULT_PROMPT_DEPENDENCIES
    )
    assert tuple(contract.origin_kind for contract in prompt_contracts[1:]) == (
        PromptDependencyOriginKind
        .WORKFLOW_LISP_PROVIDER_PEER_GROUP_MEMBER_IMPLICIT_EMPTY,
    ) * 2

    origin_map = lowered.origin_map
    assert origin_map.provider_supervision_origins == {}
    assert origin_map.provider_supervision_prompt_dependency_lineages == ()
    assert lowered.compiler_prompt_dependency_contracts == {}
    assert origin_map.prompt_dependency_lineages == ()
    prompt_origin_keys = tuple(
        contract.source_origin_key for contract in prompt_contracts
    )
    assert set((*source_owners, *prompt_origin_keys)) == set(
        origin_map.provider_peer_group_origins
    )
    assert tuple(
        lineage.source_origin_key
        for lineage in origin_map.provider_peer_group_prompt_dependency_lineages
    ) == (prompt_origin_keys[0],)

    [checkpoint] = lowered.lexical_checkpoint_points
    assert checkpoint["point_kind"] == "effect_boundary"
    assert checkpoint["step_id"] == config.node_id == step["id"]
    assert checkpoint["step_kind"] == "provider_peer_group"
    assert checkpoint["effect_boundary"]["effect_kind"] == (
        "provider_peer_group"
    )
    assert checkpoint["effect_boundary"]["boundary_kind"] == (
        "provider_peer_group"
    )
    assert checkpoint["effect_boundary"]["policy"]["policy_kind"] == (
        "fail_closed_non_idempotent"
    )
    assert checkpoint["effect_boundary"]["policy"]["effect_kind"] == (
        "provider_peer_group"
    )
    assert checkpoint["effect_boundary"]["policy"]["boundary_kind"] == (
        "provider_peer_group"
    )
    assert checkpoint["effect_boundary"]["policy"]["evidence_requirements"] == {}
    assert checkpoint["effect_boundary"]["policy"][
        "unsafe_pending_behavior"
    ] == "fail_closed"
    assert checkpoint["runtime_program_identity"]["wcc_node_id"] == (
        ownership.form
    )
    assert checkpoint["executable_identity"][
        "identity_component_digest"
    ] == defunctionalize_module._sha256_json(
        defunctionalize_module._provider_peer_group_checkpoint_identity_payload(
            config,
            target_dsl_version="2.17",
        )
    )


@pytest.mark.parametrize("member_count", (2, 3, 8))
def test_peer_group_two_through_eight_members_cross_every_executable_projection(
    tmp_path: Path,
    member_count: int,
) -> None:
    member_ids = _PEER_MEMBER_IDS[:member_count]
    compiled = _compile_peer_group(
        tmp_path,
        source=_peer_group_source_with_member_count(member_count),
        validate_shared=True,
        member_ids=member_ids,
    )
    bundle = compiled.validated_bundles["orchestrate"]

    assert bundle.ir.schema_version == "workflow_executable_ir.v1"
    assert bundle.runtime_plan.schema_version == "workflow_runtime_plan.v1"
    assert bundle.semantic_ir.schema_version == "workflow_semantic_ir.v1"
    [core_statement] = bundle.core_workflow_ast.body
    [node] = bundle.ir.nodes.values()
    assert isinstance(
        core_statement.provider_peer_group,
        ProviderPeerGroupStepConfig,
    )
    assert node.kind is ExecutableNodeKind.PROVIDER_PEER_GROUP
    assert isinstance(node.execution_config, ProviderPeerGroupStepConfig)
    assert tuple(
        member.member_id for member in node.execution_config.members
    ) == member_ids
    assert len(bundle.ir.nodes) == 1

    runtime_node = bundle.runtime_plan.nodes[node.node_id]
    assert runtime_node.provider_peer_group is not None
    assert runtime_node.provider_peer_group.member_ids == member_ids

    semantic_workflow = bundle.semantic_ir.workflows["orchestrate"]
    [semantic_statement] = semantic_workflow.statements.values()
    [effect_id] = semantic_statement.effect_ids
    effect = bundle.semantic_ir.effects[effect_id]
    assert semantic_statement.step_kind == "provider_peer_group"
    assert effect.effect_kind == "provider_peer_group"
    assert tuple(
        member["member_id"] for member in effect.details["members"]
    ) == member_ids

    [checkpoint] = bundle.runtime_plan.lexical_checkpoint_points
    assert checkpoint.details["step_kind"] == "provider_peer_group"
    assert checkpoint.details["executable_identity"][
        "identity_component_digest"
    ].startswith("sha256:")


def test_peer_checkpoint_identity_binds_full_typed_config(
    tmp_path: Path,
) -> None:
    baseline_config, baseline = _lowered_peer_config_and_checkpoint(
        _compile_peer_group(
            tmp_path / "baseline",
            planner_provider="planner-provider-a",
        )
    )
    provider_config, provider_changed = _lowered_peer_config_and_checkpoint(
        _compile_peer_group(
            tmp_path / "provider-changed",
            planner_provider="planner-provider-b",
        )
    )
    timeout_config, timeout_changed = _lowered_peer_config_and_checkpoint(
        _compile_peer_group(
            tmp_path / "timeout-changed",
            source=_peer_group_source().replace(
                ":timeout-sec 30",
                ":timeout-sec 31",
                1,
            ),
            planner_provider="planner-provider-a",
        )
    )
    assert baseline_config.members[0].provider_config.provider != (
        provider_config.members[0].provider_config.provider
    )
    assert baseline_config.members[0].timeout_sec != (
        timeout_config.members[0].timeout_sec
    )

    identity_fields = (
        "program_point_id",
        "checkpoint_id",
    )
    for changed in (provider_changed, timeout_changed):
        for field in identity_fields:
            assert changed[field] != baseline[field]
        assert changed["binding_schema"]["schema_digest"] != (
            baseline["binding_schema"]["schema_digest"]
        )
        assert changed["executable_identity"][
            "identity_component_digest"
        ] != baseline["executable_identity"]["identity_component_digest"]


def test_peer_checkpoint_config_digest_is_sensitive_to_every_field_class(
    tmp_path: Path,
) -> None:
    config, _checkpoint = _lowered_peer_config_and_checkpoint(
        _compile_peer_group(tmp_path)
    )
    identity_payload = getattr(
        defunctionalize_module,
        "_provider_peer_group_checkpoint_identity_payload",
    )

    def digest(
        candidate: ProviderPeerGroupStepConfig,
        *,
        target_dsl_version: str = "2.17",
    ) -> str:
        return defunctionalize_module._sha256_json(
            identity_payload(
                candidate,
                target_dsl_version=target_dsl_version,
            )
        )

    baseline = digest(config)
    first = config.members[0]
    second = config.members[1]
    variants = (
        replace(config, members=(second, first, *config.members[2:])),
        replace(
            config,
            members=(
                replace(
                    first,
                    provider_config=replace(
                        first.provider_config,
                        provider="alternate-provider",
                    ),
                ),
                *config.members[1:],
            ),
        ),
        replace(
            config,
            members=(
                replace(
                    first,
                    result_contract=replace(
                        first.result_contract,
                        name="AlternateString",
                    ),
                ),
                *config.members[1:],
            ),
        ),
        replace(config, messaging_policy="closed-test-policy"),
        replace(
            config,
            settlement_payload={
                **dict(config.settlement_payload),
                "expr": {"kind": "binding", "name": "builder"},
            },
        ),
        replace(
            config,
            settlement_result_contract=replace(
                config.settlement_result_contract,
                name="AlternateTeamResult",
            ),
        ),
        replace(config, schema_version="provider_peer_group.test"),
        replace(
            config,
            interactive_session_schema_version=(
                "interactive_terminal_turn_queue.test"
            ),
        ),
        replace(config, max_steers=1),
        replace(
            config,
            common=replace(
                config.common,
                timeout_sec=config.common.timeout_sec + 1,
            ),
        ),
        replace(
            config,
            members=(
                replace(first, timeout_sec=first.timeout_sec + 1),
                *config.members[1:],
            ),
        ),
        replace(
            config,
            paths=derive_provider_peer_group_paths(
                node_id=f"{config.node_id}-alternate",
                member_ids=tuple(
                    member.member_id for member in config.members
                ),
            ),
        ),
        replace(
            config,
            source_ownership=replace(
                config.source_ownership,
                form=f"{config.source_ownership.form}:alternate",
            ),
        ),
    )
    assert all(digest(variant) != baseline for variant in variants)
    assert digest(config, target_dsl_version="2.18") != baseline


def test_runtime_checkpoint_program_identity_binds_peer_config_component(
    tmp_path: Path,
) -> None:
    compiled = _compile_peer_group(
        tmp_path / "compiled",
        validate_shared=True,
    )
    bundle = compiled.validated_bundles["orchestrate"]
    state_manager = StateManager(tmp_path, run_id="peer-config-identity")
    baseline = checkpoint_runtime_program_identity(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
    )
    (point,) = bundle.runtime_plan.lexical_checkpoint_points
    executable_identity = dict(point.details["executable_identity"])
    component_digest = executable_identity["identity_component_digest"]
    assert component_digest.startswith("sha256:")
    identity_point = (
        lexical_checkpoints_module._runtime_program_identity_point(
            point,
            component_required=True,
        )
    )
    assert identity_point["effect_policy_digest"] == point.details[
        "effect_boundary"
    ]["policy"]["policy_digest"]

    tampered_point = replace(
        point,
        details={
            **dict(point.details),
            "executable_identity": {
                **executable_identity,
                "identity_component_digest": "sha256:" + "0" * 64,
            },
        },
    )
    tampered = checkpoint_runtime_program_identity(
        state_manager=state_manager,
        runtime_plan=replace(
            bundle.runtime_plan,
            lexical_checkpoint_points=(tampered_point,),
        ),
    )
    assert tampered["executable_ir_digest"] != baseline["executable_ir_digest"]
    assert tampered["semantic_ir_digest"] != baseline["semantic_ir_digest"]


@pytest.mark.parametrize(
    "component_digest",
    (
        None,
        "",
        "sha256:not-a-digest",
    ),
)
def test_runtime_checkpoint_program_identity_rejects_missing_or_malformed_peer_component(
    tmp_path: Path,
    component_digest: str | None,
) -> None:
    compiled = _compile_peer_group(
        tmp_path / "compiled",
        validate_shared=True,
    )
    bundle = compiled.validated_bundles["orchestrate"]
    (point,) = bundle.runtime_plan.lexical_checkpoint_points
    executable_identity = dict(point.details["executable_identity"])
    if component_digest is None:
        executable_identity.pop("identity_component_digest")
    else:
        executable_identity["identity_component_digest"] = component_digest
    invalid_point = replace(
        point,
        details={
            **dict(point.details),
            "executable_identity": executable_identity,
        },
    )

    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_program_identity_mismatch",
    ):
        checkpoint_runtime_program_identity(
            state_manager=StateManager(
                tmp_path,
                run_id="peer-config-identity-invalid",
            ),
            runtime_plan=replace(
                bundle.runtime_plan,
                lexical_checkpoint_points=(invalid_point,),
            ),
        )


def test_runtime_checkpoint_program_identity_requires_one_component_point_per_peer_node(
    tmp_path: Path,
) -> None:
    compiled = _compile_peer_group(
        tmp_path / "compiled",
        validate_shared=True,
    )
    bundle = compiled.validated_bundles["orchestrate"]
    (point,) = bundle.runtime_plan.lexical_checkpoint_points
    executable_identity = dict(point.details["executable_identity"])
    executable_identity.pop("identity_component_digest")
    disguised_point = replace(
        point,
        details={
            **dict(point.details),
            "step_kind": "provider",
            "executable_identity": executable_identity,
        },
    )
    state_manager = StateManager(tmp_path, run_id="peer-node-identity")

    for lexical_points in ((disguised_point,), ()):
        with pytest.raises(
            ValueError,
            match="lexical_checkpoint_program_identity_mismatch",
        ):
            checkpoint_runtime_program_identity(
                state_manager=state_manager,
                runtime_plan=replace(
                    bundle.runtime_plan,
                    lexical_checkpoint_points=lexical_points,
                ),
            )


@pytest.mark.parametrize("defect", ("step_kind", "policy"))
def test_peer_checkpoint_rejects_reusable_boundary_disguise(
    tmp_path: Path,
    defect: str,
) -> None:
    compiled = _compile_peer_group(
        tmp_path / "compiled",
        validate_shared=True,
    )
    bundle = compiled.validated_bundles["orchestrate"]
    (point,) = bundle.runtime_plan.lexical_checkpoint_points
    reusable_policy = build_effect_resume_policy(
        policy_kind="reuse_validated_structured_output",
        effect_kind="provider_call",
        boundary_kind="provider",
        step_id=point.details["effect_boundary"]["policy"]["step_id"],
        source_map_origin_key=point.origin_key,
        evidence_requirements={
            "structured_output": {
                "bundle_path_ref": "generated:provider_bundle",
                "contract_digest": "sha256:" + "0" * 64,
                "payload_digest_required": True,
                "declared_target_only": True,
            }
        },
    )
    details = dict(point.details)
    if defect == "step_kind":
        details["step_kind"] = "provider"
    else:
        details["effect_boundary"] = {
            **dict(point.details["effect_boundary"]),
            "policy": reusable_policy,
        }
    disguised_point = replace(
        point,
        details=details,
    )

    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_program_identity_mismatch",
    ):
        validate_checkpoint_point_payload(
            lexical_checkpoints_module._point_payload(disguised_point)
        )
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_program_identity_mismatch",
    ):
        checkpoint_runtime_program_identity(
            state_manager=StateManager(
                tmp_path,
                run_id="peer-policy-disguise",
            ),
            runtime_plan=replace(
                bundle.runtime_plan,
                lexical_checkpoint_points=(disguised_point,),
            ),
        )


def test_peer_implicit_empty_prompt_contract_is_evidence_valid_and_closed() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        _validate_contract,
    )

    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=(),
        optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND,
        instruction=None,
        source_origin_key="peer-group:member",
        source_workflow_bytes=b"(workflow-lisp)",
        origin_kind=(
            PromptDependencyOriginKind
            .WORKFLOW_LISP_PROVIDER_PEER_GROUP_MEMBER_IMPLICIT_EMPTY
        ),
    )
    wire = serialize_compiler_prompt_dependency_contract(contract)

    assert _validate_contract(wire) == wire
    with pytest.raises(ValueError, match="forbid dependency refs"):
        _build_compiler_prompt_dependency_contract(
            required_binding_refs=("unexpected",),
            optional_binding_refs=(),
            position=PromptDependencyPosition.PREPEND,
            instruction=None,
            source_origin_key="peer-group:invalid-member",
            source_workflow_bytes=b"(workflow-lisp)",
            origin_kind=(
                PromptDependencyOriginKind
                .WORKFLOW_LISP_PROVIDER_PEER_GROUP_MEMBER_IMPLICIT_EMPTY
            ),
        )


def _public_two_member_source() -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.17")',
            "  (defmodule provider_peer_group_three)",
            "  (export orchestrate)",
            "  (defworkflow orchestrate () -> String",
            "    (with-live-provider-peers",
            "      ((planner",
            "         (provider-result providers.planner",
            "           :prompt prompts.planner",
            "           :inputs ()",
            "           :timeout-sec 10",
            "           :returns String))",
            "       (reviewer",
            "         (provider-result providers.reviewer",
            "           :prompt prompts.reviewer",
            "           :inputs ()",
            "           :timeout-sec 10",
            "           :returns String)))",
            "      reviewer)))",
        )
    )


def _copy_public_fixture(
    workspace: Path,
    *,
    member_count: int,
) -> dict[str, Path]:
    copied: dict[str, Path] = {}
    for name in _PUBLIC_FIXTURE_FILES:
        destination = workspace / name
        destination.write_bytes((_PUBLIC_FIXTURE_ROOT / name).read_bytes())
        copied[name] = destination
    if member_count == 2:
        copied["provider_peer_group_three.orc"].write_text(
            _public_two_member_source(),
            encoding="utf-8",
        )
        for manifest_name in ("providers.json", "prompts.json"):
            payload = json.loads(
                copied[manifest_name].read_text(encoding="utf-8")
            )
            payload = {
                key: value
                for key, value in payload.items()
                if not key.endswith(".builder")
            }
            copied[manifest_name].write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    return copied


def _public_run_args(files: dict[str, Path]) -> Namespace:
    source = files["provider_peer_group_three.orc"]
    return Namespace(
        workflow=str(source),
        context=None,
        context_file=None,
        input=None,
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=False,
        backup_state=False,
        state_dir=None,
        on_error="stop",
        max_retries=0,
        retry_delay=0,
        quiet=True,
        verbose=False,
        log_level="error",
        step_summaries=False,
        summary_mode=None,
        summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow="orchestrate",
        source_root=[str(source.parent)],
        provider_externs_file=str(files["providers.json"]),
        prompt_externs_file=str(files["prompts.json"]),
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=False,
    )


def _only_public_run(workspace: Path) -> tuple[Path, dict[str, Any]]:
    run_roots = list((workspace / ".orchestrate" / "runs").iterdir())
    assert len(run_roots) == 1
    run_root = run_roots[0]
    return run_root, json.loads(
        (run_root / "state.json").read_text(encoding="utf-8")
    )


@dataclass
class _ControlledPeerHarness:
    member_ids: tuple[str, ...]
    values: dict[str, object]
    failure_mode: str | None = None
    message_acknowledged: Event = field(default_factory=Event)
    adapters: dict[str, "_ControlledPeerAdapter"] = field(
        default_factory=dict
    )
    offered_targets: list[str] = field(default_factory=list)
    exact_bundle_bytes: dict[str, bytes] = field(default_factory=dict)
    endpoint_paths: set[Path] = field(default_factory=set)

    def create_adapter(
        self,
        member: object,
    ) -> "_ControlledPeerAdapter":
        member_id = member.runtime.attempt.member_id
        adapter = _ControlledPeerAdapter(self, member_id)
        self.adapters[member_id] = adapter
        return adapter


class _ControlledPeerAdapter:
    def __init__(
        self,
        harness: _ControlledPeerHarness,
        member_id: str,
    ) -> None:
        self.harness = harness
        self.member_id = member_id
        self.handle: InteractiveMemberHandle | None = None
        self.offers: Queue[tuple[str, str] | None] = Queue()
        self.stop_requested = Event()
        self.done = Event()
        self.thread: Thread | None = None
        self.error: BaseException | None = None
        self.joined = False
        self.aborted = False

    def start(
        self,
        invocation: InteractiveMemberInvocation,
        *,
        deadline: float,
    ) -> object:
        assert deadline > time.monotonic()
        endpoint_path, _sender_binding = _decode_active_peer_binding(
            invocation.env
        )
        self.harness.endpoint_paths.add(endpoint_path)
        if (
            self.harness.failure_mode == "launch"
            and self.member_id == self.harness.member_ids[0]
        ):
            start_outcome_type = getattr(
                interactive_terminal_module,
                "InteractiveTerminalStartOutcome",
            )
            no_allocation_type = getattr(
                interactive_terminal_module,
                "NoBackendAllocationProof",
            )
            return start_outcome_type(
                status="failed",
                error_code="pane_start_failed",
                backend_allocation="none",
                cleanup_status="not_required",
                provider_zero_survivor_proven=True,
                proof=no_allocation_type(
                    disposition="no_backend_allocation",
                    backend_resource_allocated=False,
                    proof_complete=True,
                ),
            )
        handle = InteractiveMemberHandle(
            adapter_instance_id=f"controlled-adapter:{self.member_id}",
            handle_id=f"controlled-handle:{self.member_id}",
            invocation_id=invocation.invocation_id,
            member_id=invocation.member_id,
            attempt_scope_key=invocation.attempt_scope_key,
            attempt_ordinal=invocation.attempt_ordinal,
            target=f"controlled:{self.member_id}",
            socket_path=Path(
                f"/tmp/provider-peer-controlled-{self.member_id}.sock"
            ),
        )
        self.handle = handle
        self.thread = Thread(
            target=self._run_script,
            args=(invocation,),
            name=f"controlled-peer:{self.member_id}",
            daemon=True,
        )
        self.thread.start()
        start_outcome_type = getattr(
            interactive_terminal_module,
            "InteractiveTerminalStartOutcome",
        )
        return start_outcome_type(status="started", handle=handle)

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt:
        assert handle == self.handle
        assert deadline > time.monotonic()
        self.harness.offered_targets.append(self.member_id)
        if (
            self.harness.failure_mode == "offer"
            and self.member_id == self.harness.member_ids[1]
        ):
            raise InteractiveTerminalError(
                "injected_offer_failure",
            )
        lines = literal_message.split("\n", 4)
        assert lines[0] == PEER_DELIVERY_FRAME_HEADER
        assert lines[1].startswith("message_id: ")
        assert lines[2].startswith("sender_member_id: ")
        assert lines[3] == ""
        self.offers.put((lines[1].removeprefix("message_id: "), lines[4]))
        payload = literal_message.encode("utf-8")
        return OfferReceipt(
            status="offered",
            handle_id=handle.handle_id,
            byte_count=len(payload),
            content_sha256=(
                "sha256:" + hashlib.sha256(payload).hexdigest()
            ),
        )

    def offer_close(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> CloseOfferReceipt:
        assert handle == self.handle
        assert deadline > time.monotonic()
        return CloseOfferReceipt(
            status="close_offered",
            handle_id=handle.handle_id,
        )

    def join(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> NaturalShutdownProof:
        assert handle == self.handle
        thread = self.thread
        assert thread is not None
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
        self.joined = not thread.is_alive()
        return NaturalShutdownProof(
            disposition="natural_exit",
            handle_id=handle.handle_id,
            return_code=0,
            pane_absent=self.joined,
            server_absent=self.joined,
            proof_complete=self.joined,
        )

    def abort(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> FailedCleanupProof:
        assert handle == self.handle
        self.aborted = True
        self.stop_requested.set()
        self.offers.put(None)
        thread = self.thread
        assert thread is not None
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
        complete = not thread.is_alive()
        return FailedCleanupProof(
            disposition="failed_cleanup",
            handle_id=handle.handle_id,
            pane_absent=complete,
            server_absent=complete,
            cleanup_complete=complete,
            error_code=None if complete else "controlled_thread_alive",
        )

    def _run_script(
        self,
        invocation: InteractiveMemberInvocation,
    ) -> None:
        environ = dict(invocation.env)
        try:
            ready = peer_ready(
                request_id=f"ready:{self.member_id}",
                environ=environ,
            )
            assert isinstance(ready, PeerReadyReceipt)
            if self.member_id == self.harness.member_ids[0]:
                sent = peer_send(
                    target_binding=self.harness.member_ids[1],
                    message=_PUBLIC_MESSAGE,
                    request_id=f"send:{self.member_id}",
                    environ=environ,
                )
                assert isinstance(sent, PeerSendReceipt)
            elif self.member_id == self.harness.member_ids[1]:
                try:
                    offered = self.offers.get(timeout=5)
                except Empty as exc:
                    raise AssertionError(
                        "controlled peer message was not offered"
                    ) from exc
                if offered is None:
                    return
                message_id, content = offered
                assert content == _PUBLIC_MESSAGE
                acknowledged = peer_ack(
                    message_id=message_id,
                    request_id=f"ack:{self.member_id}",
                    environ=environ,
                )
                assert isinstance(
                    acknowledged,
                    PeerAcknowledgeReceipt,
                )
                self.harness.message_acknowledged.set()
            while not self.harness.message_acknowledged.wait(0.01):
                if self.stop_requested.is_set():
                    return

            value = self.harness.values[self.member_id]
            exact_bytes = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if (
                self.harness.failure_mode == "bundle"
                and self.member_id == self.harness.member_ids[1]
            ):
                exact_bytes = b"{invalid"
            output_path = Path(
                invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
            )
            output_path.write_bytes(exact_bytes)
            self.harness.exact_bundle_bytes[self.member_id] = exact_bytes
            finished = peer_finish(
                request_id=f"finish:{self.member_id}",
                environ=environ,
            )
            assert isinstance(finished, PeerFinishReceipt)
            assert finished.status == "close_offered"
        except BaseException as exc:
            self.error = exc
        finally:
            self.done.set()


def _install_controlled_public_adapters(
    monkeypatch: pytest.MonkeyPatch,
    *,
    member_ids: tuple[str, ...],
    values: dict[str, object],
    failure_mode: str | None = None,
) -> _ControlledPeerHarness:
    harness = _ControlledPeerHarness(
        member_ids=member_ids,
        values=values,
        failure_mode=failure_mode,
    )

    def create_adapter(
        _self: WorkflowProviderPeerGroupBindings,
        member: object,
    ) -> _ControlledPeerAdapter:
        return harness.create_adapter(member)

    monkeypatch.setattr(
        WorkflowProviderPeerGroupBindings,
        "create_adapter",
        create_adapter,
    )
    return harness


@pytest.mark.parametrize("member_count", (2, 3))
def test_public_run_executes_controlled_provider_peer_group_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    member_count: int,
) -> None:
    files = _copy_public_fixture(tmp_path, member_count=member_count)
    member_ids = ("planner", "reviewer", "builder")[:member_count]
    values: dict[str, object] = {
        "planner": "plan 🌍\nline two",
        "reviewer": (
            "review ✓\naccepted"
            if member_count == 2
            else True
        ),
        "builder": "notes Ω\nfinal",
    }
    monkeypatch.chdir(tmp_path)
    harness = _install_controlled_public_adapters(
        monkeypatch,
        member_ids=member_ids,
        values=values,
    )

    assert run_workflow(_public_run_args(files)) == 0

    run_root, state = _only_public_run(tmp_path)
    assert state["status"] == "completed"
    [step] = state["steps"].values()
    assert step["status"] == "completed"
    expected_artifacts = (
        {"__result__": values["reviewer"]}
        if member_count == 2
        else {
            "plan": values["planner"],
            "approved": values["reviewer"],
            "notes": values["builder"],
        }
    )
    assert step["artifacts"] == expected_artifacts
    assert state["workflow_outputs"] == (
        expected_artifacts
        if member_count == 2
        else {
            f"return__{name}": value
            for name, value in expected_artifacts.items()
        }
    )
    assert harness.offered_targets == ["reviewer"]
    assert set(harness.exact_bundle_bytes) == set(member_ids)
    assert {
        path.read_bytes()
        for path in run_root.rglob("provisional-result.json")
    } == set(harness.exact_bundle_bytes.values())
    assert all(
        adapter.error is None
        and adapter.joined
        and not adapter.aborted
        and adapter.thread is not None
        and not adapter.thread.is_alive()
        for adapter in harness.adapters.values()
    )

    terminal_path = (
        run_root
        / step["debug"]["provider_peer_group"][
            "terminal_evidence_path"
        ]
    )
    terminal = json.loads(terminal_path.read_text(encoding="ascii"))
    assert terminal["outcome"] == "completed"
    assert terminal["settlement_sha256"].startswith("sha256:")
    assert terminal["endpoint_drained"] is True
    assert terminal["endpoint_closed"] is True
    assert terminal["endpoint_workers_joined"] is True
    assert len(terminal["members"]) == member_count
    for member in terminal["members"]:
        member_id = member["attempt"]["member_id"]
        exact = harness.exact_bundle_bytes[member_id]
        assert member["frozen_bundle_sha256"] == (
            "sha256:" + hashlib.sha256(exact).hexdigest()
        )
        counts = member["ledger"]["counts"]
        assert counts == (
            {
                "recorded": 1,
                "offered": 1,
                "offer_failed": 0,
                "receiver_acknowledged": 1,
            }
            if member_id == "reviewer"
            else {
                "recorded": 0,
                "offered": 0,
                "offer_failed": 0,
                "receiver_acknowledged": 0,
            }
        )
    ledger_rows = [
        json.loads(line)
        for path in run_root.rglob("injected-messages.jsonl")
        for line in path.read_text(encoding="ascii").splitlines()
    ]
    recorded = [
        row for row in ledger_rows if row["row_kind"] == "recorded"
    ]
    assert len(recorded) == 1
    assert recorded[0]["content"] == _PUBLIC_MESSAGE
    assert recorded[0]["receiver_attempt"]["member_id"] == "reviewer"
    assert harness.endpoint_paths
    assert all(not path.exists() for path in harness.endpoint_paths)


@pytest.mark.parametrize(
    "failure_mode",
    ("launch", "offer", "bundle", "settlement"),
)
def test_public_run_peer_group_failures_never_publish_or_retarget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    files = _copy_public_fixture(tmp_path, member_count=3)
    member_ids = ("planner", "reviewer", "builder")
    values: dict[str, object] = {
        "planner": "plan",
        "reviewer": True,
        "builder": "notes",
    }
    monkeypatch.chdir(tmp_path)
    harness = _install_controlled_public_adapters(
        monkeypatch,
        member_ids=member_ids,
        values=values,
        failure_mode=failure_mode,
    )
    if failure_mode == "settlement":
        def fail_settlement(
            _self: WorkflowProviderPeerGroupBindings,
            *,
            resolved_bindings: object,
        ) -> object:
            del resolved_bindings
            raise ValueError("injected settlement failure")

        monkeypatch.setattr(
            WorkflowProviderPeerGroupBindings,
            "evaluate_settlement",
            fail_settlement,
        )

    assert run_workflow(_public_run_args(files)) == 1

    run_root, state = _only_public_run(tmp_path)
    assert state["status"] == "failed"
    assert state["workflow_outputs"] == {}
    assert state.get("artifact_versions", {}) == {}
    [step] = state["steps"].values()
    assert step["status"] == "failed"
    assert not step.get("artifacts")
    terminal_path = (
        run_root
        / step["debug"]["provider_peer_group"][
            "terminal_evidence_path"
        ]
    )
    terminal = json.loads(terminal_path.read_text(encoding="ascii"))
    assert terminal["outcome"] == "failed"
    assert terminal["settlement_sha256"] is None
    assert set(harness.offered_targets) <= {"reviewer"}
    assert all(
        adapter.thread is None or not adapter.thread.is_alive()
        for adapter in harness.adapters.values()
    )
    assert harness.endpoint_paths
    assert all(not path.exists() for path in harness.endpoint_paths)


def _pre_provider_input_files(tmp_path: Path) -> dict[str, Path]:
    """Write a target-2.26 peer group whose planner consumes a pure `if` input."""

    (tmp_path / "prompts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts" / "planner.md").write_text("Plan.\n", encoding="utf-8")
    (tmp_path / "prompts" / "reviewer.md").write_text("Review.\n", encoding="utf-8")
    source = tmp_path / "pre_provider_input.orc"
    source.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule pre_provider_input)",
                "  (export orchestrate)",
                "  (defworkflow orchestrate ((a Bool) (b Bool)) -> String",
                "    (with-live-provider-peers",
                "      ((planner",
                "         (let* ((flag (if a b false)))",
                "           (provider-result providers.planner",
                "             :prompt prompts.planner :inputs (flag)",
                "             :timeout-sec 30 :returns String)))",
                "       (reviewer",
                "         (provider-result providers.reviewer",
                "           :prompt prompts.reviewer :inputs ()",
                "           :timeout-sec 20 :returns Bool)))",
                "      planner)))",
            ]
        ),
        encoding="utf-8",
    )
    providers = tmp_path / "providers.json"
    providers.write_text(
        json.dumps(
            {"providers.planner": "codex", "providers.reviewer": "codex"},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts.json"
    prompts.write_text(
        json.dumps(
            {"prompts.planner": "prompts/planner.md", "prompts.reviewer": "prompts/reviewer.md"},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "provider_peer_group_three.orc": source,
        "providers.json": providers,
        "prompts.json": prompts,
    }


def _run_inputs(files: dict[str, Path]) -> Namespace:
    args = _public_run_args(files)
    args.input = ["a=true", "b=true"]
    return args


def test_pre_provider_input_peer_runtime_and_resume_reuses_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _pre_provider_input_files(tmp_path)
    member_ids = ("planner", "reviewer")
    values: dict[str, object] = {"planner": "plan", "reviewer": True}
    monkeypatch.chdir(tmp_path)
    harness = _install_controlled_public_adapters(
        monkeypatch,
        member_ids=member_ids,
        values=values,
    )

    assert run_workflow(_run_inputs(files)) == 0

    run_root, state = _only_public_run(tmp_path)
    assert state["status"] == "completed"
    projection_steps = [
        name for name in state["steps"] if name.endswith("__flag")
    ]
    assert len(projection_steps) == 1
    assert state["steps"][projection_steps[0]]["status"] == "completed"
    assert state["steps"][projection_steps[0]]["visit_count"] == 1

    # The projection is a pure_projection step whose ordinary checkpoint
    # policy reuses the settled result on a resume of the same run.
    projection_state = state["steps"][projection_steps[0]]
    assert projection_state["visit_count"] == 1
    # derived_pure_replay.v1 is the ordinary pure-projection checkpoint replay
    # policy: a resume of the same run reuses the settled value without
    # re-evaluating the selection.
    assert projection_state["result_storage"] == "derived_pure_replay.v1"
    assert all(not path.exists() for path in harness.endpoint_paths)


def test_pre_provider_input_peer_downstream_failure_resume_reuses_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forced settlement failure downstream of the prelude is resumed and the
    prelude projection is replayed rather than re-evaluated."""

    files = _pre_provider_input_files(tmp_path)
    member_ids = ("planner", "reviewer")
    values: dict[str, object] = {"planner": "plan", "reviewer": True}
    monkeypatch.chdir(tmp_path)

    # Build the bundle directly so the same run can be resumed at the executor.
    source = files["provider_peer_group_three.orc"]
    bundle = loaded_workflow_bundle(
        build_frontend_bundle(
            FrontendBuildRequest(
                source_path=source.resolve(),
                source_roots=(tmp_path,),
                entry_workflow="orchestrate",
                provider_externs_path=files["providers.json"].resolve(),
                prompt_externs_path=files["prompts.json"].resolve(),
                workspace_root=tmp_path,
            )
        ).validated_bundle
    )
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        name: contract
        for name, contract in runtime_inputs.items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        binding_inputs, {"a": "true", "b": "true"}, tmp_path
    )

    harness = _install_controlled_public_adapters(
        monkeypatch,
        member_ids=member_ids,
        values=values,
    )

    def fail_settlement(_self, *, resolved_bindings):
        del resolved_bindings
        raise ValueError("injected settlement failure")

    monkeypatch.setattr(
        WorkflowProviderPeerGroupBindings,
        "evaluate_settlement",
        fail_settlement,
    )

    state_manager = StateManager(workspace=tmp_path, run_id="peer_downstream_fail")
    state_manager.initialize(
        source.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
        result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
    )
    first = WorkflowExecutor(
        bundle, tmp_path, state_manager, retry_delay_ms=0
    ).execute(on_error="stop")
    assert first["status"] == "failed"
    (projection_name,) = [
        name for name in first["steps"] if name.endswith("__flag")
    ]
    projection = first["steps"][projection_name]
    assert projection["status"] == "completed"
    assert projection["visit_count"] == 1
    # The selected typed input (`if a b false` with a=b=true) is the
    # projection's durable result.
    assert projection["artifacts"]["__result__"] is True

    # Resume the same run with the settlement failure still in place. The
    # non-idempotent peer group re-runs and fails again, but the prelude
    # projection is replayed from its durable result instead of re-evaluated.
    resumed = WorkflowExecutor(
        bundle,
        tmp_path,
        _resume_manager(tmp_path, "peer_downstream_fail"),
        retry_delay_ms=0,
    ).execute(resume=True)
    assert resumed["status"] == "failed"
    # No repeated prelude work: the projection's visit count is unchanged and
    # its durable value is replayed rather than re-computed.
    assert resumed["steps"][projection_name]["visit_count"] == 1
    assert (
        resumed["steps"][projection_name]["result_storage"]
        == "derived_pure_replay.v1"
    )
    (peer_name,) = [
        name for name in resumed["steps"] if name.endswith("__result")
    ]
    assert resumed["steps"][peer_name]["visit_count"] == 2


def _resume_manager(workspace: Path, run_id: str) -> StateManager:
    manager = StateManager(workspace=workspace, run_id=run_id)
    manager.load()
    return manager
