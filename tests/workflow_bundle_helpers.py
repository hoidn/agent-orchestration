"""Test-only helpers for inspecting projection-backed bundle compatibility surfaces."""

from __future__ import annotations

from typing import Any

from orchestrator.workflow.executable_ir import ForEachNode, RepeatUntilFrameNode
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle


def _thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): _thaw(item) for key, item in value.items()}
    return value


def _materialize_loop_steps(
    bundle: LoadedWorkflowBundle,
    loop_node_id: str,
    node_ids: tuple[str, ...],
    *,
    loop_kind: str,
) -> list[dict[str, Any]]:
    if loop_kind == "for_each":
        projection = bundle.projection.for_each_nodes.get(loop_node_id)
    else:
        projection = bundle.projection.repeat_until_nodes.get(loop_node_id)

    materialized: list[dict[str, Any]] = []
    for node_id in node_ids:
        child_node = bundle.ir.nodes[node_id]
        child_step = _thaw(child_node.raw)
        child_step["step_id"] = child_node.step_id
        if projection is not None and node_id in projection.nested_presentation_keys:
            child_step["name"] = projection.nested_presentation_keys[node_id]
        elif not isinstance(child_step.get("name"), str) or not child_step["name"]:
            child_step["name"] = child_node.presentation_name
        materialized.append(child_step)
    return materialized


def materialize_projection_step(
    bundle: LoadedWorkflowBundle,
    node_id: str,
) -> dict[str, Any]:
    node = bundle.ir.nodes[node_id]
    step = _thaw(node.raw)
    step["step_id"] = node.step_id
    step["name"] = bundle.projection.presentation_key_by_node_id.get(node_id, node.presentation_name)

    if isinstance(node, ForEachNode):
        for_each = step.get("for_each")
        if isinstance(for_each, dict):
            for_each["steps"] = _materialize_loop_steps(
                bundle,
                node.node_id,
                node.body_node_ids,
                loop_kind="for_each",
            )
    elif isinstance(node, RepeatUntilFrameNode):
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            repeat_until["steps"] = _materialize_loop_steps(
                bundle,
                node.node_id,
                node.body_node_ids,
                loop_kind="repeat_until",
            )

    return step


def materialize_projection_body_steps(bundle: LoadedWorkflowBundle) -> list[dict[str, Any]]:
    return [materialize_projection_step(bundle, node_id) for node_id in bundle.ir.body_region]


def materialize_projection_finalization_steps(bundle: LoadedWorkflowBundle) -> list[dict[str, Any]]:
    return [materialize_projection_step(bundle, node_id) for node_id in bundle.ir.finalization_region]
