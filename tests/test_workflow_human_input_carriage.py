"""Direct shared-carriage checks for the future request-input leaf."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping

import pytest

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.surface_ast import (
    SurfaceStep,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
)


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def test_request_input_is_not_a_common_or_non_request_carrier() -> None:
    with pytest.raises(ValueError, match="request_input requires a request input step"):
        SurfaceStep(
            name="Command",
            step_id="command",
            kind=SurfaceStepKind.COMMAND,
            request_input={"question": {"literal": "Continue?"}},
        )


def test_request_input_selects_closed_v6_persisted_carriage() -> None:
    provenance = WorkflowProvenance(
        workflow_path=Path("workflows/human-input-persisted.orc"),
        source_root=Path("workflows"),
    )
    surface = SurfaceWorkflow(
        version="2.32",
        name="human-input-persisted",
        steps=(
            SurfaceStep(
                name="Ask",
                step_id="ask",
                kind=SurfaceStepKind.REQUEST_INPUT,
                request_input={"question": {"literal": "Continue?"}},
            ),
        ),
        provenance=provenance,
    )
    bundle = LoadedWorkflowBundle(
        surface=surface,
        core_workflow_ast=None,  # type: ignore[arg-type]
        semantic_ir=None,  # type: ignore[arg-type]
        ir=None,  # type: ignore[arg-type]
        projection=None,  # type: ignore[arg-type]
        runtime_plan=None,  # type: ignore[arg-type]
        imports={},
        provenance=provenance,
    )

    wire = serialize_persisted_workflow_surface_graph(bundle)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )

    assert wire["schema_version"] == "persisted_workflow_surface_graph.v6"
    assert wire["nodes"]["human-input-persisted"]["steps"][0]["request_input"] == {
        "question": {"literal": "Continue?"},
    }
    assert _plain(decoded.entry_node.steps[0].request_input) == {
        "question": {"literal": "Continue?"},
    }


def test_request_input_v6_retains_existing_provider_context_carriage() -> None:
    provenance = WorkflowProvenance(
        workflow_path=Path("workflows/human-input-mixed.orc"), source_root=Path("workflows"),
    )
    surface = SurfaceWorkflow(
        version="2.32",
        name="human-input-mixed",
        steps=(
            SurfaceStep(
                name="Ask", step_id="ask", kind=SurfaceStepKind.REQUEST_INPUT,
                request_input={"question": {"literal": "Continue?"}},
            ),
            SurfaceStep(
                name="Context", step_id="context", kind=SurfaceStepKind.PROVIDER,
                provider="configured-codex",
                provider_context={"input": {"ref": "inputs.history"}},
            ),
        ),
        provenance=provenance,
    )
    bundle = LoadedWorkflowBundle(
        surface=surface, core_workflow_ast=None, semantic_ir=None, ir=None,
        projection=None, runtime_plan=None, imports={}, provenance=provenance,
    )  # type: ignore[arg-type]

    wire = serialize_persisted_workflow_surface_graph(bundle)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )

    assert wire["schema_version"] == "persisted_workflow_surface_graph.v6"
    assert _plain(decoded.entry_node.steps[1].provider_context) == {
        "input": {"ref": "inputs.history"},
    }


@pytest.mark.parametrize("mutation", ("missing_map", "wrong_kind", "wrong_schema", "null_map", "output_bundle", "variant_output"))
def test_request_input_v6_decoder_requires_the_exact_kind_map_and_schema(mutation) -> None:
    provenance = WorkflowProvenance(
        workflow_path=Path("workflows/human-input-forged.orc"), source_root=Path("workflows"),
    )
    surface = SurfaceWorkflow(
        version="2.32",
        name="human-input-forged",
        steps=(SurfaceStep(
            name="Ask", step_id="ask", kind=SurfaceStepKind.REQUEST_INPUT,
            request_input={"question": {"literal": "Continue?"}},
        ),),
        provenance=provenance,
    )
    bundle = LoadedWorkflowBundle(
        surface=surface, core_workflow_ast=None, semantic_ir=None, ir=None,
        projection=None, runtime_plan=None, imports={}, provenance=provenance,
    )  # type: ignore[arg-type]
    wire = serialize_persisted_workflow_surface_graph(bundle)
    step = wire["nodes"]["human-input-forged"]["steps"][0]
    if mutation == "missing_map":
        step.pop("request_input")
    elif mutation == "wrong_kind":
        step["kind"] = "command"
    elif mutation == "null_map":
        step["request_input"] = None
    elif mutation in {"output_bundle", "variant_output"}:
        step["common"][mutation] = {}
    else:
        wire["schema_version"] = "persisted_workflow_surface_graph.v5"

    with pytest.raises(ValueError, match="request_input_persistence_mismatch"):
        decode_persisted_workflow_surface_graph(canonical_persisted_surface_bytes(wire))
