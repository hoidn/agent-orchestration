"""Target-2.23 phased-delivery persistence and checkpoint carriage."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

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











def test_non_fragment_explicit_composed_policy_persists(
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



def _non_fragment_composed_bundle(tmp_path):
    from tests.test_workflow_lisp_build_artifacts import _historical_surface_template, _synthetic_surface_bundle
    from orchestrator.workflow.surface_ast import SurfaceStep
    step = SurfaceStep("Review", "review", SurfaceStepKind.PROVIDER,
        provider="test-provider", provider_call_policy={"delivery": "composed"})
    return _synthetic_surface_bundle(_historical_surface_template(target="2.23"),
        "historical::composed", steps=(step,))
