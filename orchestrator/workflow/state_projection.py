"""Executable-IR compatibility projection tables for persisted/reporting surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .executable_ir import WorkflowRegion
from .surface_ast import empty_frozen_mapping


def _runtime_step_id(loop_node_id: str, iteration_index: int, nested_suffix: str) -> str:
    return f"{loop_node_id}#{iteration_index}.{nested_suffix}"


@dataclass(frozen=True)
class CompatibilityStepDefinition:
    """Explicit per-node compatibility metadata for reporting and resume guards."""

    report_kind: str = "unknown"
    command: Any = None
    provider: Optional[str] = None
    consumes: tuple[Any, ...] = ()
    expected_outputs: tuple[Any, ...] = ()
    max_visits: Optional[int] = None
    provider_session_enabled: bool = False
    provider_session_mode: Optional[str] = None
    managed_jobs_enabled: bool = False


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
    step_definition: CompatibilityStepDefinition = field(
        default_factory=CompatibilityStepDefinition
    )


@dataclass(frozen=True)
class IterationStepKeyProjection:
    """Compatibility key formatter for repeat-until or for-each iteration steps."""

    node_id: str
    frame_key: str
    nested_presentation_keys: Mapping[str, str] = field(default_factory=empty_frozen_mapping)
    nested_step_id_suffixes: Mapping[str, str] = field(default_factory=empty_frozen_mapping)
    max_iterations: Optional[int] = None

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
    import_alias: str
    iteration_owner_node_id: Optional[str] = None
    iteration_step_id_suffix: Optional[str] = None

    def runtime_step_id(self, iteration_index: Optional[int] = None) -> str:
        """Return the runtime-qualified step id used for call-frame checkpoint storage."""
        if self.iteration_owner_node_id is None:
            return self.step_id
        if not isinstance(iteration_index, int) or isinstance(iteration_index, bool):
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
class ResumeProjectionSlot:
    """One exact current-projection owner for a persisted resume identity."""

    node_id: str
    step_id: str
    presentation_key: str
    region: WorkflowRegion
    slot_kind: str
    iteration_owner_node_id: Optional[str] = None
    iteration_index: Optional[int] = None
    call_boundary: Optional[CallBoundaryProjection] = None


@dataclass(frozen=True)
class ResumeProjectionSlotIndex:
    """Immutable exact-candidate index for one persisted workflow scope."""

    candidates_by_step_id: Mapping[str, tuple[ResumeProjectionSlot, ...]]
    call_boundaries_by_step_id: Mapping[str, tuple[ResumeProjectionSlot, ...]]
    unclaimed_explicit_rows: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class ResumeIdentityResolution:
    """Exact resolution result for one persisted step-result identity."""

    step_id: Any
    presentation_key: Optional[str]
    candidates: tuple[ResumeProjectionSlot, ...]
    matching_candidates: tuple[ResumeProjectionSlot, ...]
    slot: Optional[ResumeProjectionSlot]

    @property
    def candidate_count(self) -> int:
        """Return the number of candidates matching all supplied selectors."""
        return len(self.matching_candidates)

    @property
    def exact_identity_candidate_count(self) -> int:
        """Return the number of scoped candidates owning the exact identity."""
        return len(self.candidates)


@dataclass(frozen=True)
class ResumeCallBoundaryResolution:
    """Exact resolution result for one persisted call-boundary identity."""

    call_step_id: Any
    candidates: tuple[ResumeProjectionSlot, ...]
    boundary: Optional[CallBoundaryProjection]

    @property
    def candidate_count(self) -> int:
        """Return the number of current boundaries owning the exact identity."""
        return len(self.candidates)


@dataclass(frozen=True)
class StructuredSelectionProjection:
    """Compatibility metadata for one structured branch or case path."""

    marker_step_id: str
    marker_presentation_key: str
    step_presentation_keys: tuple[str, ...] = ()


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
    structured_if_branches: Mapping[str, Mapping[str, StructuredSelectionProjection]] = field(
        default_factory=empty_frozen_mapping
    )
    structured_match_cases: Mapping[str, Mapping[str, StructuredSelectionProjection]] = field(
        default_factory=empty_frozen_mapping
    )

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

    def repeat_until_frame_key(self, loop_node_id: str) -> str:
        """Return the canonical persisted/reporting frame key for one typed repeat-until node."""
        projection = self.repeat_until_nodes.get(loop_node_id)
        if projection is None:
            raise KeyError(f"Unknown repeat_until node id '{loop_node_id}'")
        return projection.frame_key

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

    def enumerate_resume_slots(self, state: Mapping[str, Any]) -> ResumeProjectionSlotIndex:
        """Enumerate exact resume identities admitted by current persisted loop progress."""
        if not isinstance(state, Mapping):
            _raise_resume_projection_state_error(
                "unsupported_shape",
                "workflow state must be a mapping",
            )

        candidates: dict[str, list[ResumeProjectionSlot]] = {}
        call_boundaries: dict[str, list[ResumeProjectionSlot]] = {}
        repeat_nested_node_ids = {
            nested_node_id
            for loop_projection in self.repeat_until_nodes.values()
            for nested_node_id in loop_projection.nested_presentation_keys
        }
        for_each_nested_node_ids = {
            nested_node_id
            for loop_projection in self.for_each_nodes.values()
            for nested_node_id in loop_projection.nested_presentation_keys
        }
        nested_node_ids = repeat_nested_node_ids | for_each_nested_node_ids

        for entry in self.entries_by_node_id.values():
            if entry.node_id in nested_node_ids:
                continue
            _append_resume_slot(
                candidates,
                ResumeProjectionSlot(
                    node_id=entry.node_id,
                    step_id=entry.step_id,
                    presentation_key=entry.presentation_key,
                    region=entry.region,
                    slot_kind="step_result",
                ),
            )

        for boundary in self.call_boundaries.values():
            if boundary.iteration_owner_node_id is not None:
                continue
            entry = self.entries_by_node_id.get(boundary.node_id)
            if entry is None:
                continue
            _append_resume_slot(
                call_boundaries,
                ResumeProjectionSlot(
                    node_id=boundary.node_id,
                    step_id=boundary.step_id,
                    presentation_key=boundary.presentation_key,
                    region=entry.region,
                    slot_kind="call_boundary",
                    call_boundary=boundary,
                ),
            )

        for_each_state = _optional_loop_container(state, "for_each")
        for loop_node_id, loop_projection in self.for_each_nodes.items():
            if loop_projection.frame_key not in for_each_state:
                continue
            iteration_indices = _validated_for_each_iterations(
                loop_projection.frame_key,
                for_each_state[loop_projection.frame_key],
            )
            self._append_iteration_resume_slots(
                candidates,
                call_boundaries,
                loop_node_id=loop_node_id,
                loop_projection=loop_projection,
                iteration_indices=iteration_indices,
                loop_kind="for_each",
            )

        repeat_until_state = _optional_loop_container(state, "repeat_until")
        steps_state = state.get("steps", {})
        if not isinstance(steps_state, Mapping):
            _raise_resume_projection_state_error(
                "unsupported_shape",
                "steps must be a mapping",
            )
        for loop_node_id, loop_projection in self.repeat_until_nodes.items():
            if loop_projection.frame_key not in repeat_until_state:
                continue
            iteration_indices = _validated_repeat_until_iterations(
                loop_projection,
                repeat_until_state[loop_projection.frame_key],
                steps_state.get(loop_projection.frame_key),
            )
            self._append_iteration_resume_slots(
                candidates,
                call_boundaries,
                loop_node_id=loop_node_id,
                loop_projection=loop_projection,
                iteration_indices=iteration_indices,
                loop_kind="repeat_until",
            )

        frozen_candidates = _freeze_resume_slot_map(candidates)
        frozen_boundaries = _freeze_resume_slot_map(call_boundaries)
        unclaimed_rows = tuple(
            (presentation_key, step_id)
            for presentation_key, step_id in _explicit_step_result_rows(steps_state)
            if len(
                tuple(
                    slot
                    for slot in _resume_slot_candidates(
                        frozen_candidates,
                        step_id,
                    )
                    if slot.presentation_key == presentation_key
                )
            )
            == 0
        )
        return ResumeProjectionSlotIndex(
            candidates_by_step_id=frozen_candidates,
            call_boundaries_by_step_id=frozen_boundaries,
            unclaimed_explicit_rows=unclaimed_rows,
        )

    def _append_iteration_resume_slots(
        self,
        candidates: dict[str, list[ResumeProjectionSlot]],
        call_boundaries: dict[str, list[ResumeProjectionSlot]],
        *,
        loop_node_id: str,
        loop_projection: IterationStepKeyProjection,
        iteration_indices: tuple[int, ...],
        loop_kind: str,
    ) -> None:
        for iteration_index in iteration_indices:
            for nested_node_id in loop_projection.nested_presentation_keys:
                entry = self.entries_by_node_id.get(nested_node_id)
                if entry is None:
                    continue
                if loop_kind == "repeat_until":
                    step_id = self.repeat_until_runtime_step_id(
                        loop_node_id,
                        iteration_index,
                        nested_node_id,
                    )
                    presentation_key = self.repeat_until_step_key(
                        loop_node_id,
                        iteration_index,
                        nested_node_id,
                    )
                else:
                    step_id = self.for_each_runtime_step_id(
                        loop_node_id,
                        iteration_index,
                        nested_node_id,
                    )
                    presentation_key = self.for_each_step_key(
                        loop_node_id,
                        iteration_index,
                        nested_node_id,
                    )
                _append_resume_slot(
                    candidates,
                    ResumeProjectionSlot(
                        node_id=nested_node_id,
                        step_id=step_id,
                        presentation_key=presentation_key,
                        region=entry.region,
                        slot_kind="step_result",
                        iteration_owner_node_id=loop_node_id,
                        iteration_index=iteration_index,
                    ),
                )

            for boundary in self.call_boundaries.values():
                if boundary.iteration_owner_node_id != loop_node_id:
                    continue
                entry = self.entries_by_node_id.get(boundary.node_id)
                if entry is None:
                    continue
                step_id = self.call_boundary_runtime_step_id(
                    boundary.node_id,
                    iteration_index=iteration_index,
                )
                presentation_key = loop_projection.step_key(
                    iteration_index,
                    boundary.node_id,
                )
                _append_resume_slot(
                    call_boundaries,
                    ResumeProjectionSlot(
                        node_id=boundary.node_id,
                        step_id=step_id,
                        presentation_key=presentation_key,
                        region=entry.region,
                        slot_kind="call_boundary",
                        iteration_owner_node_id=loop_node_id,
                        iteration_index=iteration_index,
                        call_boundary=boundary,
                    ),
                )

    def resolve_resume_step_id(
        self,
        slot_index: ResumeProjectionSlotIndex,
        step_id: Any,
        presentation_key: Optional[str] = None,
    ) -> ResumeIdentityResolution:
        """Resolve one exact step identity without parsing qualified ids."""
        candidates = _resume_slot_candidates(
            slot_index.candidates_by_step_id,
            step_id,
        )
        matching_candidates = (
            candidates
            if presentation_key is None
            else tuple(
                slot
                for slot in candidates
                if slot.presentation_key == presentation_key
            )
        )
        return ResumeIdentityResolution(
            step_id=step_id,
            presentation_key=presentation_key,
            candidates=candidates,
            matching_candidates=matching_candidates,
            slot=matching_candidates[0] if len(matching_candidates) == 1 else None,
        )

    def resolve_call_boundary(
        self,
        slot_index: ResumeProjectionSlotIndex,
        call_step_id: Any,
    ) -> ResumeCallBoundaryResolution:
        """Resolve one exact call-boundary identity without parsing qualified ids."""
        candidates = _resume_slot_candidates(
            slot_index.call_boundaries_by_step_id,
            call_step_id,
        )
        boundary = (
            candidates[0].call_boundary
            if len(candidates) == 1
            else None
        )
        return ResumeCallBoundaryResolution(
            call_step_id=call_step_id,
            candidates=candidates,
            boundary=boundary,
        )


def _append_resume_slot(
    target: dict[str, list[ResumeProjectionSlot]],
    slot: ResumeProjectionSlot,
) -> None:
    target.setdefault(slot.step_id, []).append(slot)


def _freeze_resume_slot_map(
    slots: Mapping[str, list[ResumeProjectionSlot]],
) -> Mapping[str, tuple[ResumeProjectionSlot, ...]]:
    return MappingProxyType(
        {
            step_id: tuple(candidates)
            for step_id, candidates in slots.items()
        }
    )


def _resume_slot_candidates(
    slots: Mapping[str, tuple[ResumeProjectionSlot, ...]],
    identity: Any,
) -> tuple[ResumeProjectionSlot, ...]:
    if not isinstance(identity, str):
        return ()
    return slots.get(identity, ())


def _optional_loop_container(
    state: Mapping[str, Any],
    field_name: str,
) -> Mapping[str, Any]:
    if field_name not in state:
        return {}
    container = state[field_name]
    if not isinstance(container, Mapping):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"{field_name} must be a mapping",
        )
    return container


def _validated_for_each_iterations(
    frame_key: str,
    progress: Any,
) -> tuple[int, ...]:
    if not isinstance(progress, Mapping):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"for_each.{frame_key} must be a mapping",
        )
    items = progress.get("items")
    completed_indices = progress.get("completed_indices")
    current_index = progress.get("current_index")
    if not isinstance(items, list):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"for_each.{frame_key}.items must be a list",
        )
    completed = _validated_index_list(
        completed_indices,
        field=f"for_each.{frame_key}.completed_indices",
    )
    current = _validated_optional_index(
        current_index,
        field=f"for_each.{frame_key}.current_index",
    )
    item_count = len(items)
    if any(index >= item_count for index in completed):
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"for_each.{frame_key}.completed_indices contains an out-of-range index",
        )
    if current is not None and current >= item_count:
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"for_each.{frame_key}.current_index is out of range",
        )
    if current is not None and current in completed:
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"for_each.{frame_key}.current_index is already completed",
        )
    return tuple((*completed, *((current,) if current is not None else ())))


def _validated_repeat_until_iterations(
    projection: IterationStepKeyProjection,
    progress: Any,
    frame_result: Any,
) -> tuple[int, ...]:
    frame_key = projection.frame_key
    if not isinstance(progress, Mapping):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"repeat_until.{frame_key} must be a mapping",
        )
    required_fields = {
        "current_iteration",
        "completed_iterations",
        "condition_evaluated_for_iteration",
        "last_condition_result",
    }
    if not required_fields.issubset(progress):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"repeat_until.{frame_key} is missing required progress fields",
        )
    max_iterations = projection.max_iterations
    if (
        not isinstance(max_iterations, int)
        or isinstance(max_iterations, bool)
        or max_iterations <= 0
    ):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"repeat_until.{frame_key} has no positive finite projection bound",
        )

    completed = _validated_index_list(
        progress.get("completed_iterations"),
        field=f"repeat_until.{frame_key}.completed_iterations",
    )
    current = _validated_optional_index(
        progress.get("current_iteration"),
        field=f"repeat_until.{frame_key}.current_iteration",
    )
    condition_iteration = _validated_optional_index(
        progress.get("condition_evaluated_for_iteration"),
        field=f"repeat_until.{frame_key}.condition_evaluated_for_iteration",
    )
    last_condition_result = progress.get("last_condition_result")
    if last_condition_result is not None and not isinstance(last_condition_result, bool):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"repeat_until.{frame_key}.last_condition_result must be null or boolean",
        )
    exhausted = progress.get("exhausted", False)
    if not isinstance(exhausted, bool):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"repeat_until.{frame_key}.exhausted must be boolean when present",
        )
    if any(index >= max_iterations for index in completed):
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"repeat_until.{frame_key}.completed_iterations contains an out-of-range index",
        )
    if current is not None and current >= max_iterations:
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"repeat_until.{frame_key}.current_iteration is out of range",
        )
    if condition_iteration is not None and condition_iteration >= max_iterations:
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"repeat_until.{frame_key}.condition_evaluated_for_iteration is out of range",
        )

    if current is not None:
        if set(completed) != set(range(current)):
            _raise_resume_projection_state_error(
                "invalid_loop_progress",
                f"repeat_until.{frame_key}.completed_iterations is not valid prior history",
            )
        if condition_iteration not in (None, current):
            _raise_resume_projection_state_error(
                "invalid_loop_progress",
                f"repeat_until.{frame_key}.condition evaluation conflicts with current iteration",
            )
        if (condition_iteration is None) != (last_condition_result is None):
            _raise_resume_projection_state_error(
                "invalid_loop_progress",
                f"repeat_until.{frame_key}.condition result conflicts with evaluation state",
            )
        if exhausted:
            _raise_resume_projection_state_error(
                "invalid_loop_progress",
                f"repeat_until.{frame_key}.active progress cannot be exhausted",
            )
        return tuple((*completed, current))

    if not completed or condition_iteration is None:
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"repeat_until.{frame_key}.terminal progress requires completed evaluated history",
        )
    terminal_iteration = max(completed)
    if (
        condition_iteration != terminal_iteration
        or set(completed) != set(range(terminal_iteration + 1))
    ):
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"repeat_until.{frame_key}.terminal history is inconsistent",
        )
    if last_condition_result is True and not exhausted:
        return tuple(completed)
    if last_condition_result is not False:
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"repeat_until.{frame_key}.terminal condition result is invalid",
        )
    if set(completed) != set(range(max_iterations)):
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"repeat_until.{frame_key}.exhaustion does not cover max_iterations",
        )
    if not isinstance(frame_result, Mapping):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"steps.{frame_key} must be a mapping for terminal exhaustion",
        )
    if exhausted:
        if frame_result.get("status") != "completed":
            _raise_resume_projection_state_error(
                "invalid_loop_progress",
                f"repeat_until.{frame_key}.successful exhaustion requires a completed frame",
            )
        return tuple(completed)
    error = frame_result.get("error")
    if (
        frame_result.get("status") != "failed"
        or not isinstance(error, Mapping)
        or error.get("type") != "repeat_until_iterations_exhausted"
    ):
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"repeat_until.{frame_key}.failed exhaustion requires the terminal exhaustion error",
        )
    return tuple(completed)


def _validated_index_list(value: Any, *, field: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"{field} must be a list",
        )
    if any(not isinstance(index, int) or isinstance(index, bool) for index in value):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"{field} must contain only non-boolean integers",
        )
    if any(index < 0 for index in value):
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"{field} must contain only nonnegative indices",
        )
    if len(set(value)) != len(value):
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"{field} must not contain duplicate indices",
        )
    return tuple(value)


def _validated_optional_index(value: Any, *, field: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        _raise_resume_projection_state_error(
            "unsupported_shape",
            f"{field} must be null or a non-boolean integer",
        )
    if value < 0:
        _raise_resume_projection_state_error(
            "invalid_loop_progress",
            f"{field} must be nonnegative",
        )
    return value


def _explicit_step_result_rows(
    steps: Mapping[str, Any],
) -> tuple[tuple[str, Any], ...]:
    rows: list[tuple[str, Any]] = []
    for presentation_key, value in steps.items():
        if not isinstance(presentation_key, str):
            continue
        if isinstance(value, Mapping):
            if "step_id" in value:
                rows.append((presentation_key, value.get("step_id")))
            continue
        if not isinstance(value, list):
            continue
        for iteration_index, iteration_rows in enumerate(value):
            if not isinstance(iteration_rows, Mapping):
                continue
            for nested_key, nested_value in iteration_rows.items():
                if (
                    isinstance(nested_key, str)
                    and isinstance(nested_value, Mapping)
                    and "step_id" in nested_value
                ):
                    rows.append(
                        (
                            f"{presentation_key}[{iteration_index}].{nested_key}",
                            nested_value.get("step_id"),
                        )
                    )
    return tuple(rows)


def _raise_resume_projection_state_error(reason: str, message: str) -> None:
    raise ValueError(f"{reason}: {message}")
