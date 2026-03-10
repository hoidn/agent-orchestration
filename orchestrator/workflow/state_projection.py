"""Executable-IR compatibility projection tables for persisted/reporting surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from .executable_ir import WorkflowRegion
from .surface_ast import empty_frozen_mapping


def _runtime_step_id(loop_node_id: str, iteration_index: int, nested_suffix: str) -> str:
    return f"{loop_node_id}#{iteration_index}.{nested_suffix}"


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
    nested_step_id_suffixes: Mapping[str, str] = field(default_factory=empty_frozen_mapping)

    def step_key(self, iteration_index: int, nested_node_id: str) -> str:
        """Return the persisted/reporting step key for one loop iteration node."""
        nested_key = self.nested_presentation_keys.get(nested_node_id)
        if nested_key is None:
            raise KeyError(f"Unknown nested node id '{nested_node_id}' for '{self.node_id}'")
        return f"{self.frame_key}[{iteration_index}].{nested_key}"

    def runtime_step_id(self, iteration_index: int, nested_node_id: str) -> str:
        """Return the runtime-qualified step id for one loop iteration node."""
        nested_suffix = self.nested_step_id_suffixes.get(nested_node_id)
        if nested_suffix is None:
            raise KeyError(f"Unknown nested node id '{nested_node_id}' for '{self.node_id}'")
        return _runtime_step_id(self.node_id, iteration_index, nested_suffix)


@dataclass(frozen=True)
class CallBoundaryProjection:
    """Compatibility metadata for call-boundary checkpoint surfaces."""

    node_id: str
    presentation_key: str
    step_id: str
    iteration_owner_node_id: Optional[str] = None
    iteration_step_id_suffix: Optional[str] = None

    def runtime_step_id(self, iteration_index: Optional[int] = None) -> str:
        """Return the runtime-qualified step id used for call-frame checkpoint storage."""
        if self.iteration_owner_node_id is None:
            return self.step_id
        if not isinstance(iteration_index, int):
            raise ValueError(
                f"Call boundary '{self.node_id}' requires an iteration index to build a runtime step id"
            )
        assert self.iteration_step_id_suffix is not None
        return _runtime_step_id(
            self.iteration_owner_node_id,
            iteration_index,
            self.iteration_step_id_suffix,
        )


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

    def ordered_execution_node_ids(self) -> tuple[str, ...]:
        """Return top-level executable node ids in deterministic execution order."""
        body_node_ids = tuple(
            self.node_id_by_compatibility_index[index]
            for index in sorted(self.node_id_by_compatibility_index)
        )
        finalization_node_ids = tuple(
            self.finalization_node_id_by_index[index]
            for index in sorted(self.finalization_node_id_by_index)
        )
        return body_node_ids + finalization_node_ids

    def node_id_for_execution_index(self, index: int) -> Optional[str]:
        """Return the executable node id for one combined body/finalization execution index."""
        if index < 0:
            return None
        node_id = self.node_id_by_compatibility_index.get(index)
        if node_id is not None:
            return node_id
        body_count = len(self.node_id_by_compatibility_index)
        return self.finalization_node_id_by_index.get(index - body_count)

    def node_id_for_step_id(self, step_id: str) -> Optional[str]:
        """Return the executable node id for a persisted step id."""
        return self.node_id_by_step_id.get(step_id)

    def entry_for_step_id(self, step_id: str) -> Optional[CompatibilityNodeProjection]:
        """Return projection metadata for a persisted step id."""
        node_id = self.node_id_for_step_id(step_id)
        if node_id is None:
            return None
        return self.entries_by_node_id.get(node_id)

    def presentation_key_for_step_id(self, step_id: str) -> Optional[str]:
        """Return the persisted/reporting presentation key for a step id."""
        entry = self.entry_for_step_id(step_id)
        return entry.presentation_key if entry is not None else None

    def compatibility_index_for_step_id(self, step_id: str) -> Optional[int]:
        """Return the top-level compatibility index for a step id when one exists."""
        entry = self.entry_for_step_id(step_id)
        return entry.compatibility_index if entry is not None else None

    def execution_index_for_step_id(self, step_id: str) -> Optional[int]:
        """Return the combined body/finalization execution index for a step id."""
        entry = self.entry_for_step_id(step_id)
        if entry is None:
            return None
        if entry.compatibility_index is not None:
            return entry.compatibility_index
        if entry.finalization_index is not None:
            return len(self.node_id_by_compatibility_index) + entry.finalization_index
        return None

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

    def repeat_until_runtime_step_id(
        self,
        loop_node_id: str,
        iteration_index: int,
        nested_node_id: str,
    ) -> str:
        """Return the runtime-qualified step id for one repeat-until iteration node."""
        projection = self.repeat_until_nodes.get(loop_node_id)
        if projection is None:
            raise KeyError(f"Unknown repeat_until node id '{loop_node_id}'")
        return projection.runtime_step_id(iteration_index, nested_node_id)

    def for_each_runtime_step_id(
        self,
        for_each_node_id: str,
        iteration_index: int,
        nested_node_id: str,
    ) -> str:
        """Return the runtime-qualified step id for one for-each iteration node."""
        projection = self.for_each_nodes.get(for_each_node_id)
        if projection is None:
            raise KeyError(f"Unknown for_each node id '{for_each_node_id}'")
        return projection.runtime_step_id(iteration_index, nested_node_id)

    def call_boundary_runtime_step_id(
        self,
        node_id: str,
        *,
        iteration_index: Optional[int] = None,
    ) -> str:
        """Return the runtime-qualified step id for one call-boundary checkpoint."""
        projection = self.call_boundaries.get(node_id)
        if projection is None:
            raise KeyError(f"Unknown call boundary node id '{node_id}'")
        return projection.runtime_step_id(iteration_index)
