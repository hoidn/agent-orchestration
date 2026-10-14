"""Integration tests for runtime step lifecycle state updates."""

import importlib
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from orchestrator.workflow.runtime_step import RuntimeStep


@pytest.mark.parametrize(("target_dsl", "with_output"), (("2.20", False), ("2.21", False), ("2.21", True)))
def test_runtime_step_q1_q2_historical_mapping_omits_q3_authority(
    tmp_path: Path,
    target_dsl: str,
    with_output: bool,
) -> None:
    node = _historical_provider_node(tmp_path, with_output=with_output, q3=False)
    step = RuntimeStep(
        node=node,
        name=node.presentation_name,
        step_id=node.step_id,
        target_dsl_version=target_dsl,
    )

    assert step.compiler_prompt_fragment_contract is node.execution_config.compiler_prompt_fragment_contract
    assert "prompt_attempt_identity_version" not in step
    assert "compiler_prompt_attempt_binding_plan" not in step


def test_runtime_step_exposes_immutable_q3_pair_accessors(
    tmp_path: Path,
) -> None:
    node = _historical_provider_node(tmp_path, with_output=True, q3=True)
    config = node.execution_config

    step = RuntimeStep(
        node=node,
        name=node.presentation_name,
        step_id=node.step_id,
    )

    assert step.prompt_attempt_identity_version == (
        config.prompt_attempt_identity_version
    )
    assert step.compiler_prompt_attempt_binding_plan is (
        config.compiler_prompt_attempt_binding_plan
    )
    assert "prompt_attempt_identity_version" not in step.to_compat_dict()
    assert "compiler_prompt_attempt_binding_plan" not in step.to_compat_dict()
    with pytest.raises(FrozenInstanceError):
        step.prompt_attempt_identity_version = "changed"


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    (
        ("drop_version", "prompt_attempt_identity_version_missing"),
        ("drop_plan", "prompt_attempt_binding_plan_missing"),
        ("mutate_version", "prompt_attempt_identity_version_invalid"),
        ("mutate_digest", "prompt_attempt_binding_plan_invalid"),
    ),
)
def test_runtime_step_rejects_dropped_or_mutated_q3_pair(
    tmp_path: Path,
    mutation: str,
    diagnostic: str,
) -> None:
    node = _historical_provider_node(tmp_path, with_output=True, q3=True)
    config = node.execution_config
    version = config.prompt_attempt_identity_version
    plan = config.compiler_prompt_attempt_binding_plan
    plan_digest = plan.plan_sha256
    try:
        if mutation == "drop_version":
            object.__setattr__(
                config,
                "prompt_attempt_identity_version",
                None,
            )
        elif mutation == "drop_plan":
            object.__setattr__(
                config,
                "compiler_prompt_attempt_binding_plan",
                None,
            )
        elif mutation == "mutate_version":
            object.__setattr__(
                config,
                "prompt_attempt_identity_version",
                "workflow_prompt_attempt_identity.v999",
            )
        elif mutation == "mutate_digest":
            object.__setattr__(plan, "plan_sha256", "sha256:" + "0" * 64)
        else:
            raise AssertionError(mutation)

        with pytest.raises(ValueError, match=diagnostic):
            RuntimeStep(
                node=node,
                name=node.presentation_name,
                step_id=node.step_id,
            )
    finally:
        object.__setattr__(
            config,
            "prompt_attempt_identity_version",
            version,
        )
        object.__setattr__(
            config,
            "compiler_prompt_attempt_binding_plan",
            plan,
        )
        object.__setattr__(plan, "plan_sha256", plan_digest)


def test_runtime_step_rejects_complete_q3_pair_loss_with_target_authority(
    tmp_path: Path,
) -> None:
    node = _historical_provider_node(tmp_path, with_output=True, q3=True)
    config = node.execution_config
    version = config.prompt_attempt_identity_version
    plan = config.compiler_prompt_attempt_binding_plan
    object.__setattr__(config, "prompt_attempt_identity_version", None)
    object.__setattr__(
        config,
        "compiler_prompt_attempt_binding_plan",
        None,
    )
    try:
        with pytest.raises(
            ValueError,
            match="prompt_attempt_identity_version_missing",
        ):
            RuntimeStep(
                node=node,
                name=node.presentation_name,
                step_id=node.step_id,
                target_dsl_version="2.22",
            )
    finally:
        object.__setattr__(
            config,
            "prompt_attempt_identity_version",
            version,
        )
        object.__setattr__(
            config,
            "compiler_prompt_attempt_binding_plan",
            plan,
        )


def test_runtime_step_q2_boundary_validates_common_expected_outputs(
    tmp_path: Path,
) -> None:
    runtime_step_module = importlib.import_module(
        "orchestrator.workflow.runtime_step"
    )
    provider_node = _historical_provider_node(tmp_path, with_output=True, q3=False)
    runtime_step_module.RuntimeStep(
        node=provider_node,
        name=provider_node.presentation_name,
        step_id=provider_node.step_id,
    )

    config = provider_node.execution_config
    object.__setattr__(
        config,
        "common",
        replace(config.common, expected_outputs=()),
    )
    with pytest.raises(
        ValueError,
        match="prompt_output_position_contract_mismatch",
    ):
        runtime_step_module.RuntimeStep(
            node=provider_node,
            name=provider_node.presentation_name,
            step_id=provider_node.step_id,
        )


def _historical_provider_node(tmp_path, *, with_output, q3):
    from orchestrator.workflow.executable_ir import LeafExecutableNode, ExecutableNodeKind, WorkflowRegion, ProviderStepConfig, StepCommonConfig
    from tests.test_workflow_lisp_prompt_identity_persistence import _q3_bundle, _legacy_fragment_bundle
    bundle = (_q3_bundle(tmp_path, with_output=with_output) if q3 else _legacy_fragment_bundle(tmp_path, target_dsl="2.21" if with_output else "2.20", with_output=with_output, name="historical::fragment"))
    surface = bundle.surface.steps[0]
    config = ProviderStepConfig(
        common=StepCommonConfig(expected_outputs=surface.common.expected_outputs),
        provider=surface.provider,
        compiler_prompt_fragment_contract=surface.compiler_prompt_fragment_contract,
        compiled_prompt_fragment_identity=surface.compiled_prompt_fragment_identity,
        prompt_attempt_identity_version=surface.prompt_attempt_identity_version,
        compiler_prompt_attempt_binding_plan=surface.compiler_prompt_attempt_binding_plan,
        compiler_prompt_dependency_contract=surface.compiler_prompt_dependency_contract,
        typed_prompt_inputs=surface.typed_prompt_inputs,
    )
    return LeafExecutableNode(node_id="root.review", step_id="review", presentation_name="Review", kind=ExecutableNodeKind.PROVIDER, region=WorkflowRegion.BODY, lexical_scope=(), execution_config=config)
