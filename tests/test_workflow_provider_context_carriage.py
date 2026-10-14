"""Direct carriage checks for the future ordinary-provider context map."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

import pytest

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.persisted_surface import (
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA,
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5,
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.provider_context import validate_provider_context_config
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor
from orchestrator.workflow.surface_ast import (
    SurfaceFinallyBlock,
    SurfaceStep,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
)
from tests.test_workflow_lisp_prompt_identity_persistence import (
    _q3_bundle,
)


CONTEXT = {
    "input": {"ref": "inputs.history"},
    "capture": "portable",
    "result_descriptor": {
        "kind": "record",
        "name": "Answer",
        "fields": [
            {
                "name": "answer",
                "type": {"kind": "primitive", "name": "String"},
            }
        ],
    },
}


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@pytest.mark.parametrize("mutation", [
    None, "missing", "variant", "extra_field", "wrong_name", "pointer",
    "optional", "projection", "wrong_type",
])
def test_capture_model_contract_is_exactly_the_declared_root(mutation) -> None:
    from orchestrator.workflow.provider_context import validate_capture_output_contract

    config = {"capture": "portable", "result_descriptor": CONTEXT["result_descriptor"]}
    field = {
        "name": "__result__", "json_pointer": "",
        **transport_schema_for_descriptor(config["result_descriptor"], allow_nested_structures=True),
        "guidance": {"description": "Model answer"},
    }
    bundle = {"path": "answer.json", "fields": [field]}
    variant = None
    if mutation == "missing":
        bundle = None
    elif mutation == "variant":
        variant = {"path": "answer.json"}
    elif mutation == "extra_field":
        bundle["fields"].append({"name": "other", "type": "string", "json_pointer": "/other"})
    elif mutation == "wrong_name":
        field["name"] = "answer"
    elif mutation == "pointer":
        field["json_pointer"] = "/answer"
    elif mutation == "optional":
        field["required"] = False
    elif mutation == "projection":
        field["projection"] = {"projection_class": "union_workflow_boundary"}
    elif mutation == "wrong_type":
        field["fields"][0]["type"] = "integer"

    if mutation is None:
        validate_capture_output_contract(config, bundle, variant)
    else:
        with pytest.raises(ValueError, match="capture.*contract"):
            validate_capture_output_contract(config, bundle, variant)


def _persisted_only_bundle(
    name: str,
    *,
    version: str = "2.31",
    steps: tuple[SurfaceStep, ...] = (),
    imports: dict[str, LoadedWorkflowBundle] | None = None,
    finalization: SurfaceFinallyBlock | None = None,
) -> LoadedWorkflowBundle:
    provenance = WorkflowProvenance(
        workflow_path=Path("workflows") / f"{name}.yaml",
        source_root=Path("workflows"),
    )
    surface = SurfaceWorkflow(
        version=version,
        name=name,
        steps=steps,
        provenance=provenance,
        finalization=finalization,
    )
    return LoadedWorkflowBundle(
        surface=surface,
        core_workflow_ast=None,  # type: ignore[arg-type]
        semantic_ir=None,  # type: ignore[arg-type]
        ir=None,  # type: ignore[arg-type]
        projection=None,  # type: ignore[arg-type]
        runtime_plan=None,  # type: ignore[arg-type]
        imports=MappingProxyType({} if imports is None else imports),
        provenance=provenance,
    )


def _provider(name: str = "Ask") -> SurfaceStep:
    return SurfaceStep(
        name=name,
        step_id=name.lower(),
        kind=SurfaceStepKind.PROVIDER,
        provider="test-provider",
        provider_context=CONTEXT,
    )


def test_provider_context_is_not_a_common_or_non_provider_carrier() -> None:
    with pytest.raises(ValueError, match="provider_context requires an ordinary provider step"):
        SurfaceStep(
            name="Command",
            step_id="command",
            kind=SurfaceStepKind.COMMAND,
            provider_context=CONTEXT,
        )


@pytest.mark.parametrize(
    "expected_context",
    (
        {"input": {"ref": "inputs.history"}},
        {"capture": "portable", "result_descriptor": CONTEXT["result_descriptor"]},
        CONTEXT,
    ),
)
def test_provider_context_closed_config_accepts_the_three_approved_shapes(expected_context) -> None:
    assert validate_provider_context_config(
        expected_context,
        step_kind="provider",
        target_dsl_version="2.31",
    ) == expected_context


@pytest.mark.parametrize("placement", ("nested", "finalization"))
def test_provider_context_selects_v5_in_nested_and_finalization_steps(placement) -> None:
    provider = _provider()
    if placement == "nested":
        bundle = _persisted_only_bundle(
            "nested-context",
            steps=(
                SurfaceStep(
                    name="Loop",
                    step_id="loop",
                    kind=SurfaceStepKind.FOR_EACH,
                    for_each_steps=(provider,),
                ),
            ),
        )
    else:
        bundle = _persisted_only_bundle(
            "final-context",
            finalization=SurfaceFinallyBlock(
                token="finally",
                step_id="finally",
                steps=(provider,),
            ),
        )

    wire = serialize_persisted_workflow_surface_graph(bundle)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )
    assert wire["schema_version"] == (
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5
    )
    if placement == "nested":
        assert decoded.entry_node.steps[0].for_each_steps[0].provider_context is not None
    else:
        assert decoded.entry_node.finalization_steps[0].provider_context is not None


def test_provider_context_selects_v5_only_for_reachable_imports() -> None:
    child = _persisted_only_bundle("child", steps=(_provider(),))
    root = _persisted_only_bundle(
        "root",
        steps=(
            SurfaceStep(
                name="Call",
                step_id="call",
                kind=SurfaceStepKind.CALL,
                call_alias="child",
            ),
        ),
        imports={"child": child},
    )
    unused = _persisted_only_bundle("unused", steps=(_provider(),))
    root_with_unused = _persisted_only_bundle("root", imports={"unused": unused})

    wire = serialize_persisted_workflow_surface_graph(root)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )
    assert wire["schema_version"] == (
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5
    )
    assert decoded.nodes["child"].steps[0].provider_context is not None
    assert serialize_persisted_workflow_surface_graph(root_with_unused)["schema_version"] == (
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA
    )


def test_provider_context_v5_preserves_q3_legacy_fragment_carriage(tmp_path: Path) -> None:
    bundle = _q3_bundle(tmp_path)
    provider = next(
        step for step in bundle.surface.steps if step.kind is SurfaceStepKind.PROVIDER
    )
    surface = replace(
        bundle.surface,
        version="2.31",
        steps=(replace(provider, provider_context=CONTEXT),),
    )
    wire = serialize_persisted_workflow_surface_graph(
        replace(bundle, surface=surface)
    )
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )

    assert wire["schema_version"] == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5
    assert decoded.entry_node.steps[0].compiler_prompt_fragment_contract is not None


@pytest.mark.parametrize(
    ("context", "version", "policy"),
    (
        ({}, "2.31", None),
        (CONTEXT, "2.30", None),
        (CONTEXT, "2.31", {"delivery": "phased", "materialization_attempts": 1}),
    ),
)
def test_provider_context_persistence_rejects_invalid_admission(context, version, policy) -> None:
    with pytest.raises(ValueError):
        serialize_persisted_workflow_surface_graph(
            _persisted_only_bundle(
                "invalid-context", version=version,
                steps=(SurfaceStep(
                    name="Ask", step_id="ask", kind=SurfaceStepKind.PROVIDER,
                    provider="test-provider", provider_context=context,
                    provider_call_policy=policy,
                ),),
            )
        )


@pytest.mark.parametrize(
    "context",
    (
        {},
        {"input": None},
        {"input": {"ref": 1}},
        {"capture": "portable"},
        {"result_descriptor": CONTEXT["result_descriptor"]},
        {"capture": "portable", "result_descriptor": None},
        {"input": {"ref": "inputs.history"}, "unknown": True},
    ),
)
def test_provider_context_closed_config_rejects_malformed_shapes(context) -> None:
    with pytest.raises(ValueError):
        validate_provider_context_config(
            context,
            step_kind="provider",
            target_dsl_version="2.31",
        )
