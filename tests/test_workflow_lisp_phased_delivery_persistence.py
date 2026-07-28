"""Target-2.23 phased-delivery persistence and checkpoint carriage."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import (
    ProviderStepConfig,
    StepCommonConfig,
)
from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.prompt_fragment_contract import (
    PHASED_PROMPT_ATTEMPT_IDENTITY_VERSION,
    PROMPT_ATTEMPT_IDENTITY_VERSION,
)
from orchestrator.workflow.surface_ast import SurfaceStepKind
from orchestrator.workflow_lisp import lexical_checkpoints
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from tests.test_workflow_lisp_prompt_identity_persistence import _q3_bundle


REPO_ROOT = Path(__file__).resolve().parent.parent
PHASED_FIXTURE = (
    REPO_ROOT
    / "tests/fixtures/workflow_lisp/phased_contract_delivery/phased.orc"
)


def _phased_surface_bundle(tmp_path: Path):
    bundle = _q3_bundle(tmp_path, with_output=True)
    provider = next(
        step
        for step in bundle.surface.steps
        if step.kind is SurfaceStepKind.PROVIDER
    )
    phased = replace(
        provider,
        provider_call_policy={
            "model": "unchanged-provider-model",
            "effort": "high",
            "delivery": "phased",
            "materialization_attempts": 2,
        },
        prompt_attempt_identity_version=(
            PHASED_PROMPT_ATTEMPT_IDENTITY_VERSION
        ),
    )
    return replace(
        bundle,
        surface=replace(
            bundle.surface,
            version="2.23",
            steps=(phased,),
        ),
    )


def _phased_payload(tmp_path: Path) -> dict[str, object]:
    return serialize_persisted_workflow_surface_graph(
        _phased_surface_bundle(tmp_path)
    )


def _provider_wire(payload: dict[str, object]) -> dict[str, object]:
    nodes = payload["nodes"]
    assert isinstance(nodes, dict)
    node = next(iter(nodes.values()))
    assert isinstance(node, dict)
    steps = node["steps"]
    assert isinstance(steps, list)
    step = steps[0]
    assert isinstance(step, dict)
    return step


def _non_fragment_composed_bundle(tmp_path: Path):
    source = tmp_path / "composed-extern.orc"
    source.write_text(
        """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule composed_extern)
  (export review)
  (defworkflow review ((subject String)) -> Bool
    (provider-result providers.review
      :prompt prompts.review
      :inputs (subject)
      :returns Bool
      :delivery :composed)))
""",
        encoding="utf-8",
    )
    return compile_stage3_module(
        source,
        entry_workflow="review",
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={"prompts.review": "prompts/review.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    ).validated_bundles["review"]


def _fragment_omitted_bundle(tmp_path: Path, target: str):
    source = tmp_path / f"omitted-{target.replace('.', '-')}.orc"
    source.write_text(
        PHASED_FIXTURE.read_text(encoding="utf-8")
        .replace('(:target-dsl "2.23")', f'(:target-dsl "{target}")')
        .replace("\n      :delivery :phased", ""),
        encoding="utf-8",
    )
    return compile_stage3_module(
        source,
        entry_workflow="phased-review",
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    ).validated_bundles["phased-review"]


def test_phased_policy_round_trips_in_existing_persisted_graph_schema(
    tmp_path: Path,
) -> None:
    payload = _phased_payload(tmp_path)
    wire = _provider_wire(payload)

    assert payload["schema_version"] == "persisted_workflow_surface_graph.v3"
    assert wire["provider_call_policy"] == {
        "model": "unchanged-provider-model",
        "effort": "high",
        "delivery": "phased",
        "materialization_attempts": 2,
    }

    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    step = next(iter(decoded.nodes.values())).steps[0]
    assert step.provider_call_policy == wire["provider_call_policy"]
    assert step.prompt_attempt_identity_version == (
        PHASED_PROMPT_ATTEMPT_IDENTITY_VERSION
    )
    assert "phase_cursor" not in json.dumps(payload, sort_keys=True)


def test_non_fragment_explicit_composed_policy_compiles_and_persists(
    tmp_path: Path,
) -> None:
    bundle = _non_fragment_composed_bundle(tmp_path)
    step = bundle.surface.steps[0]
    assert step.provider_call_policy == {"delivery": "composed"}
    assert step.prompt_attempt_identity_version is None
    assert step.compiler_prompt_attempt_binding_plan is None

    payload = serialize_persisted_workflow_surface_graph(bundle)
    wire = _provider_wire(payload)
    assert wire["provider_call_policy"] == {"delivery": "composed"}
    assert "prompt_attempt_identity_version" not in wire
    assert "compiler_prompt_attempt_binding_plan" not in wire

    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    decoded_step = next(iter(decoded.nodes.values())).steps[0]
    assert decoded_step.provider_call_policy == {"delivery": "composed"}
    assert decoded_step.prompt_attempt_identity_version is None


@pytest.mark.parametrize(
    ("target", "expected_identity"),
    (
        ("2.20", None),
        ("2.21", None),
        ("2.22", PROMPT_ATTEMPT_IDENTITY_VERSION),
        ("2.23", PROMPT_ATTEMPT_IDENTITY_VERSION),
    ),
)
def test_omitted_delivery_compatibility_matrix_preserves_existing_carriage(
    tmp_path: Path,
    target: str,
    expected_identity: str | None,
) -> None:
    bundle = _fragment_omitted_bundle(tmp_path, target)
    surface_step = bundle.surface.steps[0]
    config = next(iter(bundle.ir.nodes.values())).execution_config
    assert isinstance(config, ProviderStepConfig)
    assert surface_step.provider_call_policy is None
    assert config.provider_call_policy is None
    assert surface_step.prompt_attempt_identity_version == expected_identity
    assert config.prompt_attempt_identity_version == expected_identity

    payload = serialize_persisted_workflow_surface_graph(bundle)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    decoded_step = next(iter(decoded.nodes.values())).steps[0]
    assert decoded_step.provider_call_policy is None
    assert decoded_step.prompt_attempt_identity_version == expected_identity

    identity = lexical_checkpoints.checkpoint_runtime_program_identity(
        state_manager=StateManager(
            tmp_path,
            run_id=f"omitted-{target.replace('.', '-')}",
        ),
        runtime_plan=bundle.runtime_plan,
        executable_ir=bundle.ir,
    )
    configurations = identity.get("provider_configurations", [])
    assert len(configurations) == (0 if expected_identity is None else 1)
    if configurations:
        assert configurations[0]["prompt_attempt_identity_version"] == (
            expected_identity
        )
        assert "provider_call_policy" not in configurations[0]


def test_persisted_phased_policy_rejects_target_downgrade_specifically(
    tmp_path: Path,
) -> None:
    payload = copy.deepcopy(_phased_payload(tmp_path))
    nodes = payload["nodes"]
    assert isinstance(nodes, dict)
    node = next(iter(nodes.values()))
    assert isinstance(node, dict)
    node["version"] = "2.22"

    with pytest.raises(
        ValueError,
        match="provider_phased_delivery_carriage_mismatch",
    ):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(payload)
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_policy",
        "missing_attempts",
        "attempts_without_delivery",
        "extra_policy_key",
        "phased_identity_v1",
        "composed_identity_v2",
        "reordered_binding_plan",
    ),
)
def test_persisted_phased_carriage_rejects_damaged_or_mixed_pairs(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload = copy.deepcopy(_phased_payload(tmp_path))
    wire = _provider_wire(payload)
    policy = wire["provider_call_policy"]
    assert isinstance(policy, dict)
    binding_plan = wire["compiler_prompt_attempt_binding_plan"]
    assert isinstance(binding_plan, dict)
    binding_rows = binding_plan["rows"]
    assert isinstance(binding_rows, list)

    if mutation == "missing_policy":
        wire.pop("provider_call_policy")
    elif mutation == "missing_attempts":
        policy.pop("materialization_attempts")
    elif mutation == "attempts_without_delivery":
        policy.pop("delivery")
    elif mutation == "extra_policy_key":
        policy["unexpected"] = True
    elif mutation == "phased_identity_v1":
        wire["prompt_attempt_identity_version"] = (
            PROMPT_ATTEMPT_IDENTITY_VERSION
        )
    elif mutation == "composed_identity_v2":
        wire["provider_call_policy"] = {"delivery": "composed"}
    elif mutation == "reordered_binding_plan":
        binding_rows.reverse()
    else:
        raise AssertionError(mutation)

    with pytest.raises(
        ValueError,
        match=(
            "provider_phased_delivery_carriage_mismatch"
            if mutation != "reordered_binding_plan"
            else "prompt_attempt_binding_plan_invalid"
        ),
    ):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(payload)
        )


def _checkpoint_inputs(tmp_path: Path, *, attempts: int):
    bundle = _phased_surface_bundle(tmp_path)
    surface = bundle.surface.steps[0]
    config = ProviderStepConfig(
        common=StepCommonConfig(
            expected_outputs=surface.common.expected_outputs,
        ),
        provider="test-provider",
        provider_call_policy={
            "delivery": "phased",
            "materialization_attempts": attempts,
        },
        compiler_prompt_dependency_contract=(
            surface.compiler_prompt_dependency_contract
        ),
        compiler_prompt_fragment_contract=(
            surface.compiler_prompt_fragment_contract
        ),
        compiled_prompt_fragment_identity=(
            surface.compiled_prompt_fragment_identity
        ),
        prompt_attempt_identity_version=(
            surface.prompt_attempt_identity_version
        ),
        compiler_prompt_attempt_binding_plan=(
            surface.compiler_prompt_attempt_binding_plan
        ),
        typed_prompt_inputs=surface.typed_prompt_inputs,
    )
    node = SimpleNamespace(
        node_id="node.phased",
        step_id="step.phased",
        execution_config=config,
    )
    executable_ir = SimpleNamespace(
        version="2.23",
        nodes={"node.phased": node},
    )
    runtime_plan = SimpleNamespace(
        workflow_name="phased-checkpoint",
        ordered_node_ids=("node.phased",),
        lexical_checkpoint_points=(),
        resume_checkpoints=(),
        nodes={"node.phased": node},
    )
    state_manager = StateManager(tmp_path, run_id=f"attempts-{attempts}")
    return state_manager, runtime_plan, executable_ir


def test_checkpoint_identity_carries_policy_and_changes_on_attempt_cap(
    tmp_path: Path,
) -> None:
    first_inputs = _checkpoint_inputs(tmp_path / "first", attempts=2)
    changed_inputs = _checkpoint_inputs(tmp_path / "changed", attempts=3)

    first = lexical_checkpoints.checkpoint_runtime_program_identity(
        state_manager=first_inputs[0],
        runtime_plan=first_inputs[1],
        executable_ir=first_inputs[2],
    )
    changed = lexical_checkpoints.checkpoint_runtime_program_identity(
        state_manager=changed_inputs[0],
        runtime_plan=changed_inputs[1],
        executable_ir=changed_inputs[2],
    )

    assert first["checkpoint_schema_version"] == (
        "workflow_lisp_lexical_checkpoint.v1"
    )
    assert first["provider_configurations"][0]["provider_call_policy"] == {
        "delivery": "phased",
        "materialization_attempts": 2,
    }
    assert first["provider_configurations"][0][
        "prompt_attempt_identity_version"
    ] == PHASED_PROMPT_ATTEMPT_IDENTITY_VERSION
    assert first["provider_configurations"] != changed[
        "provider_configurations"
    ]
    assert first["executable_ir_digest"] != changed["executable_ir_digest"]
    assert first["semantic_ir_digest"] != changed["semantic_ir_digest"]
    assert "phase_cursor" not in json.dumps(first, sort_keys=True)

    record = {
        "schema_version": "workflow_lisp_lexical_checkpoint.v1",
        "validity_envelope": {
            "binding_schema_digest": "sha256:binding",
            "storage_allocation_id": "allocation",
            "source_map_origin_key": "origin",
        },
        "program_identity": first,
    }
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_program_identity_mismatch",
    ):
        lexical_checkpoints.validate_checkpoint_record(
            record,
            expected_program_identity=changed,
        )


def test_checkpoint_identity_carries_every_provider_in_node_id_order(
    tmp_path: Path,
) -> None:
    state_manager, runtime_plan, executable_ir = _checkpoint_inputs(
        tmp_path,
        attempts=2,
    )
    config = executable_ir.nodes["node.phased"].execution_config
    later = SimpleNamespace(
        node_id="node.z",
        step_id="step.z",
        execution_config=config,
    )
    earlier = SimpleNamespace(
        node_id="node.a",
        step_id="step.a",
        execution_config=config,
    )
    executable_ir.nodes = {
        later.node_id: later,
        earlier.node_id: earlier,
    }
    runtime_plan.nodes = executable_ir.nodes
    runtime_plan.ordered_node_ids = (later.node_id, earlier.node_id)

    identity = lexical_checkpoints.checkpoint_runtime_program_identity(
        state_manager=state_manager,
        runtime_plan=runtime_plan,
        executable_ir=executable_ir,
    )

    configurations = identity["provider_configurations"]
    assert len(configurations) == 2
    assert [row["node_id"] for row in configurations] == [
        "node.a",
        "node.z",
    ]
    assert [row["step_id"] for row in configurations] == [
        "step.a",
        "step.z",
    ]


def test_checkpoint_identity_carries_non_fragment_explicit_composed_policy(
    tmp_path: Path,
) -> None:
    bundle = _non_fragment_composed_bundle(tmp_path)
    state_manager = StateManager(tmp_path, run_id="composed-checkpoint")

    identity = lexical_checkpoints.checkpoint_runtime_program_identity(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        executable_ir=bundle.ir,
    )

    configurations = identity["provider_configurations"]
    assert len(configurations) == 1
    assert configurations[0]["provider_call_policy"] == {
        "delivery": "composed",
    }
    assert "prompt_attempt_identity_version" not in configurations[0]
    assert "compiler_prompt_attempt_binding_plan" not in configurations[0]


def test_checkpoint_rejects_mixed_phased_policy_and_identity(
    tmp_path: Path,
) -> None:
    state_manager, runtime_plan, executable_ir = _checkpoint_inputs(
        tmp_path,
        attempts=2,
    )
    config = executable_ir.nodes["node.phased"].execution_config
    object.__setattr__(
        config,
        "prompt_attempt_identity_version",
        PROMPT_ATTEMPT_IDENTITY_VERSION,
    )

    with pytest.raises(
        ValueError,
        match="provider_phased_delivery_carriage_mismatch",
    ):
        lexical_checkpoints.checkpoint_runtime_program_identity(
            state_manager=state_manager,
            runtime_plan=runtime_plan,
            executable_ir=executable_ir,
        )
