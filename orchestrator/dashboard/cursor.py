"""Execution cursor projection for dashboard display."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class CursorNode:
    """One display-only cursor node."""

    kind: str
    name: str
    step_id: Optional[str] = None
    status: Optional[str] = None
    frame_id: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionCursor:
    """Display-only active execution cursor."""

    summary: str
    nodes: list[CursorNode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExecutionCursorProjector:
    """Project active top-level and nested execution state without routing decisions."""

    def __init__(self, max_depth: int = 8) -> None:
        self.max_depth = max_depth

    def project(self, state: Mapping[str, Any]) -> ExecutionCursor:
        nodes: list[CursorNode] = []
        warnings: list[str] = []
        current_step = state.get("current_step")
        if isinstance(current_step, Mapping):
            self._add_current_step(
                current_step,
                state,
                nodes,
                warnings,
                seen_step_ids=set(),
                depth=0,
                root_state=state,
            )

        self._add_loop_state(state, nodes)
        finalization = state.get("finalization")
        if isinstance(finalization, Mapping) and finalization:
            nodes.append(
                CursorNode(
                    kind="finalization",
                    name="finalization",
                    status=self._str_or_none(finalization.get("status")),
                    details=dict(finalization),
                )
            )

        summary = " -> ".join(node.name for node in nodes if node.kind == "current_step")
        return ExecutionCursor(summary=summary, nodes=nodes, warnings=warnings)

    def _add_current_step(
        self,
        current_step: Mapping[str, Any],
        state: Mapping[str, Any],
        nodes: list[CursorNode],
        warnings: list[str],
        *,
        seen_step_ids: set[str],
        depth: int,
        root_state: Mapping[str, Any],
    ) -> None:
        if depth > self.max_depth:
            warnings.append("maximum call-frame cursor depth reached")
            return
        name = self._str_or_none(current_step.get("name")) or self._str_or_none(
            current_step.get("step_id")
        ) or "current_step"
        step_id = self._str_or_none(current_step.get("step_id"))
        nodes.append(
            CursorNode(
                kind="current_step",
                name=name,
                step_id=step_id,
                status=self._str_or_none(current_step.get("status")),
                details=dict(current_step),
            )
        )
        if step_id is None:
            return
        if step_id in seen_step_ids:
            warnings.append(f"cycle detected at step id {step_id}")
            return
        seen_step_ids.add(step_id)

        for frame_id, frame in self._matching_call_frames(state, step_id, root_state):
            frame_state = self._frame_state(frame)
            nested_current = self._nested_current_step(frame)
            frame_details = {
                "workflow_file": frame.get("workflow_file"),
                "import_alias": frame.get("import_alias"),
                "bound_inputs": frame.get("bound_inputs", {}),
                "body_status": frame.get("body_status"),
                "finalization_status": frame.get("finalization_status"),
                "export_status": frame.get("export_status"),
            }
            nodes.append(
                CursorNode(
                    kind="call_frame",
                    name=str(frame_id),
                    frame_id=str(frame_id),
                    status=self._str_or_none(frame.get("status")),
                    details=frame_details,
                )
            )
            if nested_current is not None:
                self._add_current_step(
                    nested_current,
                    frame_state,
                    nodes,
                    warnings,
                    seen_step_ids=seen_step_ids,
                    depth=depth + 1,
                    root_state=root_state,
                )

    def _matching_call_frames(
        self,
        state: Mapping[str, Any],
        step_id: str,
        root_state: Mapping[str, Any],
    ) -> list[tuple[str, Mapping[str, Any]]]:
        matches: list[tuple[str, Mapping[str, Any]]] = []
        seen_frame_ids: set[str] = set()
        for candidate_state in (state, root_state):
            call_frames = candidate_state.get("call_frames")
            if not isinstance(call_frames, Mapping):
                continue
            for frame_id, frame in call_frames.items():
                frame_id_text = str(frame_id)
                if frame_id_text in seen_frame_ids or not isinstance(frame, Mapping):
                    continue
                caller_step_id = frame.get("call_step_id") or frame.get("caller_step_id")
                if caller_step_id == step_id and frame.get("status") == "running":
                    seen_frame_ids.add(frame_id_text)
                    matches.append((frame_id_text, frame))
        return matches

    def _frame_state(self, frame: Mapping[str, Any]) -> Mapping[str, Any]:
        nested_state = frame.get("state")
        return nested_state if isinstance(nested_state, Mapping) else frame

    def _nested_current_step(self, frame: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        current_step = frame.get("current_step")
        if isinstance(current_step, Mapping):
            return current_step
        nested_state = frame.get("state")
        if isinstance(nested_state, Mapping) and isinstance(nested_state.get("current_step"), Mapping):
            return nested_state["current_step"]
        return None

    def _add_loop_state(self, state: Mapping[str, Any], nodes: list[CursorNode]) -> None:
        repeat_until = state.get("repeat_until")
        if isinstance(repeat_until, Mapping):
            for name, payload in repeat_until.items():
                if not isinstance(payload, Mapping):
                    continue
                nodes.append(
                    CursorNode(
                        kind="repeat_until",
                        name=str(name),
                        details=dict(payload),
                    )
                )
        for_each = state.get("for_each")
        if isinstance(for_each, Mapping):
            for name, payload in for_each.items():
                if not isinstance(payload, Mapping):
                    continue
                details = dict(payload)
                items = payload.get("items")
                if isinstance(items, list):
                    details["item_count"] = len(items)
                nodes.append(
                    CursorNode(
                        kind="for_each",
                        name=str(name),
                        details=details,
                    )
                )

    def _str_or_none(self, value: Any) -> Optional[str]:
        return value if isinstance(value, str) and value else None
