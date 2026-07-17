from __future__ import annotations

import copy
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pytest

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.persisted_surface import (
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA,
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.surface_ast import (
    SurfaceFinallyBlock,
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
)


def _bundle(
    name: str,
    *,
    steps: tuple[SurfaceStep, ...] = (),
    imports: Mapping[str, LoadedWorkflowBundle] | None = None,
    finalization: SurfaceFinallyBlock | None = None,
) -> LoadedWorkflowBundle:
    provenance = WorkflowProvenance(
        workflow_path=Path("workflows") / f"{name}.orc",
        source_root=Path("workflows"),
    )
    surface = SurfaceWorkflow(
        version="1",
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
        imports={} if imports is None else imports,
        provenance=provenance,
    )


def _call(name: str, alias: str) -> SurfaceStep:
    return SurfaceStep(
        name=name,
        step_id=name.lower(),
        kind=SurfaceStepKind.CALL,
        call_alias=alias,
    )


def _canonical_payload(bundle: LoadedWorkflowBundle) -> tuple[dict[str, Any], bytes]:
    raw = serialize_persisted_workflow_surface_graph(bundle)
    return raw, canonical_persisted_surface_bytes(raw)


def test_serializer_follows_root_nested_and_finalization_calls_but_not_unused_imports() -> None:
    direct = _bundle("direct")
    nested = _bundle("nested")
    finalized = _bundle("finalized")
    unused = _bundle("unused")
    root = _bundle(
        "root",
        steps=(
            _call("Direct", "direct"),
            SurfaceStep(
                name="Loop",
                step_id="loop",
                kind=SurfaceStepKind.FOR_EACH,
                for_each_steps=(_call("Nested", "nested"),),
            ),
        ),
        finalization=SurfaceFinallyBlock(
            token="finally",
            step_id="finally",
            steps=(_call("Finalized", "finalized"),),
        ),
        imports={
            "direct": direct,
            "nested": nested,
            "finalized": finalized,
            "unused": unused,
        },
    )

    raw, payload = _canonical_payload(root)
    graph = decode_persisted_workflow_surface_graph(payload)

    assert set(raw["nodes"]) == {"root", "direct", "nested", "finalized"}
    assert raw["nodes"]["root"]["calls"] == {
        "direct": "direct",
        "finalized": "finalized",
        "nested": "nested",
    }
    assert graph.entry_node.steps[0].call_alias == "direct"
    assert graph.entry_node.steps[1].for_each_steps[0].call_alias == "nested"
    assert graph.entry_node.finalization_steps[0].call_alias == "finalized"


def test_serializer_deduplicates_two_aliases_and_a_diamond_to_one_node() -> None:
    shared = _bundle("shared")
    left = _bundle(
        "left",
        steps=(_call("LeftShared", "shared"),),
        imports={"shared": shared},
    )
    right = _bundle(
        "right",
        steps=(_call("RightShared", "shared"),),
        imports={"shared": shared},
    )
    root = _bundle(
        "root",
        steps=(
            _call("FirstAlias", "first"),
            _call("SecondAlias", "second"),
            _call("Left", "left"),
            _call("Right", "right"),
        ),
        imports={"first": shared, "second": shared, "left": left, "right": right},
    )

    raw, payload = _canonical_payload(root)
    graph = decode_persisted_workflow_surface_graph(payload)

    assert set(raw["nodes"]) == {"root", "left", "right", "shared"}
    assert raw["nodes"]["root"]["calls"]["first"] == "shared"
    assert raw["nodes"]["root"]["calls"]["second"] == "shared"
    assert graph.imported_node(graph.entry_node, "first") is graph.imported_node(
        graph.entry_node, "second"
    )


def test_serializer_rejects_a_used_alias_missing_from_imports() -> None:
    root = _bundle("root", steps=(_call("Missing", "missing"),))

    with pytest.raises(ValueError, match="has no imported bundle"):
        serialize_persisted_workflow_surface_graph(root)


def test_serializer_rejects_import_cycles() -> None:
    imports: dict[str, LoadedWorkflowBundle] = {}
    root = _bundle("root", steps=(_call("Again", "again"),), imports=imports)
    imports["again"] = root

    with pytest.raises(ValueError, match="import cycle"):
        serialize_persisted_workflow_surface_graph(root)


def test_serializer_rejects_same_name_with_different_payloads() -> None:
    first = _bundle("shared")
    second = _bundle(
        "shared",
        steps=(
            SurfaceStep(
                name="Different",
                step_id="different",
                kind=SurfaceStepKind.COMMAND,
            ),
        ),
    )
    root = _bundle(
        "root",
        steps=(_call("First", "first"), _call("Second", "second")),
        imports={"first": first, "second": second},
    )

    with pytest.raises(ValueError, match="workflow-name conflict"):
        serialize_persisted_workflow_surface_graph(root)


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        ("extra_alias", "call-edge table"),
        ("missing_alias", "call-edge table"),
        ("missing_target", "target is missing"),
        ("unreachable_node", "unreachable"),
        ("cycle", "import cycle"),
    ],
)
def test_decoder_rejects_inconsistent_or_unreachable_topology(
    damage: str,
    message: str,
) -> None:
    child = _bundle("child")
    raw, _payload = _canonical_payload(
        _bundle("root", steps=(_call("Child", "child"),), imports={"child": child})
    )
    damaged = copy.deepcopy(raw)
    root_node = damaged["nodes"]["root"]
    child_node = damaged["nodes"]["child"]

    if damage == "extra_alias":
        root_node["calls"]["extra"] = "child"
    elif damage == "missing_alias":
        root_node["calls"].pop("child")
    elif damage == "missing_target":
        root_node["calls"]["child"] = "missing"
    elif damage == "unreachable_node":
        orphan = copy.deepcopy(child_node)
        orphan["workflow_name"] = "orphan"
        damaged["nodes"]["orphan"] = orphan
    else:
        child_node["steps"] = [copy.deepcopy(root_node["steps"][0])]
        child_node["steps"][0]["call_alias"] = "root"
        child_node["calls"] = {"root": "root"}

    with pytest.raises(ValueError, match=message):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(damaged)
        )


def test_decoder_accepts_only_canonical_json_without_duplicate_keys() -> None:
    raw, canonical = _canonical_payload(_bundle("root"))

    assert decode_persisted_workflow_surface_graph(canonical).entry_workflow == "root"
    with pytest.raises(ValueError, match="not canonical"):
        decode_persisted_workflow_surface_graph(
            (json.dumps(raw, indent=2, sort_keys=True) + "\n").encode("utf-8")
        )

    duplicate_key = canonical[:-2] + (
        b',"schema_version":"' + PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA.encode() + b'"}\n'
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_persisted_workflow_surface_graph(duplicate_key)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda raw: raw.update(schema_version="unsupported.v2"),
            id="unsupported-schema",
        ),
        pytest.param(lambda raw: raw.update(extra=True), id="unknown-root-field"),
        pytest.param(lambda raw: raw.pop("entry_workflow"), id="missing-root-field"),
        pytest.param(
            lambda raw: raw["nodes"]["root"].update(extra=True),
            id="unknown-node-field",
        ),
        pytest.param(
            lambda raw: raw["nodes"]["root"].pop("version"),
            id="missing-node-field",
        ),
        pytest.param(
            lambda raw: raw["nodes"]["root"]["steps"][0].update(extra=True),
            id="unknown-step-field",
        ),
        pytest.param(
            lambda raw: raw["nodes"]["root"]["steps"][0].pop("step_id"),
            id="missing-step-field",
        ),
        pytest.param(
            lambda raw: raw["nodes"]["root"]["steps"][0].update(
                kind="not_a_surface_step_kind"
            ),
            id="invalid-step-kind",
        ),
    ],
)
def test_decoder_rejects_unknown_missing_or_unsupported_wire_values(mutate) -> None:
    raw, _payload = _canonical_payload(
        _bundle(
            "root",
            steps=(
                SurfaceStep(
                    name="Command",
                    step_id="command",
                    kind=SurfaceStepKind.COMMAND,
                ),
            ),
        )
    )
    mutate(raw)

    with pytest.raises(ValueError):
        decode_persisted_workflow_surface_graph(canonical_persisted_surface_bytes(raw))


def test_decoder_returns_a_deeply_immutable_graph() -> None:
    step = SurfaceStep(
        name="Provider",
        step_id="provider",
        kind=SurfaceStepKind.PROVIDER,
        input_file={"path": ["prompt.md"]},
        depends_on={"nested": ["dependency"]},
        common=SurfaceStepCommonConfig(
            publishes=({"nested": ["publish"]},),
            expected_outputs=({"nested": ["output"]},),
        ),
    )
    _raw, payload = _canonical_payload(_bundle("root", steps=(step,)))

    graph = decode_persisted_workflow_surface_graph(payload)
    decoded = graph.entry_node.steps[0]

    assert isinstance(graph.nodes, MappingProxyType)
    assert isinstance(graph.entry_node.calls, MappingProxyType)
    assert decoded.input_file["path"] == ("prompt.md",)
    assert decoded.depends_on["nested"] == ("dependency",)
    assert decoded.common.publishes[0]["nested"] == ("publish",)
    assert decoded.common.expected_outputs[0]["nested"] == ("output",)
    with pytest.raises(TypeError):
        graph.nodes["other"] = graph.entry_node  # type: ignore[index]
    with pytest.raises(TypeError):
        decoded.input_file["path"] = ()
