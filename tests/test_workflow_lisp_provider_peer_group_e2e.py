"""Post-WCC lowering acceptance for static provider peer groups."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

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
