"""Executable-IR compatibility projection tables for persisted/reporting surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from .executable_ir import WorkflowRegion
from .surface_ast import empty_frozen_mapping


@dataclass(frozen=True)
class CompatibilityNodeProjection:
    """Compatibility metadata for one executable node."""

    node_id: str
    step_id: str
    presentation_key: str
    display_name: str
    region: WorkflowRegion
    compatibility_index: Optional[int] = None
    finalization_index: Optional[int] = None


@dataclass(frozen=True)
class IterationStepKeyProjection:
    """Compatibility key formatter for repeat-until or for-each iteration steps."""

    node_id: str
    frame_key: str
    nested_presentation_keys: Mapping[str, str] = field(default_factory=empty_frozen_mapping)

    def step_key(self, iteration_index: int, nested_node_id: str) -> str:
        """Return the persisted/reporting step key for one loop iteration node."""
        nested_key = self.nested_presentation_keys.get(nested_node_id)
        if nested_key is None:
            raise KeyError(f"Unknown nested node id '{nested_node_id}' for '{self.node_id}'")
        return f"{self.frame_key}[{iteration_index}].{nested_key}"


@dataclass(frozen=True)
class CallBoundaryProjection:
    """Compatibility metadata for call-boundary checkpoint surfaces."""

    node_id: str
    presentation_key: str
    step_id: str


@dataclass(frozen=True)
class WorkflowStateProjection:
    """Projection between executable node ids and persisted/reporting compatibility surfaces."""

    entries_by_node_id: Mapping[str, CompatibilityNodeProjection]
    node_id_by_compatibility_index: Mapping[int, str] = field(default_factory=empty_frozen_mapping)
    compatibility_index_by_node_id: Mapping[str, int] = field(default_factory=empty_frozen_mapping)
    presentation_key_by_node_id: Mapping[str, str] = field(default_factory=empty_frozen_mapping)
    node_id_by_step_id: Mapping[str, str] = field(default_factory=empty_frozen_mapping)
    finalization_node_id_by_index: Mapping[int, str] = field(default_factory=empty_frozen_mapping)
    finalization_index_by_node_id: Mapping[str, int] = field(default_factory=empty_frozen_mapping)
    repeat_until_nodes: Mapping[str, IterationStepKeyProjection] = field(default_factory=empty_frozen_mapping)
    for_each_nodes: Mapping[str, IterationStepKeyProjection] = field(default_factory=empty_frozen_mapping)
    call_boundaries: Mapping[str, CallBoundaryProjection] = field(default_factory=empty_frozen_mapping)

    def repeat_until_step_key(self, loop_node_id: str, iteration_index: int, nested_node_id: str) -> str:
        """Format the persisted/reporting key for one repeat-until iteration node."""
        projection = self.repeat_until_nodes.get(loop_node_id)
        if projection is None:
            raise KeyError(f"Unknown repeat_until node id '{loop_node_id}'")
        return projection.step_key(iteration_index, nested_node_id)

    def for_each_step_key(self, for_each_node_id: str, iteration_index: int, nested_node_id: str) -> str:
        """Format the persisted/reporting key for one for-each iteration node."""
        projection = self.for_each_nodes.get(for_each_node_id)
        if projection is None:
            raise KeyError(f"Unknown for_each node id '{for_each_node_id}'")
        return projection.step_key(iteration_index, nested_node_id)
